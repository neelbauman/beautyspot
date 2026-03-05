import logging
from beautyspot import Spot, SQLiteTaskDB


def test_check_cache_sync_unknown_result_type(tmp_path, caplog):
    """MINOR-1: 未知の result_type を検知して警告を出し、CACHE_MISS を返すこと"""
    db_path = tmp_path / "test.db"
    spot = Spot("test_minor1", db=SQLiteTaskDB(db_path))

    # DBに直接未知のタイプを書き込む
    def inject_data(conn):
        conn.execute(
            "INSERT INTO tasks (cache_key, result_type, version) VALUES (?, ?, ?)",
            ("unknown_key", "GHOST_TYPE", "1.0"),
        )

    spot.cache.db._enqueue_write(inject_data)

    with caplog.at_level(logging.WARNING):
        # 内部メソッドを直接呼んでチェック
        from beautyspot.cache import CACHE_MISS

        res = spot.cache.get("unknown_key")
        assert res is CACHE_MISS

        assert "Unknown result_type 'GHOST_TYPE'" in caplog.text
