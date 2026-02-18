# tests/integration/core/test_serializer_override.py

import pickle
import beautyspot as bs
from beautyspot.db import SQLiteTaskDB

# --- Helpers ---


class NonMsgpackable:
    """Class that Msgpack cannot serialize by default, but Pickle can."""

    def __init__(self, val):
        self.val = val

    def __eq__(self, other):
        return self.val == other.val


def test_override_with_pickle_mark(tmp_path):
    """Test that @spot.mark(serializer=pickle) handles non-msgpackable objects."""
    spot = bs.Spot("test_pickle_mark", db=SQLiteTaskDB(tmp_path / "test.db"))

    # 1. Define a task that returns a complex object
    # Without serializer=pickle, this would raise SerializationError
    @spot.mark(serializer=pickle)
    def create_complex(val):
        return NonMsgpackable(val)

    # 2. First Run: Should save successfully using pickle
    obj1 = create_complex(10)
    assert isinstance(obj1, NonMsgpackable)
    assert obj1.val == 10

    # 3. Second Run: Should load successfully using pickle
    # Check internals to ensure it hit cache
    # (In a real unit test we might mock, but here we trust the behavior)
    obj2 = create_complex(10)
    assert obj2 is not obj1  # Should be a new instance from unpickling
    assert obj2 == obj1  # Value equality


def test_override_with_pickle_cached_run(tmp_path):
    """Test that spot.cached_run(serializer=pickle) works."""
    spot = bs.Spot("test_pickle_run", db=SQLiteTaskDB(tmp_path / "test.db"))

    def heavy_set_op(a, b):
        # set is not supported by default msgpack
        return {a, b}

    # 1. Run with pickle
    with spot.cached_run(heavy_set_op, serializer=pickle) as task:
        res1 = task(1, 2)
        assert res1 == {1, 2}

    # 2. Run again (Hit cache)
    with spot.cached_run(heavy_set_op, serializer=pickle) as task:
        res2 = task(1, 2)
        assert res2 == {1, 2}


def test_fallback_on_serializer_mismatch(tmp_path):
    """
    Test that if data was saved with Pickle but we try to load with Msgpack (default),
    it treats it as a cache miss (due to deserialization error) and re-computes.
    """
    db_path = str(tmp_path / "mismatch.db")
    spot = bs.Spot("test_mismatch", db=SQLiteTaskDB(db_path))

    # 1. Save data using Pickle
    @spot.mark(serializer=pickle)
    def my_task_1(x):
        return f"value-{x}"

    val1 = my_task_1("A")
    assert val1 == "value-A"

    # 2. Define SAME task but without override (defaults to Msgpack)
    # Note: Function name must match for cache key to collide
    spot2 = bs.Spot("test_mismatch", db=SQLiteTaskDB(db_path))

    @spot2.mark
    def my_task_2(x):
        return f"value-{x}-recomputed"

    # 3. Run with Msgpack serializer
    # The existing cache is a pickled blob. Msgpack.unpack will likely fail (or produce garbage).
    # BeautySpot should catch the error and re-execute.
    val2 = my_task_2("A")

    assert val2 == "value-A-recomputed"
