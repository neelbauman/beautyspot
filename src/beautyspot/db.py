# src/beautyspot/db.py

import sqlite3
import os
import logging
from datetime import datetime
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

    Implementation Note:
        The methods of this class (save, get, delete) may be called concurrently
        from multiple threads if `Spot` is initialized with `io_workers > 1`.

        Therefore, implementations must be thread-safe. The recommended pattern
        is to create a new database connection within each method call
        (or use a thread-safe connection pool), rather than sharing a single
        connection attribute across threads.
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
    ):
        pass

    @abstractmethod
    def get_history(self, limit: int = 1000) -> "pd.DataFrame":
        pass

    @abstractmethod
    def delete(self, cache_key: str) -> bool:
        pass

    # --- Optional Maintenance Methods ---

    def prune(self, older_than: datetime, func_name: Optional[str] = None) -> int:
        """Delete tasks older than the specified datetime."""
        logger.warning(
            f"{self.__class__.__name__} does not support pruning operations."
        )
        return 0

    def get_outdated_tasks(self, older_than: datetime, func_name: Optional[str] = None) -> list[tuple[str, str, str]]:
        """
        Retrieve tasks older than the specified datetime (Preview for prune).
        Returns a list of (cache_key, func_name, updated_at).
        """
        return []

    def get_blob_refs(self) -> Optional[set[str]]:
        """Retrieve all 'result_value' entries that point to external storage."""
        return None


class SQLiteTaskDB(TaskDBBase):
    """
    Default implementation using SQLite.
    """

    def __init__(self, db_path: str | Path, timeout: float = 30.0):
        """
        Args:
            db_path: Path to the SQLite database file.
            timeout: How many seconds the connection should wait for the lock
                     to go away before raising an error. Default is 30.0s.
        """
        self.db_path = db_path
        self.timeout = timeout


    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=self.timeout)

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

            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            if "content_type" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN content_type TEXT;")
            if "version" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN version TEXT;")
            if "result_data" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN result_data BLOB;")

    def get(self, cache_key: str) -> Optional[TaskRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_type, result_value, result_data FROM tasks WHERE cache_key=?",
                (cache_key,),
            ).fetchone()
            if row:
                return {
                    "result_type": row[0],
                    "result_value": row[1],
                    "result_data": row[2],
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
    ):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (cache_key, func_name, input_id, version, result_type, content_type, result_value, result_data) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    content_type, result_value, result_data, updated_at 
                FROM tasks 
                ORDER BY updated_at DESC LIMIT ?
            """
            return pd.read_sql_query(query, conn, params=[limit])

    def delete(self, cache_key: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE cache_key=?", (cache_key,))
            return cursor.rowcount > 0

    def prune(self, older_than: datetime, func_name: Optional[str] = None) -> int:
        cutoff_str = older_than.strftime("%Y-%m-%d %H:%M:%S")
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

    def get_outdated_tasks(self, older_than: datetime, func_name: Optional[str] = None) -> list[tuple[str, str, str]]:
        cutoff_str = older_than.strftime("%Y-%m-%d %H:%M:%S")
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

    def get_blob_refs(self) -> Optional[set[str]]:
        if not os.path.exists(self.db_path):
            return set()

        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT result_value FROM tasks WHERE result_type = 'FILE' AND result_value IS NOT NULL"
            )
            # Use filename for robust matching across machines/paths
            return {Path(row[0]).name for row in cursor.fetchall() if row[0]}

