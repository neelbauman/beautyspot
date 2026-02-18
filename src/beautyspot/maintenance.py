# src/beautyspot/maintenance.py

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

from beautyspot.db import TaskDBBase
from beautyspot.storage import BlobStorageBase
from beautyspot.serializer import SerializerProtocol

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class MaintenanceService:
    """
    Service layer for administrative tasks, dashboard support, and system assembly.
    """

    def __init__(self, db: TaskDBBase, storage: BlobStorageBase, serializer: SerializerProtocol):
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

        db = SQLiteTaskDB(path)
        try:
            db.init_schema()
        except Exception:
            pass

        return cls(
            db=db,
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

    def delete_expired_tasks(self) -> int:
        """期限切れタスクの物理削除 (GC用)"""
        # [FIX] 内部実装(_connect)への依存を排除し、インターフェースメソッドを使用
        return self.db.delete_expired()

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

        # DB参照をファイル名のみのセットに変換 (S3/Local両対応)
        ref_filenames = set()
        for r in refs:
            if r:
                name = r.replace("\\", "/").split("/")[-1]
                ref_filenames.add(name)

        orphans = []
        for location in self.storage.list_keys():
            # location は "subdir/abc.bin" の可能性がある
            filename = location.replace("\\", "/").split("/")[-1]
            
            if filename not in ref_filenames:
                orphans.append(location)
        
        return orphans

    def clean_garbage(self, orphans: Optional[list[str]] = None) -> tuple[int, int]:
        if orphans is None:
            orphans = self.scan_garbage()
        
        deleted_count = 0
        freed_bytes = 0 
        
        # Phase 1: ファイル削除
        if orphans:
            for location in orphans:
                try:
                    self.storage.delete(location)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete orphan {location}: {e}")
        
        # Phase 2: 空ディレクトリ掃除 (LocalStorageのみ)
        if hasattr(self.storage, "prune_empty_dirs"):
            try:
                dir_count = self.storage.prune_empty_dirs()  # type: ignore
                if dir_count > 0:
                    logger.info(f"Removed {dir_count} empty directories.")
            except Exception as e:
                logger.warning(f"Failed to prune empty directories: {e}")
        
        return deleted_count, freed_bytes

    # --- Zombie Project Cleanup (gc command) ---

    @staticmethod
    def scan_orphan_projects(workspace_dir: Path) -> list[Path]:
        """
        Scan for blob directories in .beautyspot/blobs/ that have no corresponding .db file.
        Returns a list of Path objects for the orphan directories.
        """
        blobs_root = workspace_dir / "blobs"
        if not blobs_root.exists():
            return []
        
        orphans = []
        for entry in blobs_root.iterdir():
            if entry.is_dir():
                # blobs/{name} に対して {name}.db が存在するか確認
                db_path = workspace_dir / f"{entry.name}.db"
                if not db_path.exists():
                    orphans.append(entry)
        
        return orphans

    @staticmethod
    def delete_project_storage(path: Path) -> None:
        """
        Recursively delete a project storage directory.
        """
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
            except Exception as e:
                logger.error(f"Failed to delete directory {path}: {e}")
                raise e

