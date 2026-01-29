import pytest
from unittest.mock import MagicMock
from beautyspot import Spot


def test_spot_context_manager(tmp_path):
    """Test that spot works as a context manager and calls shutdown on exit."""
    db_path = str(tmp_path / "test.db")

    # Create a spot instance
    spot = Spot(name="test_cm", db=db_path)

    # Mock the shutdown method
    spot.shutdown = MagicMock()

    # Use as context manager
    with spot as p:
        assert p is spot
        # Verify shutdown is NOT called yet
        spot.shutdown.assert_not_called()

    # Verify shutdown IS called after exit
    spot.shutdown.assert_called_once()


def test_spot_context_manager_exception(tmp_path):
    """Test that shutdown is called even if an exception occurs."""
    db_path = str(tmp_path / "test.db")
    spot = Spot(name="test_cm_exc", db=db_path)
    spot.shutdown = MagicMock()

    with pytest.raises(ValueError):
        with spot:
            raise ValueError("Test Exception")

    spot.shutdown.assert_called_once()
