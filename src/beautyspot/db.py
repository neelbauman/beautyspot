# src/beautyspot/db.py

import sqlite3
import os
import logging
import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING, TypedDict, Any, Callable
import weakref


class _ReadConnWrapper:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.lock = threading.RLock()
        self._closed = False

    def close(self, wait: bool = True):
        """
        Args:
            wait: True の場合はロック解放を待機。
                  False (シャットダウン時) の場合は即座に試行し、他が使用中ならスキップする。
        """
        # wait=False の場合は blocking=False になり、取得できなければ直ちに False を返す
        if not self.lock.acquire(blocking=wait):
            # 誰かがクエリ実行中なので、強制クローズによるクラッシュを防ぐために諦める。
            # (次回のアクセス時に self._shutdown_requested で弾かれるため問題ない)
            return

        try:
            if not self._closed:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self._closed = True
        finally:
            self.lock.release()

    def __del__(self):
        self.close()


if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def _ensure_utc_isoformat(dt: Optional[datetime]) -> Optional[str]:
    """datetime を UTC 保証の ISO 8601 文字列に変換する。None はそのまま返す。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat(" ")


class TaskRecord(TypedDict):
    result_type: str
    result_value: Optional[str]
    result_data: Optional[bytes]
    expires_at: Optional[str]


@dataclass
class _WriteTask:
    fn: Callable[[sqlite3.Connection], Any]
    event: threading.Event
    result: Any = None
    error: Exception | None = None
    state: str = "PENDING"  # "PENDING", "RUNNING", "DONE", "CANCELLED"
    _state_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)

    def try_cancel(self) -> bool:
        """PENDING 状態のタスクをキャンセルする。成功時 True。"""
        with self._state_lock:
            if self.state == "PENDING":
                self.state = "CANCELLED"
                return True
            return False

    def try_start(self) -> bool:
        """PENDING → RUNNING に遷移する。CANCELLED なら False を返す。"""
        with self._state_lock:
            if self.state == "CANCELLED":
                return False
            self.state = "RUNNING"
            return True

    def mark_done(self) -> None:
        """RUNNING → DONE に遷移する。"""
        with self._state_lock:
            if self.state != "CANCELLED":
                self.state = "DONE"


_STOP = object()


class TaskDBBase(ABC):
    """
    Abstract interface for task metadata storage.
    """

    @abstractmethod
    def init_schema(self):
        pass

    @abstractmethod
    def get(
        self, cache_key: str, *, include_expired: bool = False
    ) -> Optional[TaskRecord]:
        pass

    @abstractmethod
    def save(
        self,
        cache_key: str,
        func_name: str,
        func_identifier: Optional[str],
        input_id: str,
        version: Optional[str],
        result_type: str,
        content_type: Optional[str],
        result_value: Optional[str] = None,
        result_data: Optional[bytes] = None,
        expires_at: Optional[datetime] = None,  # [ADD] Added argument
    ):
        pass

    @abstractmethod
    def get_history(self, limit: int = 1000) -> "pd.DataFrame":
        pass

    @abstractmethod
    def delete(self, cache_key: str) -> bool:
        pass

    # --- Optional Maintenance Methods ---
    def delete_expired(self) -> int:
        """Delete tasks that have passed their expiration time."""
        return 0

    def prune(self, older_than: datetime, func_name: Optional[str] = None) -> int:
        """Delete tasks older than the specified datetime."""
        logger.warning(
            f"{self.__class__.__name__} does not support pruning operations."
        )
        return 0

    def get_outdated_tasks(
        self, older_than: datetime, func_name: Optional[str] = None
    ) -> list[tuple[str, str, str]]:
        """
        Retrieve tasks older than the specified datetime (Preview for prune).
        """
        return []

    def get_blob_refs(self) -> Optional[set[str]]:
        """Retrieve all 'result_value' entries that point to external storage."""
        return None

    def delete_all(self, func_name: Optional[str] = None) -> int:
        """Delete all tasks, optionally filtered by function name."""
        return 0

    def get_keys_start_with(self, prefix: str) -> list[str]:
        """Retrieve cache keys that start with the given prefix."""
        return []

    def flush(self, timeout: Optional[float] = None) -> bool:
        """Wait for all pending background writes to complete."""
        return True

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully shut down the database backend."""
        return None


