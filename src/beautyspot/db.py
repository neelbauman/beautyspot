# src/beautyspot/db.py

import sqlite3
import os
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

class TaskDB:
    """
    Data Access Object (DAO) for the tasks database (SQLite).
    Encapsulates all SQL queries and schema management.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def init_schema(self):
        """
        Ensures the DB table exists and performs auto-migration if columns are missing.
        """
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")

            # 1. Create Table (if not exists)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    cache_key TEXT PRIMARY KEY,
                    func_name TEXT,
                    input_id  TEXT,
                    result_type TEXT,
                    result_value TEXT, 
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 2. Migration: Check and Add columns dynamically
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "content_type" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN content_type TEXT;")
            if "version" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN version TEXT;")

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a task result by cache key."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result_type, result_value FROM tasks WHERE cache_key=?", 
                (cache_key,)
            ).fetchone()
            if row:
                return {"result_type": row[0], "result_value": row[1]}
        return None

    def save(
        self, 
        cache_key: str, 
        func_name: str, 
        input_id: str, 
        version: Optional[str], 
        result_type: str, 
        content_type: Optional[str], 
        result_value: str
    ):
        """Upsert a task result."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks 
                (cache_key, func_name, input_id, version, result_type, content_type, result_value) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cache_key, func_name, input_id, version, result_type, content_type, result_value)
            )

    def get_history(self, limit: int = 1000) -> "pd.DataFrame":
        """
        Fetch task history for analysis/dashboard.
        Uses lazy import for pandas to keep the core library lightweight.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "Pandas is required for this feature. "
                "Please install it via `pip install 'beautyspot[dashboard]'` "
                "or `pip install pandas`."
            ) from e

        if not os.path.exists(self.db_path):
            return pd.DataFrame()

        with self._connect() as conn:
            query = """
                SELECT 
                    cache_key, 
                    func_name, 
                    input_id, 
                    version, 
                    result_type, 
                    content_type, 
                    result_value, 
                    updated_at 
                FROM tasks 
                ORDER BY updated_at DESC 
                LIMIT ?
            """
            return pd.read_sql_query(query, conn, params=(limit,))

