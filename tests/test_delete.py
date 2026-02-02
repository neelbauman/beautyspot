import os
from beautyspot import Spot

def test_delete_hit(tmp_path):
    """
    正常系: DBレコードとBlobファイルの両方が削除されることを確認
    """
    db_path = tmp_path / "test.db"
    storage_path = tmp_path / "blobs"
    
    spot = Spot("test_spot", db=str(db_path), storage_path=str(storage_path))

    # 1. データを作成 (Blob保存あり)
    @spot.mark(save_blob=True)
    def heavy_func(x):
        return {"data": "x" * 100}

    heavy_func(1)
    
    # DBとファイルが作成されたか確認
    df = spot.db.get_history()
    assert len(df) == 1
    cache_key = df.iloc[0]["cache_key"]
    blob_path = df.iloc[0]["result_value"]
    
    assert os.path.exists(blob_path)

    # 2. 削除実行
    deleted = spot.delete(cache_key)
    
    # 3. 検証
    assert deleted is True
    
    # DBから消えているか
    assert spot.db.get(cache_key) is None
    
    # ファイルが消えているか
    assert not os.path.exists(blob_path)

def test_delete_miss(tmp_path):
    """
    異常系: 存在しないキーを指定した場合
    """
    db_path = tmp_path / "test.db"
    spot = Spot("test_spot", db=str(db_path))
    
    assert spot.delete("non_existent_key") is False

def test_delete_db_only(tmp_path):
    """
    正常系: Blobを持たない（SQLite内にデータを保存した）タスクの削除
    """
    db_path = tmp_path / "test.db"
    spot = Spot("test_spot", db=str(db_path))

    @spot.mark(save_blob=False)
    def light_func(x):
        return x * 2

    light_func(10)
    
    df = spot.db.get_history()
    cache_key = df.iloc[0]["cache_key"]
    
    # 削除実行
    deleted = spot.delete(cache_key)
    
    assert deleted is True
    assert spot.db.get(cache_key) is None

def test_delete_orphaned_blob_record(tmp_path):
    """
    準正常系: DB上はファイルがあることになっているが、実ファイルが既に消されている場合
    -> エラーにならず、DBレコードを削除してTrueを返すべき
    """
    db_path = tmp_path / "test.db"
    storage_path = tmp_path / "blobs"
    spot = Spot("test_spot", db=str(db_path), storage_path=str(storage_path))

    @spot.mark(save_blob=True)
    def func(x):
        return x

    func(1)
    
    df = spot.db.get_history()
    cache_key = df.iloc[0]["cache_key"]
    blob_path = df.iloc[0]["result_value"]

    # 意地悪くファイルを裏で消す
    os.remove(blob_path)
    assert not os.path.exists(blob_path)

    # 削除実行 (エラーにならないこと)
    deleted = spot.delete(cache_key)
    
    assert deleted is True
    assert spot.db.get(cache_key) is None

