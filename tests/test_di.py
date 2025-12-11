import pytest
from concurrent.futures import ThreadPoolExecutor
from beautyspot import Project
from beautyspot.storage import BlobStorageBase
from beautyspot.db import TaskDB

class MockStorage(BlobStorageBase):
    def __init__(self):
        self.data = {}
        
    def save(self, key: str, data: bytes) -> str:
        self.data[key] = data
        return f"mock://{key}"
        
    def load(self, location: str) -> bytes:
        key = location.replace("mock://", "")
        if key not in self.data:
            raise FileNotFoundError(key)
        return self.data[key]

class MockDB(TaskDB):
    def __init__(self):
        self.store = {}
        
    def init_schema(self):
        pass
        
    def get(self, cache_key: str):
        return self.store.get(cache_key)
        
    def save(self, cache_key, func_name, input_id, version, result_type, content_type, result_value):
        self.store[cache_key] = {
            "func_name": func_name,
            "result_value": result_value,
            "result_type": result_type
        }
        
    def get_history(self, limit=1000):
        import pandas as pd
        return pd.DataFrame(list(self.store.values()))

def test_custom_storage_injection(tmp_path):
    """Test injecting a custom storage backend."""
    storage = MockStorage()
    project = Project(name="di_test", db=str(tmp_path / "test.db"), storage=storage)
    
    @project.task(save_blob=True)
    def blob_task():
        return "blob_data"
        
    res = blob_task()
    assert res == "blob_data"
    
    # Verify data ended up in our mock storage
    assert len(storage.data) == 1
    # Key is md5 hash, so we just check if any key exists
    key = list(storage.data.keys())[0]
    assert b"blob_data" in storage.data[key] # msgpack serialized string might contain the string itself


def test_custom_db_injection(tmp_path):
    """Test injecting a custom DB backend."""
    db = MockDB()
    project = Project(name="di_test", db=db, storage_path=str(tmp_path / "blobs"))
    
    @project.task
    def simple_task():
        return 123
        
    res = simple_task()
    assert res == 123
    
    # Verify metadata ended up in our mock DB
    assert len(db.store) == 1
    key = list(db.store.keys())[0]
    assert db.store[key]["result_value"] == "123"


def test_custom_executor_injection(tmp_path):
    """Test injecting a custom executor."""
    # Use a single worker to ensure sequential execution (though hard to prove without timing)
    executor = ThreadPoolExecutor(max_workers=1)
    project = Project(
        name="di_test", 
        db=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs"),
        executor=executor
    )
    
    @project.task
    def task_a(): return "A"
    
    assert task_a() == "A"
    
    # Executor should remain open after project shutdown if injected?
    # The current implementation says:
    # if executor is not None: ... self._own_executor = False
    # so project.shutdown() should NOT shut it down.
    
    project.shutdown()
    
    # Verify executor is still usable
    f = executor.submit(lambda: "still_alive")
    assert f.result() == "still_alive"
    
    executor.shutdown()
