# src/beautyspot/maintenance.py

import logging
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from typing import Optional, Any

from beautyspot.db import Flushable, Shutdownable, TaskDBMaintenable
from beautyspot.storage import BlobStorageMaintenable
from beautyspot.serializer import SerializerProtocol

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class MaintenanceService:
    """
    Service layer for administrative tasks, dashboard support, and system assembly.
    """

    def __init__(
        self,
        db: TaskDBMaintenable,
        storage: BlobStorageMaintenable,
        serializer: SerializerProtocol,
    ):
        self.db = db
        self.storage = storage
        self.serializer = serializer
        self._cleaning_lock = threading.Lock()
        self._owns_db = False  # from_path で作成した場合のみ True

    def close(self) -> None:
        """DB バックエンドをシャットダウンする。

        ``from_path`` で作成された場合のみ DB をシャットダウンします。
        外部から注入された DB は呼び出し元の責務でシャットダウンしてください。
        """
        if self._owns_db and isinstance(self.db, Shutdownable):
            self.db.shutdown(wait=True)

    def __enter__(self) -> "MaintenanceService":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @classmethod
    def from_path(
        cls, db_path: str | Path, blob_dir: Optional[str | Path] = None
    ) -> "MaintenanceService":
        """
        Factory method to assemble the system components (SQLite + Msgpack + Storage)
        from a database path.
        """
        # 遅延インポートで依存関係を解決
        from beautyspot.db import SQLiteTaskDB
        from beautyspot.storage import create_storage
        from beautyspot.serializer import MsgpackSerializer

        path = Path(db_path)

        # Blobディレクトリの推論ロジック
        if blob_dir:
            b_path = Path(blob_dir)
        else:
            # bs.Spot(name="foo") のデフォルト配置:
            #   .beautyspot/foo.db -> .beautyspot/blobs/foo/
            parent = path.parent
            stem = path.stem

            # 現行レイアウト優先: .beautyspot/blobs/{name}/
            candidate = parent / "blobs" / stem
            if candidate.exists():
                b_path = candidate
            else:
                # 旧レイアウトへのフォールバック: .beautyspot/{name}/blobs/
                legacy = parent / stem / "blobs"
                b_path = legacy if legacy.exists() else candidate

        db = SQLiteTaskDB(path)

        service = cls(
            db=db,
            storage=create_storage(str(b_path)),
            serializer=MsgpackSerializer(),
        )
        service._owns_db = True
        return service

    # --- Dashboard Support ---

    def get_history(self, limit: int = 1000):
        """Get task history from DB."""
        return self.db.get_history(limit=limit)

    def get_task_detail(
        self, cache_key: str, *, include_expired: bool = False
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve task details and decode the blob data if available.
        Returns the record dict with an extra 'decoded_data' key.

        Args:
            include_expired: If True, return expired records as well (for dashboard/debugging).
        """
        record = self.db.get(cache_key, include_expired=include_expired)
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
        record = self.db.get(cache_key, include_expired=True)
        if not record:
            return False

        result_record: dict[str, Any] = dict(record)

        # Bug Fix (Bug6): DB レコードを先に削除してからブロブを削除する。
        # 旧実装（ブロブ先削除）では DB レコード削除が失敗すると
        # 「DB に参照が残るがブロブが消えた」状態になり、次のアクセスで
        # CacheCorruptedError が発生していた。
        # ブロブが孤立した場合は GC (scan_garbage) で回収可能なため、
        # この順序の方が安全。
        deleted = self.db.delete(cache_key)
        if not deleted:
            return False

        # Blob削除
        if record.get("result_type") == "FILE" and record.get("result_value"):
            try:
                self.storage.delete(result_record["result_value"])
            except Exception as e:
                logger.warning(
                    f"Failed to delete blob for key '{cache_key}': {e}. "
                    "The orphaned blob will be collected by GC."
                )

        return True

    # --- Maintenance Operations ---

    def get_prunable_tasks(
        self, days: int, func_name: Optional[str] = None
    ) -> list[tuple[str, str, str]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return self.db.get_outdated_tasks(cutoff, func_name)

    def prune(self, days: int, func_name: Optional[str] = None) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        logger.info(f"Pruning tasks older than {cutoff} (func={func_name})...")
        count = self.db.prune(cutoff, func_name)
        logger.info(f"Deleted {count} tasks.")
        return count

    def clear(self, func_name: Optional[str] = None) -> int:
        logger.info(f"Clearing all tasks (func={func_name})...")
        count = self.db.delete_all(func_name)
        logger.info(f"Cleared {count} tasks.")
        return count

    def scan_garbage(self, grace_period: float = 60.0) -> list[str]:
        """
        Scan for orphaned blob files that are not referenced in the database.

        Args:
            grace_period: Minimum age of a blob (in seconds) to be considered an orphan.
                         This prevents deleting blobs that were just created but
                         not yet registered in the database (background saves).
        """
        ref_filenames = self.db.get_blob_refs()
        if ref_filenames is None:
            return []

        def _normalize_location(location: str) -> str:
            return location.replace("\\", "/")

        def _basename(location: str) -> str:
            return _normalize_location(location).split("/")[-1]

        ref_locations = {_normalize_location(loc) for loc in ref_filenames}
        # Legacy support: DBに絶対パスが保存されていた場合のみbasenameを許容
        ref_basenames = {
            _basename(loc) for loc in ref_locations if Path(loc).is_absolute()
        }

        now = time.time()
        orphans = []
        for location in self.storage.list_keys():
            norm = _normalize_location(location)
            if norm in ref_locations:
                continue
            if _basename(norm) in ref_basenames:
                continue

            # Check grace period
            if grace_period > 0:
                try:
                    mtime = self.storage.get_mtime(location)
                    if now - mtime < grace_period:
                        # Too new; potentially in-flight background save.
                        continue
                except Exception as e:
                    logger.debug(f"Failed to check mtime for {location} (ignored): {e}")
                    # Skip files that we can't check, to be safe.
                    continue

            orphans.append(location)

        return orphans

    def clean_garbage(
        self,
        orphans: Optional[list[str]] = None,
        tmp_max_age_seconds: int = 86400,
        orphan_grace_seconds: float = 60.0,
    ) -> tuple[int, int]:
        """
        期限切れのタスク（DBレコード）と孤立したBlobファイルを削除します。
        また、アトミック書き込み時に残留した古い一時ファイル (.spot_tmp) の
        クリーンアップも同時に行います。

        Args:
            orphans: 事前にスキャンされた孤立ファイルのリスト。
            tmp_max_age_seconds: 一時ファイルを削除対象とするまでの猶予期間（秒）。デフォルトは24時間。
            orphan_grace_seconds: 孤立ファイルを判定する際の猶予期間（秒）。デフォルトは60秒。

        Returns:
            tuple[int, int]: (削除された期限切れタスクの数, 削除された孤立ファイルの数)
        """
        if not self._cleaning_lock.acquire(blocking=False):
            logger.debug("Another eviction task is currently running. Skipping.")
            return 0, 0

        try:
            # Phase -1: DBの書き込みキューをフラッシュ
            # save_sync=False で投入された書き込みが未コミットの場合、
            # 直後の scan_garbage() がその blob を孤立ファイルと誤判定して
            # 削除してしまうレースコンディションを防ぐ。
            if isinstance(self.db, Flushable):
                try:
                    self.db.flush(timeout=10.0)
                except Exception as e:
                    logger.warning(f"DB flush before garbage scan failed: {e}")

            # Phase 0: 期限切れタスクの削除
            deleted_expired_count = self.delete_expired_tasks()
            if deleted_expired_count > 0:
                logger.info(f"Deleted {deleted_expired_count} expired tasks from DB.")

            # Phase 1: 孤立したファイルの特定
            if orphans is None:
                orphans = self.scan_garbage(grace_period=orphan_grace_seconds)

            deleted_orphan_count = 0

            # Phase 2: ファイルの実体削除
            if orphans:
                for location in orphans:
                    try:
                        self.storage.delete(location)
                        deleted_orphan_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete orphan blob {location}: {e}")

                if deleted_orphan_count > 0:
                    logger.info(f"Deleted {deleted_orphan_count} orphaned blob files.")

            # [ADD] Phase 2.5: 古い一時ファイルのクリーンアップ
            if hasattr(self.storage, "clean_temp_files"):
                try:
                    tmp_count = self.storage.clean_temp_files(  # type: ignore
                        max_age_seconds=tmp_max_age_seconds
                    )
                    if tmp_count > 0:
                        logger.info(f"Removed {tmp_count} abandoned temporary files.")
                except Exception as e:
                    logger.warning(f"Failed to clean temporary files: {e}")

            # Phase 3: 空ディレクトリ掃除
            if hasattr(self.storage, "prune_empty_dirs"):
                try:
                    dir_count = self.storage.prune_empty_dirs()  # type: ignore
                    if dir_count > 0:
                        logger.info(f"Removed {dir_count} empty directories.")
                except Exception as e:
                    logger.warning(f"Failed to prune empty directories: {e}")

            return deleted_expired_count, deleted_orphan_count

        finally:
            self._cleaning_lock.release()

    def resolve_key_prefix(self, prefix: str) -> str | list[str] | None:
        """
        Resolve a potentially shortened key to a full cache key.

        Returns:
            str: The single matching full key (Exact match or unique prefix match).
            list[str]: A list of conflicting candidates (Ambiguous).
            None: No match found.
        """
        # 1. 完全一致を最優先でチェック
        if self.db.get(prefix, include_expired=True):
            return prefix

        # 2. プレフィックス検索
        candidates = self.db.get_keys_start_with(prefix)

        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # 3. 曖昧な場合 (複数の候補を返す)
        return candidates

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
                raise