class SQLiteTaskDB(TaskDBBase):
    """
    Default implementation using SQLite.
    """

    def __init__(self, db_path: str | Path | None = None, timeout: float = 30.0):
        self.db_path = (
            Path(db_path).resolve() if db_path else Path(f".beautyspot/{hash(self)}.db")
        )
        self._ensure_cache_dir(self.db_path.parent)
        self.timeout = timeout
        self._local = threading.local()
        self._write_queue: queue.Queue[object] = queue.Queue()
        self._shutdown_lock = threading.Lock()
        self._shutdown_requested = False
        self._writer_ready = threading.Event()
        self._writer_error: Exception | None = None
        # 読み取り専用スレッドローカル接続を追跡し、
        # shutdown() 時に一括クローズする。WAL チェックポイントの妨げを防ぐ。
        self._read_wrappers = weakref.WeakSet()
        self._read_conns_lock = threading.Lock()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="BeautySpot-SQLiteWriter"
        )
        self._writer_thread.start()
        self._writer_ready.wait()
        if self._writer_error:
            raise self._writer_error

    @staticmethod
    def _ensure_cache_dir(directory: Path) -> None:
        """
        データベース格納用の親ディレクトリを作成し、.gitignore を配置する。
        """
        directory.mkdir(parents=True, exist_ok=True)
        gitignore_path = directory / ".gitignore"
        if not gitignore_path.exists():
            try:
                gitignore_path.write_text("*\n")
            except OSError as e:
                logging.warning(f"Failed to create .gitignore in {directory}: {e}")

    @contextmanager
    def _read_connect(self) -> Iterator[sqlite3.Connection]:
        """
        Thread-safe connection context manager for read-only operations.
        Uses a thread-local pool to reuse connections and reduce overhead.
        PRAGMA query_only = ON により、誤った書き込みを接続レベルで防止する。

        新規接続を _read_wrappers に登録し、
        shutdown() 時の一括クローズで WAL チェックポイント妨害を防ぐ。
        また、_ReadConnWrapper によってスレッド終了時に接続がクローズされ、メモリリークを防止。
        """
        if self._shutdown_requested:
            raise RuntimeError("SQLiteTaskDB is shutting down.")

        wrapper = getattr(self._local, "read_conn_wrapper", None)
        if wrapper is None or wrapper._closed:
            # シャットダウン後に新しい接続がリークするのを防ぐため再チェック。
            # 最初のチェック通過後に別スレッドが shutdown() を呼び出し、
            # 全ラッパーをクローズした場合にここに到達する。
            if self._shutdown_requested:
                raise RuntimeError("SQLiteTaskDB is shutting down.")
            conn = sqlite3.connect(
                self.db_path, timeout=self.timeout, check_same_thread=False
            )
            try:
                conn.execute("PRAGMA query_only = ON;")
            except Exception:
                conn.close()
                raise
            wrapper = _ReadConnWrapper(conn)
            with self._read_conns_lock:
                # ロック内で再度チェックし、shutdown() による _read_wrappers.clear() と
                # 新規追加の間の競合を完全に排除する。
                if self._shutdown_requested:
                    conn.close()
                    raise RuntimeError("SQLiteTaskDB is shutting down.")
                self._read_wrappers.add(wrapper)
            self._local.read_conn_wrapper = wrapper

        with wrapper.lock:
            if wrapper._closed:
                raise RuntimeError("Database connection was closed")
            try:
                yield wrapper.conn
            except sqlite3.Error:
                # 接続が壊れた場合等のリカバリ (BUG-3)
                # 現在の接続を破棄し、次回のアクセス時に新しく作り直す
                wrapper.close()
                with self._read_conns_lock:
                    self._read_wrappers.discard(wrapper)
                self._local.read_conn_wrapper = None
                raise

    def _writer_loop(self) -> None:
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception as e:
            self._writer_error = e
            self._writer_ready.set()
            return

        self._writer_ready.set()
        try:
            while True:
                task = self._write_queue.get()
                if task is _STOP:
                    self._write_queue.task_done()
                    break
                assert isinstance(task, _WriteTask)
                if not task.try_start():
                    # CANCELLED 状態 — スキップ
                    task.event.set()
                    self._write_queue.task_done()
                    continue

                try:
                    task.result = task.fn(conn)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    task.error = e
                finally:
                    task.mark_done()
                    task.event.set()
                    self._write_queue.task_done()
        finally:
            if conn is not None:
                conn.close()

    def _enqueue_write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        self._writer_ready.wait()
        if self._writer_error:
            raise RuntimeError(
                "SQLite writer thread failed to start."
            ) from self._writer_error

        with self._shutdown_lock:
            if self._shutdown_requested:
                raise RuntimeError("SQLiteTaskDB is shutting down.")
            if not self._writer_thread.is_alive():
                raise RuntimeError("SQLite writer thread is not running.")
            task = _WriteTask(fn=fn, event=threading.Event())
            self._write_queue.put(task)

        start = time.monotonic()
        _warned_running = False
        while not task.event.wait(timeout=0.5):
            if not self._writer_thread.is_alive():
                raise RuntimeError("SQLite writer thread stopped unexpectedly.")
            if self._shutdown_requested:
                raise RuntimeError("SQLiteTaskDB is shutting down.")
            elapsed = time.monotonic() - start
            if elapsed > self.timeout:
                if task.try_cancel():
                    # PENDING（未着手）のタスクはキャンセル可能
                    raise TimeoutError(
                        f"SQLite write did not start within {self.timeout}s and was cancelled."
                    )
                elif not _warned_running:
                    # RUNNING（実行中）のタスクはキャンセル不可。
                    # 旧実装では RUNNING でも TimeoutError を送出していたが、
                    # DB への書き込みは継続されるため呼び出し元との整合性が取れなかった。
                    # 修正後は完了まで待ち続け、警告ログのみ出力する。
                    logger.warning(
                        f"SQLite write has been running for over {self.timeout}s. "
                        "The operation cannot be cancelled and will continue until completion."
                    )
                    _warned_running = True
                # RUNNING 状態: 完了まで待ち続ける（TimeoutError は送出しない）
        if task.error:
            raise task.error
        return task.result

    def shutdown(self, wait: bool = True) -> None:
        with self._shutdown_lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True

        if not self._writer_thread.is_alive():
            logger.error(
                "SQLite writer thread is not running; pending writes may be lost."
            )
            return

        if wait:
            self._write_queue.join()
        self._write_queue.put(_STOP)
        if wait:
            self._writer_thread.join()

        # 全スレッドのread-only接続を一括クローズ。
        # スレッドローカル接続が開いたままだと WAL チェックポイントを妨げるため。
        with self._read_conns_lock:
            for wrapper in self._read_wrappers:
                try:
                    wrapper.close(wait=False)
                except Exception:
                    pass
            self._read_wrappers.clear()

    def init_schema(self):
        # スキーマ初期化および全マイグレーションを Writer Thread の接続で実行する。
        # _connect() による別コネクション経由の DDL は、Writer Thread が保持する
        # WAL ライターロックと競合するリスクがあるため、_enqueue_write に委譲する。
        def _op(conn: sqlite3.Connection) -> None:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    cache_key TEXT PRIMARY KEY,
                    func_name TEXT,
                    func_identifier TEXT,
                    input_id  TEXT,
                    result_type TEXT,
                    result_value TEXT,
                    result_data BLOB,
                    content_type TEXT,
                    version TEXT,
                    expires_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Auto Migration
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            if "content_type" not in columns:
                try:
                    conn.execute("ALTER TABLE tasks ADD COLUMN content_type TEXT;")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    pass
            if "version" not in columns:
                try:
                    conn.execute("ALTER TABLE tasks ADD COLUMN version TEXT;")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    pass
            if "result_data" not in columns:
                try:
                    conn.execute("ALTER TABLE tasks ADD COLUMN result_data BLOB;")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    pass

            if "func_identifier" not in columns:
                try:
                    conn.execute("ALTER TABLE tasks ADD COLUMN func_identifier TEXT;")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    pass
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_func_identifier ON tasks(func_identifier);"
                )

            if "expires_at" not in columns:
                try:
                    conn.execute("ALTER TABLE tasks ADD COLUMN expires_at TIMESTAMP;")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e).lower():
                        raise
                    pass
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_expires_at ON tasks(expires_at);"
                )

        self._enqueue_write(_op)

    def get(
        self, cache_key: str, *, include_expired: bool = False
    ) -> Optional[TaskRecord]:
        with self._read_connect() as conn:
            # [MOD] Include expires_at in query
            row = conn.execute(
                "SELECT result_type, result_value, result_data, expires_at FROM tasks WHERE cache_key=?",
                (cache_key,),
            ).fetchone()

            if row:
                r_type, r_val, r_data, exp_str = row

                # [ADD] Lazy Expiration Check (skip when include_expired=True)
                if exp_str and not include_expired:
                    try:
                        # SQLite returns timestamps as strings usually
                        # Replace space with T for compatibility with Python <= 3.10
                        expires_at = datetime.fromisoformat(exp_str.replace(" ", "T"))
                        # Naive datetimes stored before timezone support are treated as UTC
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        if expires_at < datetime.now(timezone.utc):
                            # Expired -> Treat as Cache Miss
                            # (Physical deletion is deferred to `beautyspot gc`)
                            return None
                    except (ValueError, TypeError):
                        pass  # Ignore parsing errors, treat as valid

                return TaskRecord(
                    result_type=r_type,
                    result_value=r_val,
                    result_data=r_data,
                    expires_at=exp_str,
                )
        return None

    def save(
        self,
        cache_key: str,
        func_name: str,
        func_identifier: Optional[str],
        input_id: str,
        version: Optional[str],
        result_type: str,
        content_type: Optional[str],
        result_value: Optional[str] = None,
        result_data: Optional[bytes] = None,
        expires_at: Optional[datetime] = None,  # [ADD] Added argument
    ):
        def _op(conn: sqlite3.Connection) -> None:
            effective_identifier = func_identifier or func_name
            # updated_at を明示的に設定し、expires_at と同じ形式
            # (_ensure_utc_isoformat) で統一する。
            # SQLite の DEFAULT CURRENT_TIMESTAMP は秒精度でフォーマットが異なるため、
            # prune/get_outdated_tasks との比較精度を揃える。
            now_str = _ensure_utc_isoformat(datetime.now(timezone.utc))
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks
                (cache_key, func_name, func_identifier, input_id, version, result_type, content_type, result_value, result_data, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    func_name,
                    effective_identifier,
                    input_id,
                    version,
                    result_type,
                    content_type,
                    result_value,
                    result_data,
                    _ensure_utc_isoformat(expires_at),
                    now_str,
                ),
            )

        self._enqueue_write(_op)

    def get_history(self, limit: int = 1000) -> "pd.DataFrame":
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("Pandas is required for this feature.") from e

        if not os.path.exists(self.db_path):
            return pd.DataFrame()

        with self._read_connect() as conn:
            query = """
                SELECT
                    cache_key, func_name, func_identifier, input_id, version, result_type,
                    content_type, result_value, result_data, updated_at, expires_at
                FROM tasks
                ORDER BY updated_at DESC LIMIT ?
            """
            return pd.read_sql_query(query, conn, params=[limit])

    def delete(self, cache_key: str) -> bool:
        def _op(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("DELETE FROM tasks WHERE cache_key=?", (cache_key,))
            return cursor.rowcount > 0

        return bool(self._enqueue_write(_op))

    def delete_all(self, func_name: Optional[str] = None) -> int:
        def _op(conn: sqlite3.Connection) -> int:
            if func_name:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE func_name = ? OR func_identifier = ?",
                    (func_name, func_name),
                )
            else:
                cursor = conn.execute("DELETE FROM tasks")
            return cursor.rowcount

        return int(self._enqueue_write(_op))

    def prune(self, older_than: datetime, func_name: Optional[str] = None) -> int:
        cutoff_str = _ensure_utc_isoformat(older_than)

        def _op(conn: sqlite3.Connection) -> int:
            if func_name:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE updated_at < ? AND (func_name = ? OR func_identifier = ?)",
                    (cutoff_str, func_name, func_name),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE updated_at < ?",
                    (cutoff_str,),
                )
            return cursor.rowcount

        return int(self._enqueue_write(_op))

    def get_outdated_tasks(
        self, older_than: datetime, func_name: Optional[str] = None
    ) -> list[tuple[str, str, str]]:
        cutoff_str = _ensure_utc_isoformat(older_than)
        if not os.path.exists(self.db_path):
            return []

        with self._read_connect() as conn:
            if func_name:
                cursor = conn.execute(
                    "SELECT cache_key, COALESCE(func_identifier, func_name), updated_at FROM tasks "
                    "WHERE updated_at < ? AND (func_name = ? OR func_identifier = ?)",
                    (cutoff_str, func_name, func_name),
                )
            else:
                cursor = conn.execute(
                    "SELECT cache_key, COALESCE(func_identifier, func_name), updated_at FROM tasks WHERE updated_at < ?",
                    (cutoff_str,),
                )
            return [(row[0], row[1], str(row[2])) for row in cursor.fetchall()]

    def delete_expired(self) -> int:
        if not os.path.exists(self.db_path):
            return 0

        # save() と同じ _ensure_utc_isoformat を使い、フォーマットを統一する
        now_str = _ensure_utc_isoformat(datetime.now(timezone.utc))

        def _op(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now_str,),
            )
            return cursor.rowcount

        return int(self._enqueue_write(_op))

    def get_blob_refs(self) -> Optional[set[str]]:
        if not os.path.exists(self.db_path):
            return set()

        with self._read_connect() as conn:
            cursor = conn.execute(
                "SELECT result_value FROM tasks WHERE result_type = 'FILE' AND result_value IS NOT NULL"
            )
            # Return full location strings for precise matching
            return {row[0] for row in cursor.fetchall() if row[0]}

    def get_keys_start_with(self, prefix: str) -> list[str]:
        if not os.path.exists(self.db_path):
            return []

        with self._read_connect() as conn:
            # LIKE ワイルドカード文字をエスケープしてプレフィックス検索
            escaped = (
                prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            cursor = conn.execute(
                "SELECT cache_key FROM tasks WHERE cache_key LIKE ? ESCAPE '\\' LIMIT 50",
                (f"{escaped}%",),
            )
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def count_tasks(db_path: Path, timeout: float = 5.0) -> int:
        """
        Writer Thread を起動せずに tasks テーブルの件数を返す軽量ユーティリティ。
        CLI の一覧表示など、読み込みのみを目的とした用途向け。
        エラー時は -1 を返す。
        """
        try:
            conn = sqlite3.connect(str(db_path), timeout=timeout)
            try:
                # 読み取り専用ユーティリティに journal_mode=WAL 設定は不要。
                # query_only=ON との組み合わせで動作が曖昧になる可能性もあるため削除。
                conn.execute("PRAGMA query_only = ON;")
                cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                result = cursor.fetchone()
                return result[0] if result else 0
            finally:
                conn.close()
        except Exception:
            return -1

    def flush(self, timeout: Optional[float] = None) -> bool:
        """
        キューに溜まっているすべての書き込み操作が完了するまで待機します。

        No-op（何もしない）タスクをキューの末尾に挿入し、そのタスクが処理されるまで
        待機することで、先行するすべてのタスクの完了を保証します。

        Args:
            timeout: 待機する最大秒数。タイムアウトした場合は False を返します。
                     None の場合は無期限に待機しますが、ライタースレッドの
                     死活監視ループにより永久ハングは防止されます。
        """
        self._writer_ready.wait()

        # キューをフラッシュするためのダミータスク
        def _noop_op(conn: sqlite3.Connection) -> None:
            pass

        task = _WriteTask(fn=_noop_op, event=threading.Event())

        # shutdown との TOCTOU を防ぐため、ロック内でチェックと put を原子的に行う
        with self._shutdown_lock:
            if self._shutdown_requested or not self._writer_thread.is_alive():
                return False
            self._write_queue.put(task)

        # ライタースレッドの死活を定期確認しながら待機する。
        # timeout=None で event.wait() を直接呼ぶとスレッド死亡時に永久ハングするため、
        # ポーリングループで代替する。
        _POLL = 0.5
        deadline = (time.monotonic() + timeout) if timeout is not None else None

        while True:
            remaining = (
                max(0.0, deadline - time.monotonic()) if deadline is not None else None
            )
            wait_time = _POLL if remaining is None else min(_POLL, remaining)

            if task.event.wait(timeout=wait_time):
                return True

            if not self._writer_thread.is_alive():
                logger.error(
                    "SQLite writer thread died unexpectedly while waiting for flush."
                )
                return False

            if deadline is not None and time.monotonic() >= deadline:
                return False
