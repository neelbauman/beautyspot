# tests/test_core_default.py

import pytest
from beautyspot import Spot

def test_project_defaults_run(tmp_path, inspect_db):
    """Test that project.run() inherits and overrides defaults."""
    db_path = str(tmp_path / "test_defaults.db")
    
    # Init with defaults: save_blob=True, version="v1"
    with Spot(
        name="test_defaults", 
        db=db_path, 
        default_save_blob=True, 
        default_version="v1"
    ) as project:
        
        def my_func(x):
            return x * 2

        # 1. Inherit defaults (save_blob=True, version="v1")
        res = project.run(my_func, 10)
        assert res == 20
        
        # 検証: Helper fixtureを使用してDBを直接確認
        entries = inspect_db(db_path)
        assert len(entries) == 1
        assert entries[0]["version"] == "v1"
        assert entries[0]["result_type"] == "FILE" # FILE implies save_blob=True

        # 2. Override defaults (version="v2")
        res2 = project.run(my_func, 10, _version="v2")
        assert res2 == 20
        
        entries = inspect_db(db_path)
        # Different version -> New entry
        assert len(entries) == 2
        versions = sorted([e["version"] for e in entries])
        assert versions == ["v1", "v2"]

        # 3. Override save_blob (save_blob=False)
        # Note: Use a new version to ensure new entry creation
        res3 = project.run(my_func, 10, _version="v3", _save_blob=False)
        
        entries = inspect_db(db_path)
        v3_entry = next(e for e in entries if e["version"] == "v3")
        assert v3_entry["result_type"] == "DIRECT_BLOB"

def test_project_defaults_decorator(tmp_path, inspect_db):
    """Test that @task inherits and overrides defaults."""
    db_path = str(tmp_path / "test_dec_defaults.db")
    
    # Default: save_blob=True
    project = Spot(name="test_dec", db=db_path, default_save_blob=True)

    # Case 1: Inherit
    @project.mark
    def task_inherit(x):
        return x

    task_inherit(1)
    
    entries = inspect_db(db_path)
    assert len(entries) == 1
    # Check correct function name
    assert entries[0]["func_name"] == "task_inherit"
    # Inherited default_save_blob=True
    assert entries[0]["result_type"] == "FILE"

    # Case 2: Override
    @project.mark(save_blob=False)
    def task_override(x):
        return x

    task_override(1)
    
    entries = inspect_db(db_path)
    # Check the entry for task_override
    entry = next(e for e in entries if e["func_name"] == "task_override")
    assert entry["result_type"] == "DIRECT_BLOB"
