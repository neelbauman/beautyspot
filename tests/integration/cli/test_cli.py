# tests/integration/cli/test_cli.py

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from beautyspot.cli import app

runner = CliRunner()


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with test data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)

    # Create schema
    conn.execute("""
        CREATE TABLE tasks (
            cache_key TEXT PRIMARY KEY,
            func_name TEXT,
            input_id TEXT,
            result_type TEXT,
            result_value TEXT,
            result_data BLOB,
            content_type TEXT,
            version TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Insert test data
    conn.execute("""
        INSERT INTO tasks (cache_key, func_name, input_id, result_type, version, updated_at)
        VALUES ('key1', 'my_function', 'input1', 'DIRECT_BLOB', '1.0.0', datetime('now'))
    """)
    conn.execute("""
        INSERT INTO tasks (cache_key, func_name, input_id, result_type, version, updated_at)
        VALUES ('key2', 'other_function', 'input2', 'FILE', '1.0.0', datetime('now', '-60 days'))
    """)
    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def temp_db_with_blobs(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary database with blob files."""
    db_path = tmp_path / "test.db"
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE tasks (
            cache_key TEXT PRIMARY KEY,
            func_name TEXT,
            input_id TEXT,
            result_type TEXT,
            result_value TEXT,
            result_data BLOB,
            content_type TEXT,
            version TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create blob file and reference it
    blob_file = blob_dir / "referenced.bin"
    blob_file.write_bytes(b"test data")

    conn.execute(
        """
        INSERT INTO tasks (cache_key, func_name, input_id, result_type, result_value, updated_at)
        VALUES ('key1', 'my_function', 'input1', 'FILE', ?, datetime('now'))
    """,
        (str(blob_file),),
    )
    conn.commit()
    conn.close()

    # Create orphaned blob file (not referenced in DB)
    orphaned_file = blob_dir / "orphaned.bin"
    orphaned_file.write_bytes(b"orphaned data")

    return db_path, blob_dir


@pytest.fixture
def beautyspot_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create .beautyspot directory and change to tmp_path."""
    beautyspot = tmp_path / ".beautyspot"
    beautyspot.mkdir()

    # Create test database
    db_path = beautyspot / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE tasks (
            cache_key TEXT PRIMARY KEY,
            func_name TEXT,
            input_id TEXT,
            result_type TEXT,
            result_value TEXT,
            result_data BLOB,
            content_type TEXT,
            version TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        INSERT INTO tasks (cache_key, func_name, input_id, result_type, version)
        VALUES ('key1', 'test_func', 'input1', 'DIRECT_BLOB', '1.0.0')
    """)
    conn.commit()
    conn.close()

    # Change working directory
    monkeypatch.chdir(tmp_path)

    return beautyspot


# =============================================================================
# Test: version
# =============================================================================


def test_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "beautyspot" in result.stdout


# =============================================================================
# Test: list
# =============================================================================


def test_list_databases(beautyspot_dir: Path):
    """Test listing databases when no db argument is provided."""
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "test.db" in result.stdout
    assert "Available Databases" in result.stdout


def test_list_databases_no_beautyspot_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Test list command when .beautyspot directory doesn't exist."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0
    assert "No .beautyspot/ directory found" in result.stdout


def test_list_tasks(temp_db: Path):
    """Test listing tasks in a database."""
    result = runner.invoke(app, ["list", str(temp_db)])

    assert result.exit_code == 0
    assert "my_function" in result.stdout
    assert "other_function" in result.stdout


def test_list_tasks_with_filter(temp_db: Path):
    """Test listing tasks with function filter."""
    result = runner.invoke(app, ["list", str(temp_db), "--func", "my_function"])

    assert result.exit_code == 0
    assert "my_function" in result.stdout
    assert "other_function" not in result.stdout


def test_list_tasks_with_limit(temp_db: Path):
    """Test listing tasks with limit."""
    result = runner.invoke(app, ["list", str(temp_db), "--limit", "1"])

    assert result.exit_code == 0
    assert "1 records" in result.stdout


def test_list_db_not_found():
    """Test list command with non-existent database."""
    result = runner.invoke(app, ["list", "/nonexistent/path.db"])

    assert result.exit_code == 1
    assert "Database not found" in result.stdout


# =============================================================================
# Test: show
# =============================================================================


def test_show_task(temp_db: Path):
    """Test showing task details."""
    result = runner.invoke(app, ["show", str(temp_db), "key1"])

    assert result.exit_code == 0
    assert "key1" in result.stdout
    assert "Task Details" in result.stdout


def test_show_task_not_found(temp_db: Path):
    """Test show command with non-existent cache key."""
    result = runner.invoke(app, ["show", str(temp_db), "nonexistent_key"])

    assert result.exit_code == 1
    assert "Cache key not found" in result.stdout


# =============================================================================
# Test: stats
# =============================================================================


def test_stats(temp_db: Path):
    """Test stats command."""
    result = runner.invoke(app, ["stats", str(temp_db)])

    assert result.exit_code == 0
    assert "Overview" in result.stdout
    assert "Total Tasks" in result.stdout


def test_stats_empty_db(tmp_path: Path):
    """Test stats command with empty database."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE tasks (
            cache_key TEXT PRIMARY KEY,
            func_name TEXT,
            input_id TEXT,
            result_type TEXT,
            result_value TEXT,
            result_data BLOB,
            content_type TEXT,
            version TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.close()

    result = runner.invoke(app, ["stats", str(db_path)])

    assert result.exit_code == 0
    assert "No tasks recorded" in result.stdout


# =============================================================================
# Test: clear
# =============================================================================


def test_clear_all_with_force(temp_db: Path):
    """Test clearing all tasks with --force flag."""
    result = runner.invoke(app, ["clear", str(temp_db), "--force"])

    assert result.exit_code == 0
    assert "Deleted" in result.stdout

    # Verify database is empty
    conn = sqlite3.connect(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert count == 0


def test_clear_specific_function(temp_db: Path):
    """Test clearing tasks for a specific function."""
    result = runner.invoke(
        app, ["clear", str(temp_db), "--func", "my_function", "--force"]
    )

    assert result.exit_code == 0
    assert "Deleted" in result.stdout

    # Verify only specified function was deleted
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT func_name FROM tasks").fetchall()
    conn.close()

    func_names = [row[0] for row in rows]
    assert "my_function" not in func_names
    assert "other_function" in func_names


def test_clear_aborted(temp_db: Path):
    """Test clear command when user aborts."""
    result = runner.invoke(app, ["clear", str(temp_db)], input="n\n")

    assert result.exit_code == 0
    assert "Aborted" in result.stdout


# =============================================================================
# Test: clean
# =============================================================================


def test_clean_dry_run(temp_db_with_blobs: tuple[Path, Path]):
    """Test clean command with --dry-run flag."""
    db_path, blob_dir = temp_db_with_blobs

    result = runner.invoke(
        app, ["clean", str(db_path), "--blob-dir", str(blob_dir), "--dry-run"]
    )

    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    assert "orphaned.bin" in result.stdout

    # Verify file was not deleted
    assert (blob_dir / "orphaned.bin").exists()


def test_clean_force(temp_db_with_blobs: tuple[Path, Path]):
    """Test clean command with --force flag."""
    db_path, blob_dir = temp_db_with_blobs

    result = runner.invoke(
        app, ["clean", str(db_path), "--blob-dir", str(blob_dir), "--force"]
    )

    assert result.exit_code == 0
    assert "Deleted" in result.stdout

    # Verify orphaned file was deleted
    assert not (blob_dir / "orphaned.bin").exists()
    # Verify referenced file still exists
    assert (blob_dir / "referenced.bin").exists()


def test_clean_no_orphans(temp_db: Path, tmp_path: Path):
    """Test clean command when there are no orphaned files."""
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir()

    result = runner.invoke(app, ["clean", str(temp_db), "--blob-dir", str(blob_dir)])

    assert result.exit_code == 0
    assert "No orphaned files found" in result.stdout


# =============================================================================
# Test: prune
# =============================================================================


def test_prune_dry_run(temp_db: Path):
    """Test prune command with --dry-run flag."""
    result = runner.invoke(app, ["prune", str(temp_db), "--days", "30", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    # The 60-day old task should be listed
    assert "other_function" in result.stdout


def test_prune_force(temp_db: Path):
    """Test prune command with --force flag."""
    result = runner.invoke(
        app, ["prune", str(temp_db), "--days", "30", "--force", "--no-clean-blobs"]
    )

    assert result.exit_code == 0
    assert "Deleted" in result.stdout

    # Verify old task was deleted
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT func_name FROM tasks").fetchall()
    conn.close()

    func_names = [row[0] for row in rows]
    assert "other_function" not in func_names  # 60 days old, should be deleted
    assert "my_function" in func_names  # recent, should remain


def test_prune_specific_function(temp_db: Path):
    """Test prune command for a specific function."""
    result = runner.invoke(
        app,
        [
            "prune",
            str(temp_db),
            "--days",
            "30",
            "--func",
            "other_function",
            "--force",
            "--no-clean-blobs",
        ],
    )

    assert result.exit_code == 0
    assert "Deleted" in result.stdout


def test_prune_no_old_tasks(temp_db: Path):
    """Test prune command when there are no old tasks."""
    result = runner.invoke(
        app,
        [
            "prune",
            str(temp_db),
            "--days",
            "365",  # Nothing older than 365 days
        ],
    )

    assert result.exit_code == 0
    assert "No tasks older than" in result.stdout


def test_prune_invalid_days(temp_db: Path):
    """Test prune command with invalid days value."""
    result = runner.invoke(app, ["prune", str(temp_db), "--days", "0"])

    assert result.exit_code == 1
    assert "--days must be at least 1" in result.stdout


# =============================================================================
# Test: ui
# =============================================================================


def test_ui_db_not_found():
    """Test ui command with non-existent database."""
    result = runner.invoke(app, ["ui", "/nonexistent/path.db"])

    assert result.exit_code == 1
    assert "Database not found" in result.stdout


@patch("beautyspot.cli.subprocess.run")
@patch("beautyspot.cli._is_port_in_use", return_value=False)
def test_ui_success(mock_port_check: MagicMock, mock_run: MagicMock, temp_db: Path):
    """Test ui command successful launch."""
    mock_run.return_value = None

    result = runner.invoke(app, ["ui", str(temp_db)])

    assert result.exit_code == 0
    assert "Starting beautyspot Dashboard" in result.stdout
    mock_run.assert_called_once()


@patch("beautyspot.cli._is_port_in_use", side_effect=[True, False])
@patch("beautyspot.cli.subprocess.run")
def test_ui_port_in_use_auto_switch(
    mock_run: MagicMock, mock_port_check: MagicMock, temp_db: Path
):
    """Test ui command auto-switches port when default is in use."""
    result = runner.invoke(app, ["ui", str(temp_db)])

    assert result.exit_code == 0
    assert "Port 8501 is in use" in result.stdout
    assert "8502" in result.stdout


@patch("beautyspot.cli._is_port_in_use", return_value=True)
def test_ui_port_in_use_no_auto(mock_port_check: MagicMock, temp_db: Path):
    """Test ui command fails when port is in use and auto-port is disabled."""
    result = runner.invoke(app, ["ui", str(temp_db), "--no-auto-port"])

    assert result.exit_code == 1
    assert "already in use" in result.stdout


# =============================================================================
# Test: Helper Functions
# =============================================================================


def test_format_size():
    """Test _format_size helper function."""
    from beautyspot.cli import _format_size

    assert _format_size(500) == "500.0 B"
    assert _format_size(1024) == "1.0 KB"
    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(1024 * 1024 * 1024) == "1.0 GB"


def test_format_timestamp():
    """Test _format_timestamp helper function."""
    from beautyspot.cli import _format_timestamp

    # Test with a known timestamp
    timestamp = datetime(2025, 1, 15, 10, 30).timestamp()
    result = _format_timestamp(timestamp)

    assert "2025-01-15" in result
    assert "10:30" in result

    # tests/integration/cli/test_cli.py

# ... (既存のテストコード)

# =============================================================================
# Test: gc (Garbage Collection for Zombie Projects)
# =============================================================================

@pytest.fixture
def workspace_with_zombies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Create a workspace with:
    1. Active project (DB + Blobs) -> Should be KEPT
    2. Zombie project (Blobs only, no DB) -> Should be DELETED
    """
    beautyspot = tmp_path / ".beautyspot"
    beautyspot.mkdir()
    blobs_root = beautyspot / "blobs"
    blobs_root.mkdir()

    # 1. Active Project
    active_db = beautyspot / "active.db"
    active_db.touch()
    active_blobs = blobs_root / "active"
    active_blobs.mkdir()
    (active_blobs / "data.bin").write_bytes(b"important data")

    # 2. Zombie Project
    zombie_blobs = blobs_root / "zombie"
    zombie_blobs.mkdir()
    (zombie_blobs / "ghost.bin").write_bytes(b"scary data")

    # Change working directory to tmp_path so CLI looks at .beautyspot
    monkeypatch.chdir(tmp_path)

    return beautyspot


def test_gc_dry_run(workspace_with_zombies: Path):
    """Test gc command with dry-run."""
    result = runner.invoke(app, ["gc", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    assert "zombie" in result.stdout

    # Verify nothing was deleted
    blobs_root = workspace_with_zombies / "blobs"
    assert (blobs_root / "zombie").exists()
    assert (blobs_root / "active").exists()


def test_gc_force(workspace_with_zombies: Path):
    """Test gc command execution."""
    result = runner.invoke(app, ["gc", "--force"])

    assert result.exit_code == 0
    assert "Cleaned up 1 orphan projects" in result.stdout

    blobs_root = workspace_with_zombies / "blobs"
    
    # Zombie should be gone
    assert not (blobs_root / "zombie").exists()
    
    # Active should remain
    assert (blobs_root / "active").exists()
    assert (blobs_root / "active" / "data.bin").exists()


def test_gc_no_orphans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test gc when everything is clean."""
    beautyspot = tmp_path / ".beautyspot"
    beautyspot.mkdir()
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["gc"])

    assert result.exit_code == 0
    assert "No orphan storage directories found" in result.stdout


# =============================================================================
# Test: Prune vs Clean Interaction
# =============================================================================

def test_prune_without_clean(temp_db_with_blobs: tuple[Path, Path]):
    """
    Test pruning tasks BUT keeping the files (--no-clean-blobs).
    This clarifies the distinction: Prune deletes DB rows, Clean deletes files.
    """
    db_path, blob_dir = temp_db_with_blobs
    
    # Manually update the timestamp of the task to be old
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE tasks SET updated_at = datetime('now', '-100 days') WHERE cache_key = 'key1'"
    )
    conn.commit()
    conn.close()

    # Run Prune with --no-clean-blobs
    result = runner.invoke(
        app, 
        ["prune", str(db_path), "--days", "30", "--no-clean-blobs", "--force"]
    )

    assert result.exit_code == 0
    
    # 1. Task record should be gone
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    conn.close()
    assert count == 0

    # 2. Blob file should STILL exist (because we skipped clean)
    assert (blob_dir / "referenced.bin").exists()

    # 3. Now run Clean
    result_clean = runner.invoke(
        app, ["clean", str(db_path), "--blob-dir", str(blob_dir), "--force"]
    )
    assert result_clean.exit_code == 0
    
    # 4. Blob file should NOW be gone
    assert not (blob_dir / "referenced.bin").exists()

