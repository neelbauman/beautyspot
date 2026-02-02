# tests/conftest.py

import pytest
import sqlite3


@pytest.fixture
def inspect_db():
    """Factory fixture to inspect SQLite DB directly."""

    def _fetch_all(db_path):
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks")
            return [dict(row) for row in cursor.fetchall()]

    return _fetch_all
