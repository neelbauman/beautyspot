# tests/conftest.py

import pytest
import sqlite3
from beautyspot import Spot
from beautyspot.storage import LocalStorage
from beautyspot.db import SQLiteTaskDB

# tests/typing/ 配下は pyright 専用。pytest での収集を除外する。
collect_ignore_glob = ["typing/*.py"]


@pytest.fixture
def inspect_db():
    """Factory fixture to inspect SQLite DB directly."""

    def _fetch_all(db_path):
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM tasks")
            return [dict(row) for row in cursor.fetchall()]

    return _fetch_all


@pytest.fixture
def spot(tmp_path):
    # DBもBlobも一時ディレクトリに作成
    return Spot(
        name="test_spot",
        db=SQLiteTaskDB(tmp_path / "test.db"),
        storage_backend=LocalStorage(tmp_path / "blobs"),
    )
