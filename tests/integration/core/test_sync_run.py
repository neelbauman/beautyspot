# tests/test_core_run.py

import asyncio
from beautyspot import Spot


def test_project_run_sync_in_context(tmp_path):
    """Test explicit run within a context manager."""
    # workspace機能により .beautyspot/test_run.db が作られる想定
    project = Spot(name="test_run", db=str(tmp_path / "test_run.db"))

    call_count = 0

    def add(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # Recommended usage: with statement
    with project:
        # First run: Should execute
        res1 = project.run(add, 1, 2)
        assert res1 == 3
        assert call_count == 1

        # Second run: Should use cache
        res2 = project.run(add, 1, 2)
        assert res2 == 3
        assert call_count == 1

        # Different args: Should execute
        res3 = project.run(add, 2, 3)
        assert res3 == 5
        assert call_count == 2


def test_project_run_async_in_context(tmp_path):
    """Test explicit run with asynchronous function in context."""
    project = Spot(name="test_run_async", db=str(tmp_path / "test_run_async.db"))

    call_count = 0

    async def async_mul(a, b):
        nonlocal call_count
        call_count += 1
        return a * b

    async def main():
        # Recommended usage for async
        with project:
            # First run
            res1 = await project.run(async_mul, 3, 4)
            assert res1 == 12
            assert call_count == 1

            # Second run (Cached)
            res2 = await project.run(async_mul, 3, 4)
            assert res2 == 12
            assert call_count == 1

    asyncio.run(main())


def test_project_run_with_options(tmp_path, inspect_db):
    """Test project.run with configuration options (_save_blob, etc)."""

    def heavy_data(size):
        return b"0" * size

    # Using with block ensures cleanup
    with Spot(name="test_opts", db=str(tmp_path / "test_opts.db")) as project:
        # Run with save_blob=True
        # Note: args are passed as *args, options as named args starting with _
        data = project.run(heavy_data, 1024, _save_blob=True)
        assert len(data) == 1024

        # Verify it was saved as FILE (blob) in DB
        entries = inspect_db(tmp_path / "test_opts.db")
        assert len(entries) == 1
        assert entries[0]["result_type"] == "FILE"
