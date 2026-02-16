# src/beautyspot/maintenance.py

import logging
from datetime import datetime, timedelta
from typing import Optional

from beautyspot.db import TaskDB
from beautyspot.storage import BlobStorageBase

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class MaintenanceService:
    """
    Service layer for administrative tasks like pruning old cache entries
    and garbage collecting orphaned blob files.
    """

    def __init__(self, db: TaskDB, storage: BlobStorageBase):
        self.db = db
        self.storage = storage

    def get_prunable_tasks(self, days: int, func_name: Optional[str] = None) -> list[tuple[str, str, str]]:
        """
        Preview tasks that would be deleted by prune.
        """
        cutoff = datetime.now() - timedelta(days=days)
        return self.db.get_outdated_tasks(cutoff, func_name)

    def prune(self, days: int, func_name: Optional[str] = None) -> int:
        """
        Delete tasks older than N days.
        """
        cutoff = datetime.now() - timedelta(days=days)
        logger.info(f"Pruning tasks older than {cutoff} (func={func_name})...")
        count = self.db.prune(cutoff, func_name)
        logger.info(f"Deleted {count} tasks.")
        return count
        
    def clear(self, func_name: Optional[str] = None) -> int:
        """
        Clear ALL tasks (or all tasks for a specific function).
        Implemented by pruning with a future date.
        """
        # 100年後の日付を指定して、実質的に全削除を行う
        future = datetime.now() + timedelta(days=365*100)
        logger.info(f"Clearing all tasks (func={func_name})...")
        count = self.db.prune(future, func_name)
        logger.info(f"Cleared {count} tasks.")
        return count

    def scan_garbage(self) -> list[str]:
        """
        Scan for orphaned blob files and return their identifiers (full locations).
        Does NOT delete anything.
        """
        refs = self.db.get_blob_refs()
        if refs is None:
            return []

        orphans = []
        for location in self.storage.list_keys():
            # Extract filename for comparison with DB refs
            filename = location.replace("\\", "/").split("/")[-1]
            
            if filename not in refs:
                orphans.append(location)
        
        return orphans

    def clean_garbage(self, orphans: Optional[list[str]] = None) -> tuple[int, int]:
        """
        Delete specific orphaned files.
        """
        if orphans is None:
            orphans = self.scan_garbage()
        
        if not orphans:
            return 0, 0

        deleted_count = 0
        freed_bytes = 0 

        for location in orphans:
            try:
                self.storage.delete(location)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete orphan {location}: {e}")
        
        return deleted_count, freed_bytes

