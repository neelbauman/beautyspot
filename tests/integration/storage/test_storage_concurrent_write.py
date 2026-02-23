# tests/integration/storage/test_storage_concurrent_write.py

"""LocalStorage の並行書き込みテスト (tempfile.mkstemp 対応)。"""

import threading
from beautyspot.storage import LocalStorage


def test_concurrent_writes_no_corruption(tmp_path):
    """複数スレッドから同時に save() しても、データ破損が起きないことを確認する。"""
    storage = LocalStorage(tmp_path / "blobs")
    num_threads = 10
    errors: list[Exception] = []

    def write_blob(thread_id: int):
        try:
            key = f"key_{thread_id}"
            data = f"data_{thread_id}".encode()
            location = storage.save(key, data)
            loaded = storage.load(location)
            assert loaded == data, f"Thread {thread_id}: data mismatch"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_blob, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent writes: {errors}"


def test_concurrent_writes_same_key(tmp_path):
    """同じキーに対する並行書き込みが最終的に有効なデータを残すことを確認する。"""
    storage = LocalStorage(tmp_path / "blobs")
    num_threads = 10
    errors: list[Exception] = []

    def write_same_key(thread_id: int):
        try:
            data = f"data_{thread_id}".encode()
            storage.save("shared_key", data)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_same_key, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent writes: {errors}"

    # 最終的にファイルは読み込み可能
    result = storage.load("shared_key.bin")
    assert result.startswith(b"data_")


def test_no_leftover_temp_files(tmp_path):
    """保存後に .tmp ファイルが残っていないことを確認する。"""
    storage = LocalStorage(tmp_path / "blobs")
    storage.save("clean_key", b"clean_data")

    tmp_files = list((tmp_path / "blobs").glob("*.tmp"))
    assert len(tmp_files) == 0, f"Leftover temp files: {tmp_files}"
