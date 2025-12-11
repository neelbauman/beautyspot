# tests/test_db.py

import pytest
from beautyspot.db import SQLiteTaskDB


@pytest.fixture
def db(tmp_path):
    # 修正: :memory: ではなく、一時ファイルを使用する
    # これにより、接続を切ってもデータが維持される
    db_path = tmp_path / "test_tasks.db"
    task_db = SQLiteTaskDB(str(db_path))
    task_db.init_schema()
    return task_db


def test_init_schema(db):
    """スキーマが正しく初期化されているか"""
    with db._connect() as conn:
        # テーブルが存在するか確認
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks';"
        )
        assert cursor.fetchone() is not None

        # カラムが存在するか確認 (マイグレーション含む)
        cursor = conn.execute("PRAGMA table_info(tasks)")
        columns = [row[1] for row in cursor.fetchall()]
        assert "content_type" in columns
        assert "version" in columns


def test_save_and_get(db):
    """データの保存と取得"""
    key = "test_key_123"
    db.save(
        cache_key=key,
        func_name="my_func",
        input_id="input_1",
        version="v1",
        result_type="DIRECT",
        content_type="text/plain",
        result_value='"hello"',
    )

    result = db.get(key)
    assert result is not None
    assert result["result_type"] == "DIRECT"
    assert result["result_value"] == '"hello"'


def test_get_non_existent(db):
    """存在しないキーの取得"""
    assert db.get("missing_key") is None


def test_get_history(db):
    """履歴の取得 (Pandas)"""
    # データを投入
    db.save("k1", "f1", "i1", "v1", "DIRECT", "text", '"v1"')
    db.save("k2", "f1", "i2", "v1", "DIRECT", "text", '"v2"')

    df = db.get_history()
    assert len(df) == 2
    assert "cache_key" in df.columns
    # 新しい順に並んでいるか
    assert set(df["cache_key"]) == {"k1", "k2"}
