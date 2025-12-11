# tests/test_edge_cases.py

import pytest
from unittest.mock import MagicMock
from beautyspot import Project
from beautyspot.storage import LocalStorage


def test_path_traversal_prevention(tmp_path):
    """Test that LocalStorage prevents path traversal attacks."""
    storage = LocalStorage(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid key"):
        storage.save("../malicious", b"data")

    with pytest.raises(ValueError, match="Invalid key"):
        storage.save("subdir/malicious", b"data")


def test_storage_failure_handling(tmp_path):
    """Test that Project handles storage failures gracefully (or raises as expected)."""
    # In the current implementation, Project doesn't catch storage errors during save,
    # so we expect it to propagate. This test documents that behavior.

    project = Project(
        name="test_proj",
        db=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs"),
    )

    # Mock storage.save to fail
    project.storage.save = MagicMock(side_effect=PermissionError("Disk full"))

    @project.task(save_blob=True)
    def my_task():
        return "data"

    with pytest.raises(PermissionError):
        my_task()


def test_db_failure_handling(tmp_path):
    """Test behavior when DB fails."""
    project = Project(name="test_proj", db=str(tmp_path / "test.db"))

    # Mock db.save to fail
    project.db.save = MagicMock(side_effect=Exception("DB Connection Lost"))

    @project.task
    def my_task():
        return "data"

    # Currently expected to propagate
    with pytest.raises(Exception, match="DB Connection Lost"):
        my_task()


def test_invalid_json_serialization(tmp_path):
    """Test behavior when unserializable object is returned."""
    from beautyspot.serializer import SerializationError

    project = Project(name="test_proj", db=str(tmp_path / "test.db"))

    class Unserializable:
        pass

    @project.task(save_blob=False)
    def bad_task():
        return Unserializable()

    with pytest.raises(SerializationError):
        bad_task()
