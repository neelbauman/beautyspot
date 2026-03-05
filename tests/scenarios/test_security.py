# tests/scenarios/test_security.py

import pytest
from beautyspot.storage import LocalStorage
from beautyspot.exceptions import ValidationError


@pytest.fixture
def storage(tmp_path):
    s = LocalStorage(str(tmp_path / "blobs"))
    return s


def test_path_traversal_save(storage):
    """Test that saving with a key containing path traversal characters fails."""
    unsafe_key = "../../../etc/passwd"
    data = b"secret"

    # Bug Fix (Bug10): ValueError ではなく ValidationError を明示的に期待する。
    # ValidationError は ValueError のサブクラスだが、将来の継承関係変更に対して堅牢にする。
    with pytest.raises(ValidationError, match="Invalid key"):
        storage.save(unsafe_key, data)


def test_path_traversal_key_validation(storage):
    """Test various unsafe keys."""
    unsafe_keys = ["../foo", "foo/bar", "\\foo", "foo\\bar"]

    for key in unsafe_keys:
        with pytest.raises(ValidationError, match="Invalid key"):
            storage.save(key, b"data")


def test_valid_save_load(storage):
    """Test that valid keys still work."""
    key = "valid_key_123"
    data = b"hello world"

    # v2.5.0 change: save() returns filename (relative path), not absolute path
    filename = storage.save(key, data)

    # 検証: base_dir と結合してファイルの存在を確認
    # storage.base_dir は pathlib.Path オブジェクトです
    full_path = storage.base_dir / filename
    assert full_path.exists()

    # load() はファイル名（相対パス）を受け取って正しく解決できるはず
    loaded = storage.load(filename)
    assert loaded == data


def test_load_outside_base_dir(storage, tmp_path):
    """Test that loading a file outside the base dir fails."""
    # Create a dummy file outside base dir (in parent of tmp_path)
    outside_file = tmp_path.parent / "outside.txt"
    outside_file.write_bytes(b"outside")

    try:
        abs_path = str(outside_file.absolute())

        # Try to load it via LocalStorage
        from beautyspot.exceptions import CacheCorruptedError

        with pytest.raises(CacheCorruptedError, match="Access denied"):
            storage.load(abs_path)
    finally:
        if outside_file.exists():
            outside_file.unlink()
