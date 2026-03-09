# tests/integration/storage/test_blob_storage_base.py

"""BlobStorageBase 抽象インターフェース契約の検証テスト。

LocalStorage を具象実装として使い、SPEC024 で定義された
save / load / delete / list_keys / get_mtime の振る舞いを検証する。
"""

import time

import pytest

from beautyspot.exceptions import CacheCorruptedError
from beautyspot.storage import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "blobs")


# --- save ---


class TestSave:
    def test_returns_location_identifier(self, storage):
        """save はデータを永続化し、一意な識別子（文字列）を返す。"""
        location = storage.save("key1", b"hello")
        assert isinstance(location, str)
        assert len(location) > 0

    def test_accepts_bytes(self, storage):
        """bytes データを保存・復元できる。"""
        data = b"\x00\x01\x02\xff"
        location = storage.save("bin_key", data)
        assert storage.load(location) == data

    def test_accepts_memoryview(self, storage):
        """ReadableBuffer として memoryview を受け入れる（ゼロコピー書き込み）。"""
        original = b"memoryview data"
        mv = memoryview(original)
        location = storage.save("mv_key", mv)
        assert storage.load(location) == original

    def test_accepts_bytearray(self, storage):
        """ReadableBuffer として bytearray を受け入れる。"""
        data = bytearray(b"bytearray data")
        location = storage.save("ba_key", data)
        assert storage.load(location) == bytes(data)

    def test_overwrite_existing_key(self, storage):
        """同じキーに再保存すると上書きされる。"""
        storage.save("dup", b"first")
        location = storage.save("dup", b"second")
        assert storage.load(location) == b"second"

    def test_empty_data(self, storage):
        """空バイトデータも保存できる。"""
        location = storage.save("empty", b"")
        assert storage.load(location) == b""


# --- load ---


class TestLoad:
    def test_roundtrip(self, storage):
        """save した内容を load で復元できる。"""
        data = b"roundtrip test"
        location = storage.save("rt", data)
        assert storage.load(location) == data

    def test_missing_raises_cache_corrupted(self, storage):
        """存在しないロケーションの load は CacheCorruptedError を送出する。"""
        with pytest.raises(CacheCorruptedError):
            storage.load("nonexistent.bin")


# --- delete ---


class TestDelete:
    def test_delete_existing(self, storage):
        """delete は保存済みデータを削除する。"""
        location = storage.save("del_key", b"data")
        storage.delete(location)
        with pytest.raises(CacheCorruptedError):
            storage.load(location)

    def test_delete_nonexistent_is_idempotent(self, storage):
        """存在しないロケーションの delete はエラーを出さない（冪等）。"""
        storage.delete("nonexistent.bin")  # should not raise

    def test_delete_twice_is_idempotent(self, storage):
        """同じロケーションを2回 delete してもエラーにならない。"""
        location = storage.save("d2", b"data")
        storage.delete(location)
        storage.delete(location)  # should not raise


# --- list_keys ---


class TestListKeys:
    def test_empty_storage(self, storage):
        """保存データがなければ空のイテレータを返す。"""
        assert list(storage.list_keys()) == []

    def test_lists_saved_items(self, storage):
        """save したアイテムが list_keys に含まれる。"""
        loc1 = storage.save("a", b"1")
        loc2 = storage.save("b", b"2")
        keys = list(storage.list_keys())
        assert loc1 in keys
        assert loc2 in keys

    def test_deleted_item_not_listed(self, storage):
        """delete 後は list_keys に含まれない。"""
        location = storage.save("rm", b"data")
        storage.delete(location)
        assert location not in list(storage.list_keys())


# --- get_mtime ---


class TestGetMtime:
    def test_returns_posix_timestamp(self, storage):
        """get_mtime は POSIX タイムスタンプ（float）を返す。"""
        location = storage.save("mt", b"data")
        mtime = storage.get_mtime(location)
        assert isinstance(mtime, float)
        # 最近保存したので、現在時刻と大きく乖離しないこと
        assert abs(time.time() - mtime) < 10

    def test_missing_raises_error(self, storage):
        """存在しないロケーションの get_mtime はエラーを送出する。"""
        with pytest.raises((CacheCorruptedError, ValueError)):
            storage.get_mtime("nonexistent.bin")
