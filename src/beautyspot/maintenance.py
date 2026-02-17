# src/beautyspot/maintenance.py

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

from beautyspot.db import TaskDB
from beautyspot.storage import BlobStorageBase
from beautyspot.serializer import SerializerProtocol

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class MaintenanceService:
    """
    Service layer for administrative tasks, dashboard support, and system assembly.
    """

    def __init__(self, db: TaskDB, storage: BlobStorageBase, serializer: SerializerProtocol):
        self.db = db
        self.storage = storage
        self.serializer = serializer

    @classmethod
    def from_path(cls, db_path: str | Path, blob_dir: Optional[str | Path] = None) -> "MaintenanceService":
        """
        Factory method to assemble the system components (SQLite + Msgpack + Storage)
        from a database path.
        """
        # 遅延インポートで依存関係を解決
        from beautyspot.db import SQLiteTaskDB
        from beautyspot.storage import create_storage
        from beautyspot.serializer import MsgpackSerializer

        path = Path(db_path)

        # Blobディレクトリの推論ロジック (旧 Spot.from_path より移植)
        if blob_dir:
            b_path = Path(blob_dir)
        else:
            # .beautyspot/project.db -> .beautyspot/project/blobs/
            # または兄弟ディレクトリ: .beautyspot/blobs/
            parent = path.parent
            stem = path.stem
            
            candidate = parent / stem / "blobs"
            if candidate.exists():
                b_path = candidate
            else:
                b_path = parent / "blobs"

        return cls(
            db=SQLiteTaskDB(path),
            storage=create_storage(str(b_path)),
            serializer=MsgpackSerializer(),
        )


    # --- Dashboard Support ---

    def get_history(self, limit: int = 1000):
        """Get task history from DB."""
        return self.db.get_history(limit=limit)

    def get_task_detail(self, cache_key: str) -> Optional[dict[str, Any]]:
        """
        Retrieve task details and decode the blob data if available.
        Returns the record dict with an extra 'decoded_data' key.
        """
        record = self.db.get(cache_key)
        if not record:
            return None

        result_record: dict[str, Any] = dict(record)

        decoded_data = None
        r_type = record.get("result_type")
        r_val = record.get("result_value")
        r_blob = record.get("result_data")

        try:
            if r_type == "DIRECT_BLOB":
                if r_blob is not None:
                    decoded_data = self.serializer.loads(r_blob)
            
            elif r_type == "FILE":
                if r_val:
                    # Storage からロードしてデシリアライズ
                    data_bytes = self.storage.load(r_val)
                    decoded_data = self.serializer.loads(data_bytes)
        
        except Exception as e:
            logger.error(f"Failed to decode data for key '{cache_key}': {e}")
            # デコード失敗時は decoded_data は None のまま

        result_record["decoded_data"] = decoded_data
        return result_record

    def delete_task(self, cache_key: str) -> bool:
        """
        Delete a task record and its associated blob file.
        """
        record = self.db.get(cache_key)
        if not record:
            return False

        result_record: dict[str, Any] = dict(record)

        # Blob削除
        if record.get("result_type") == "FILE" and record.get("result_value"):
            try:
                self.storage.delete(result_record["result_value"])
            except Exception as e:
                logger.warning(f"Failed to delete blob for key '{cache_key}': {e}")

        # レコード削除
        return self.db.delete(cache_key)

    # --- Maintenance Operations ---

    def get_prunable_tasks(self, days: int, func_name: Optional[str] = None) -> list[tuple[str, str, str]]:
        cutoff = datetime.now() - timedelta(days=days)
        return self.db.get_outdated_tasks(cutoff, func_name)

    def prune(self, days: int, func_name: Optional[str] = None) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        logger.info(f"Pruning tasks older than {cutoff} (func={func_name})...")
        count = self.db.prune(cutoff, func_name)
        logger.info(f"Deleted {count} tasks.")
        return count
        
    def clear(self, func_name: Optional[str] = None) -> int:
        future = datetime.now() + timedelta(days=365*100)
        logger.info(f"Clearing all tasks (func={func_name})...")
        count = self.db.prune(future, func_name)
        logger.info(f"Cleared {count} tasks.")
        return count

    def scan_garbage(self) -> list[str]:
        refs = self.db.get_blob_refs()
        if refs is None:
            return []

        # 1. 比較用に DB側の参照を「ファイル名」に正規化して集合(set)にする
        ref_filenames = set()
        for r in refs:
            if r:
                # S3 URI や パス区切りを考慮して末尾(ファイル名)を取得
                name = r.replace("\\", "/").split("/")[-1]
                ref_filenames.add(name)

        orphans = []
        for location in self.storage.list_keys():
            # 2. ストレージ上のファイルも同様にファイル名を取り出す
            filename = location.replace("\\", "/").split("/")[-1]
            
            # 3. ファイル名同士で比較
            if filename not in ref_filenames:
                orphans.append(location)
        
        return orphans

    def clean_garbage(self, orphans: Optional[list[str]] = None) -> tuple[int, int]:
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

