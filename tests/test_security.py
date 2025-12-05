import pytest
import os
import shutil
from beautyspot.storage import LocalStorage

BASE_DIR = "./test_blobs"

@pytest.fixture
def storage():
    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    s = LocalStorage(BASE_DIR)
    yield s
    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)

def test_path_traversal_save(storage):
    """Test that saving with a key containing path traversal characters fails."""
    unsafe_key = "../../../etc/passwd"
    data = b"secret"
    
    with pytest.raises(ValueError, match="Invalid key"):
        storage.save(unsafe_key, data)

def test_path_traversal_key_validation(storage):
    """Test various unsafe keys."""
    unsafe_keys = [
        "../foo",
        "foo/bar",
        "\\foo",
        "foo\\bar"
    ]
    
    for key in unsafe_keys:
        with pytest.raises(ValueError, match="Invalid key"):
            storage.save(key, b"data")

def test_valid_save_load(storage):
    """Test that valid keys still work."""
    key = "valid_key_123"
    data = b"hello world"
    
    path = storage.save(key, data)
    assert os.path.exists(path)
    
    loaded = storage.load(path)
    assert loaded == data

def test_load_outside_base_dir(storage):
    """Test that loading a file outside the base dir fails."""
    # Create a dummy file outside base dir
    outside_file = "outside.txt"
    with open(outside_file, "wb") as f:
        f.write(b"outside")
        
    try:
        abs_path = os.path.abspath(outside_file)
        
        # Try to load it via LocalStorage
        with pytest.raises(ValueError, match="Access denied"):
            storage.load(abs_path)
    finally:
        if os.path.exists(outside_file):
            os.remove(outside_file)
