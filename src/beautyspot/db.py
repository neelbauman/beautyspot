# src/beautyspot/db.py

import sqlite3
import os
import logging
import queue
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING, TypedDict, Any, Callable

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


def _ensure_utc_isoformat_naive(dt: datetime) -> str:
    """UTCに揃えたタイムゾーンなしの ISO 8601 文字列に変換する。"""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
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

    def __init__(self, db_path: str | Path, timeout: float = 30.0):
        self.db_path = Path(db_path).resolve()
        self._ensure_cache_dir(self.db_path.parent)
        self.timeout = timeout
        self._write_queue: queue.Queue[object] = queue.Queue()
        self._shutdown_lock = threading.Lock()
        self._shutdown_requested = False
        self._writer_ready = threading.Event()
        self._writer_error: Exception | None = None
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
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Connection context manager for schema/maintenance operations.
        Each call creates a new connection, commits on success, rolls back on
        exception, and always closes.
        """
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _read_connect(self) -> Iterator[sqlite3.Connection]:
        """
        Thread-safe connection context manager for read-only operations.
        Skips commit/rollback since no data is modified.
        """
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        try:
            yield conn
        finally:
            conn.close()

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
                try:
                    task.result = task.fn(conn)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    task.error = e
                finally:
                    task.event.set()
                    self._write_queue.task_done()
        finally:
            if conn is not None:
                conn.close()

    def _enqueue_write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        self._writer_ready.wait()
        if self._writer_error:
            raise RuntimeError("SQLite writer thread failed to start.") from self._writer_error

        with self._shutdown_lock:
            if self._shutdown_requested:
                raise RuntimeError("SQLiteTaskDB is shutting down.")
            if not self._writer_thread.is_alive():
                raise RuntimeError("SQLite writer thread is not running.")
            task = _WriteTask(fn=fn, event=threading.Event())
            self._write_queue.put(task)

        start = time.monotonic()
        while not task.event.wait(timeout=0.5):
            if not self._writer_thread.is_alive():
                raise RuntimeError("SQLite writer thread stopped unexpectedly.")
            if self._shutdown_requested:
                raise RuntimeError("SQLiteTaskDB is shutting down.")
            if time.monotonic() - start > self.timeout:
                raise TimeoutError(
                    f"SQLite write did not complete within {self.timeout}s."
                )
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

    def init_schema(self):
        with self._connect() as conn:
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
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # [ADD] Auto Migration for expires_at
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            if "content_type" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN content_type TEXT;")
            if "version" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN version TEXT;")
            if "result_data" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN result_data BLOB;")

            if "func_identifier" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN func_identifier TEXT;")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_func_identifier ON tasks(func_identifier);"
                )

            if "expires_at" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN expires_at TIMESTAMP;")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_expires_at ON tasks(expires_at);"
                )

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
                        expires_at = datetime.fromisoformat(exp_str)
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
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (cache_key, func_name, func_identifier, input_id, version, result_type, content_type, result_value, result_data, expires_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        cutoff_str = _ensure_utc_isoformat_naive(older_than)
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
        cutoff_str = _ensure_utc_isoformat_naive(older_than)
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

        def _op(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at < ?",
                (datetime.now(timezone.utc).isoformat(" "),),
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

    def flush(self, timeout: Optional[float] = None) -> bool:
        """
        キューに溜まっているすべての書き込み操作が完了するまで待機します。
        
        No-op（何もしない）タスクをキューの末尾に挿入し、そのタスクが処理されるまで
        待機することで、先行するすべてのタスクの完了を保証します。
        
        Args:
            timeout: 待機する最大秒数。タイムアウトした場合は False を返します。
        """
        self._writer_ready.wait()
        
        with self._shutdown_lock:
            if self._shutdown_requested or not self._writer_thread.is_alive():
                return False

        # キューをフラッシュするためのダミータスク
        def _noop_op(conn: sqlite3.Connection) -> None:
            pass

        task = _WriteTask(fn=_noop_op, event=threading.Event())
        self._write_queue.put(task)
        
        # ダミータスクの完了を待機
        return task.event.wait(timeout=timeout)

