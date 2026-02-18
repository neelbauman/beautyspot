# tests/integreation/core/test_config.py

from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB


def test_project_defaults_run(tmp_path, inspect_db):
    """Test that project defaults (version, save_blob) are applied to tasks."""
    db_path = str(tmp_path / "test_defaults.db")

    # Init with defaults: save_blob=True, version="v1"
    with Spot(
        name="test_defaults",
        db=SQLiteTaskDB(db_path),
        default_save_blob=True,
        default_version="v1",
    ) as project:

        def my_func(x):
            return x * 2

        with project.cached_run(my_func) as task:
            task(10)

        # 検証
        entries = inspect_db(db_path)
        assert len(entries) == 1

        # デフォルト値が適用されているか確認
        assert entries[0]["version"] == "v1"
        # result_typeがFILEならsave_blob=Trueが効いている
        assert entries[0]["result_type"] == "FILE"


def test_project_defaults_decorator(tmp_path, inspect_db):
    """Test that @task inherits and overrides defaults."""
    db_path = str(tmp_path / "test_dec_defaults.db")

    # Default: save_blob=True
    project = Spot(name="test_dec", db=SQLiteTaskDB(db_path), default_save_blob=True)

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


def test_default_version_applied(tmp_path):
    """Spot初期化時のdefault_versionがタスクに適用されるか確認"""
    # 1. default_version を指定して初期化
    spot = Spot(
        name="version_test",
        db=SQLiteTaskDB(str(tmp_path / "v_test.db")),
        default_version="v1.0",
    )

    @spot.mark
    def my_task(x):
        return x * 2

    # 実行
    my_task(10)

    # 2. 保存されたレコードを確認
    df = spot.db.get_history()
    assert len(df) == 1
    # バグがある場合、ここは None になりアサーションエラーになるはず
    assert df.iloc[0]["version"] == "v1.0"


def test_override_default_version(tmp_path):
    """default_versionがあっても、個別に指定したversionが優先されるか"""
    spot = Spot(
        name="version_override",
        db=SQLiteTaskDB(str(tmp_path / "vo_test.db")),
        default_version="v1.0",
    )

    @spot.mark(version="v2.0-beta")
    def my_task_v2(x):
        return x * 2

    my_task_v2(10)

    df = spot.db.get_history()
    assert df.iloc[0]["version"] == "v2.0-beta"
