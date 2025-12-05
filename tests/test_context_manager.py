import pytest
from unittest.mock import MagicMock
from beautyspot import Project

def test_project_context_manager(tmp_path):
    """Test that Project works as a context manager and calls shutdown on exit."""
    db_path = str(tmp_path / "test.db")
    
    # Create a project instance
    project = Project(name="test_cm", db=db_path)
    
    # Mock the shutdown method
    project.shutdown = MagicMock()
    
    # Use as context manager
    with project as p:
        assert p is project
        # Verify shutdown is NOT called yet
        project.shutdown.assert_not_called()
        
    # Verify shutdown IS called after exit
    project.shutdown.assert_called_once()

def test_project_context_manager_exception(tmp_path):
    """Test that shutdown is called even if an exception occurs."""
    db_path = str(tmp_path / "test.db")
    project = Project(name="test_cm_exc", db=db_path)
    project.shutdown = MagicMock()
    
    with pytest.raises(ValueError):
        with project:
            raise ValueError("Test Exception")
            
    project.shutdown.assert_called_once()
