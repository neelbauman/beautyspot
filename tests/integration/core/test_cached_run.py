# tests/cached_run.py

import pytest
from beautyspot import Spot


@pytest.fixture
def spot(tmp_path):
    """Temporary Spot instance for testing."""
    db_path = str(tmp_path / "test_cached_run.db")
    return Spot(name="test_runner", db=db_path)


def test_cached_run_single_function(spot):
    """
    Test the 'Smart Return Policy' for a single function.
    It should return the wrapper directly, not a tuple.
    """
    call_count = 0

    def adder(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # Case 1: Single function passed -> Returns single wrapper
    with spot.cached_run(adder) as task:
        # 1st run: Execution
        assert task(10, 20) == 30
        assert call_count == 1

        # 2nd run: Cache Hit
        assert task(10, 20) == 30
        assert call_count == 1  # Count should not increase

    # Verify context exit doesn't kill the spot
    # (Checking if spot is still usable)
    assert spot.db is not None


def test_cached_run_multiple_functions(spot):
    """
    Test unpacking behavior when multiple functions are passed.
    """
    calls_a = 0
    calls_b = 0

    def func_a(x):
        nonlocal calls_a
        calls_a += 1
        return x * 2

    def func_b(x):
        nonlocal calls_b
        calls_b += 1
        return x + 100

    # Case 2: Multiple functions passed -> Returns tuple
    with spot.cached_run(func_a, func_b) as (task_a, task_b):
        assert task_a(5) == 10
        assert task_b(5) == 105

        # Check caching individually
        assert task_a(5) == 10
        assert calls_a == 1
        assert calls_b == 1


def test_cached_run_options_applied(spot):
    """
    Verify that options (version, save_blob) are applied to the wrapper.
    """
    call_count = 0

    def sensitive_task(data):
        nonlocal call_count
        call_count += 1
        return data

    # Apply version="v2"
    with spot.cached_run(sensitive_task, version="v2") as task:
        task("test")

    assert call_count == 1

    # Verify in DB that version is recorded
    # (Assuming internal DB structure, or checking cache miss with different version)

    # Same input, different version -> Should be a cache miss (call_count increases)
    with spot.cached_run(sensitive_task, version="v3") as task_v3:
        task_v3("test")

    assert call_count == 2


def test_run_deprecation_warning(spot):
    """
    Ensure spot.run() raises a DeprecationWarning.
    """

    def old_style_func(x):
        return x

    with pytest.warns(DeprecationWarning, match="cached_run"):
        res = spot.run(old_style_func, 10)
        assert res == 10


def test_cached_run_input_validation(spot):
    """
    Should raise ValueError if no functions are provided.
    """
    with pytest.raises(ValueError, match="At least one function"):
        with spot.cached_run():
            pass


def test_cached_run_strict_scoping(spot):
    """
    Verify that the cached function raises RuntimeError when called outside the 'with' block.
    """
    captured_task = None

    def simple_task(x):
        return x + 1

    # 1. Inside block: Should work normally
    with spot.cached_run(simple_task) as task:
        captured_task = task
        assert task(10) == 11

    # 2. Outside block: Should raise RuntimeError
    # The variable 'task' still exists, but the guard should prevent execution.
    with pytest.raises(
        RuntimeError, match="called outside of its 'cached_run' context"
    ):
        captured_task(10)


@pytest.mark.asyncio
async def test_cached_run_strict_scoping_async(spot):
    """
    Verify strict scoping for async functions.
    """
    captured_task = None

    async def async_task(x):
        return x * 2

    # 1. Inside block
    with spot.cached_run(async_task) as task:
        captured_task = task
        res = await task(5)
        assert res == 10

    # 2. Outside block
    with pytest.raises(
        RuntimeError, match="called outside of its 'cached_run' context"
    ):
        await captured_task(5)
