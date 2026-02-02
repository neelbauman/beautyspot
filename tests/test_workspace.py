# tests/test_workspace.py
import os
from pathlib import Path
from beautyspot import Spot


def test_workspace_creation(tmp_path):
    """Test that .beautyspot directory and .gitignore are created."""
    # Change CWD to tmp_path to test relative path creation
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        project_name = "test_ws"
        # Init project without explicit db/storage paths
        # This should trigger default workspace creation
        with Spot(name=project_name):
            pass

        ws_dir = Path(".beautyspot")

        # 1. Directory exists
        assert ws_dir.exists()
        assert ws_dir.is_dir()

        # 2. .gitignore exists and contains '*'
        gitignore = ws_dir / ".gitignore"
        assert gitignore.exists()
        assert gitignore.read_text().strip() == "*"

        # 3. DB is created inside workspace
        db_file = ws_dir / f"{project_name}.db"
        assert db_file.exists()

        # 4. Storage dir is created inside workspace
        blob_dir = ws_dir / "blobs"
        assert blob_dir.exists()

    finally:
        os.chdir(cwd)


def test_custom_paths_ignore_workspace(tmp_path):
    """Test that explicit paths do NOT use the workspace dir."""
    custom_db = tmp_path / "custom.db"
    custom_blobs = tmp_path / "custom_blobs"

    # Explicitly providing paths should bypass default workspace locations
    with Spot(name="custom", db=str(custom_db), storage_path=str(custom_blobs)):
        pass

    # Files should be at custom locations
    assert custom_db.exists()
    assert custom_blobs.exists()

    # Workspace might still be created (as setup runs in init), but it shouldn't contain our files
    assert Path(".beautyspot").exists()
    assert not (Path(".beautyspot") / "custom.db").exists()
