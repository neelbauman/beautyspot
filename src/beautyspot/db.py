# src/beautyspot/db.py

import sqlite3
import os
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class TaskRecord(TypedDict):
    result_type: str
    result_value: Optional[str]
    result_data: Optional[bytes]


class TaskDBBase(ABC):
    """
    Abstract interface for task metadata storage.
    """

    @abstractmethod
    def init_schema(self):
        pass

    @abstractmethod
    def get(self, cache_key: str) -> Optional[TaskRecord]:
        pass

    @abstractmethod
    def save(
        self,
        cache_key: str,
        func_name: str,
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


class SQLiteTaskDB(TaskDBBase):
    """
    Default implementation using SQLite.
    """

    def __init__(self, db_path: str | Path, timeout: float = 30.0):
        self.db_path = db_path
        self.timeout = timeout

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """
        Thread-safe connection context manager.
        Each call creates a new connection (one per operation), ensuring that
        concurrent callers from different threads never share a connection.
        Commits on success, rolls back on exception, and always closes.
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

    def init_schema(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    cache_key TEXT PRIMARY KEY,
                    func_name TEXT,
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

            if "expires_at" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN expires_at TIMESTAMP;")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_expires_at ON tasks(expires_at);"
                )

    def get(self, cache_key: str) -> Optional[TaskRecord]:
        with self._connect() as conn:
            # [MOD] Include expires_at in query
            row = conn.execute(
                "SELECT result_type, result_value, result_data, expires_at FROM tasks WHERE cache_key=?",
                (cache_key,),
            ).fetchone()

            if row:
                r_type, r_val, r_data, exp_str = row

                # [ADD] Lazy Expiration Check
                if exp_str:
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

                return {
                    "result_type": r_type,
                    "result_value": r_val,
                    "result_data": r_data,
                }
        return None

    def save(
        self,
        cache_key: str,
        func_name: str,
        input_id: str,
        version: Optional[str],
        result_type: str,
        content_type: Optional[str],
        result_value: Optional[str] = None,
        result_data: Optional[bytes] = None,
        expires_at: Optional[datetime] = None,  # [ADD] Added argument
    ):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (cache_key, func_name, input_id, version, result_type, content_type, result_value, result_data, expires_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    func_name,
                    input_id,
                    version,
                    result_type,
                    content_type,
                    result_value,
                    result_data,
                    (
                        expires_at.replace(tzinfo=timezone.utc)
                        if expires_at.tzinfo is None
                        else expires_at
                    ).isoformat(" ")
                    if expires_at is not None
                    else None,
                ),
            )

    def get_history(self, limit: int = 1000) -> "pd.DataFrame":
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("Pandas is required for this feature.") from e

        if not os.path.exists(self.db_path):
            return pd.DataFrame()

        with self._connect() as conn:
            query = """
                SELECT 
                    cache_key, func_name, input_id, version, result_type, 
                    content_type, result_value, result_data, updated_at, expires_at 
                FROM tasks 
                ORDER BY updated_at DESC LIMIT ?
            """
            return pd.read_sql_query(query, conn, params=[limit])

    def delete(self, cache_key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE cache_key=?", (cache_key,))
            return cursor.rowcount > 0

    def delete_all(self, func_name: Optional[str] = None) -> int:
        with self._connect() as conn:
            if func_name:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE func_name = ?", (func_name,)
                )
            else:
                cursor = conn.execute("DELETE FROM tasks")
            return cursor.rowcount

    def prune(self, older_than: datetime, func_name: Optional[str] = None) -> int:
        if older_than.tzinfo is None:
            older_than = older_than.replace(tzinfo=timezone.utc)
        cutoff_str = older_than.isoformat(" ")
        with self._connect() as conn:
            if func_name:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE updated_at < ? AND func_name = ?",
                    (cutoff_str, func_name),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE updated_at < ?",
                    (cutoff_str,),
                )
            return cursor.rowcount

    def get_outdated_tasks(
        self, older_than: datetime, func_name: Optional[str] = None
    ) -> list[tuple[str, str, str]]:
        if older_than.tzinfo is None:
            older_than = older_than.replace(tzinfo=timezone.utc)
        cutoff_str = older_than.isoformat(" ")
        if not os.path.exists(self.db_path):
            return []

        with self._connect() as conn:
            if func_name:
                cursor = conn.execute(
                    "SELECT cache_key, func_name, updated_at FROM tasks WHERE updated_at < ? AND func_name = ?",
                    (cutoff_str, func_name),
                )
            else:
                cursor = conn.execute(
                    "SELECT cache_key, func_name, updated_at FROM tasks WHERE updated_at < ?",
                    (cutoff_str,),
                )
            return [(row[0], row[1], str(row[2])) for row in cursor.fetchall()]

    def delete_expired(self) -> int:
        if not os.path.exists(self.db_path):
            return 0

        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at < ?",
                (datetime.now(timezone.utc).isoformat(" "),),
            )
            return cursor.rowcount

    def get_blob_refs(self) -> Optional[set[str]]:
        if not os.path.exists(self.db_path):
            return set()

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT result_value FROM tasks WHERE result_type = 'FILE' AND result_value IS NOT NULL"
            )
            # Use filename for robust matching across machines/paths
            return {Path(row[0]).name for row in cursor.fetchall() if row[0]}

    def get_keys_start_with(self, prefix: str) -> list[str]:
        if not os.path.exists(self.db_path):
            return []

        with self._connect() as conn:
            # プレフィックス検索 (LIMITをつけて大量取得を防止)
            cursor = conn.execute(
                "SELECT cache_key FROM tasks WHERE cache_key LIKE ? LIMIT 50",
                (f"{prefix}%",),
            )
            return [row[0] for row in cursor.fetchall()]
