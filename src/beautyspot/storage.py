# src/beautyspot/storage.py

import os
import io
import logging
import tempfile
import time
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, TypeAlias, Iterator, Protocol, runtime_checkable
from dataclasses import dataclass, field
from beautyspot.exceptions import CacheCorruptedError, ValidationError

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


ReadableBuffer: TypeAlias = bytes | bytearray | memoryview

# --- Storage Policies ---


@runtime_checkable
class StoragePolicyProtocol(Protocol):
    """
    Protocol to determine if data should be saved as a blob (file/object storage)
    or directly in the database based on the data content (usually size).
    """

    def should_save_as_blob(self, data: bytes) -> bool: ...


@dataclass
class ThresholdStoragePolicy(StoragePolicyProtocol):
    """
    Policy that saves data as a blob if its size exceeds a configured threshold.
    This is the recommended policy for automatic optimization.
    """

    threshold: int

    def should_save_as_blob(self, data: bytes) -> bool:
        return len(data) > self.threshold


@dataclass
class WarningOnlyPolicy(StoragePolicyProtocol):
    """
    Policy for backward compatibility (v2.0 behavior).
    Does not force blob storage, but logs a warning if size exceeds threshold.
    """

    warning_threshold: int
    # logger は比較・repr 対象外にする。
    # dataclass の自動生成 __eq__ に logger インスタンスが混入するのを防ぐ。
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("beautyspot"),
        compare=False,
        repr=False,
    )

    def should_save_as_blob(self, data: bytes) -> bool:
        if len(data) > self.warning_threshold:
            self.logger.warning(
                f"⚠️ Large data detected ({len(data)} bytes). "
                f"Consider using `save_blob=True` or a stricter StoragePolicy."
            )
        return False


@dataclass
class AlwaysBlobPolicy(StoragePolicyProtocol):
    """
    Policy that always saves data as a blob.
    Equivalent to setting `default_save_blob=True`.
    """

    def should_save_as_blob(self, data: bytes) -> bool:
        return True


# --- Blob Storage Implementations ---


class BlobStorageBase(ABC):
    """
    Abstract base class for large object storage (BLOBs).
    """

    @abstractmethod
    def save(self, key: str, data: ReadableBuffer) -> str:
        """
        Persist the data associated with the given key.
        Returns a location identifier.
        """
        pass

    @abstractmethod
    def load(self, location: str) -> bytes:
        """
        Retrieve data from the specified location.
        """
        pass

    @abstractmethod
    def delete(self, location: str) -> None:
        """
        Delete the blob at the specified location.
        Should be idempotent (no error if file missing).
        """
        pass

    @abstractmethod
    def list_keys(self) -> Iterator[str]:
        """
        Yields location identifiers for all stored blobs.
        Used for Garbage Collection.
        MUST yield the same format (path/URI) that is accepted by `delete`.
        """
        pass

    @abstractmethod
    def get_mtime(self, location: str) -> float:
        """
        Get the last modified time of the blob as a POSIX timestamp.
        Used to prevent race conditions during Garbage Collection.
        """
        pass

    def prune_empty_dirs(self) -> int:
        """
        Remove empty directories left after blob deletion.
        Returns the count of removed directories.
        Default implementation is a no-op (e.g. for S3 which has no directories).
        """
        return 0

    def clean_temp_files(self, max_age_seconds: int = 86400) -> int:
        """
        Clean up abandoned temporary files older than the specified age.
        Returns the count of removed files.
        Default implementation is a no-op.
        """
        return 0


class LocalStorage(BlobStorageBase):
    def __init__(self, base_dir: str | Path):
        # Resolve to absolute path explicitly on init
        self.base_dir = Path(base_dir).resolve()
        self._ensure_cache_dir(self.base_dir)

    @staticmethod
    def _ensure_cache_dir(directory: Path) -> None:
        """
        ディレクトリを作成し、Gitの管理下に入らないよう .gitignore を配置する。
        """
        directory.mkdir(parents=True, exist_ok=True)
        gitignore_path = directory / ".gitignore"
        if not gitignore_path.exists():
            try:
                gitignore_path.write_text("*\n")
            except OSError as e:
                # 権限問題などで書けない場合は処理を続行（ログのみ）
                logging.warning(f"Failed to create .gitignore in {directory}: {e}")

    def _validate_key(self, key: str):
        """save() に渡されるキャッシュキーを検証する。

        Note:
            この検証は save() の引数（通常は SHA-256 ハッシュ）にのみ適用される。
            list_keys() が返すロケーション文字列（例: 'subdir/hash.bin'）は
            レガシーデータとの互換性のためにパス区切り文字を含む場合があり、
            load() / delete() では別途パストラバーサルチェックを行う。
        """
        # Prevent Path Traversal
        if ".." in key or "/" in key or "\\" in key:
            raise ValidationError(
                f"Invalid key: '{key}'. Keys must not contain path separators."
            )

    def save(self, key: str, data: ReadableBuffer) -> str:
        self._validate_key(key)
        filename = f"{key}.bin"
        filepath = self.base_dir / filename

        # Atomic write: mkstemp generates a unique temp file to avoid collisions
        # when multiple threads/processes write concurrently.
        # flush + fsync ensures data reaches disk before rename,
        # so a crash between write and rename never leaves a corrupt file.
        fd, temp_path_str = tempfile.mkstemp(dir=self.base_dir, suffix=".spot_tmp")
        try:
            with os.fdopen(fd, "wb", closefd=True) as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            Path(temp_path_str).replace(filepath)
        except BaseException:
            try:
                os.unlink(temp_path_str)
            except OSError:
                # PermissionError等で消せなかった場合は残留するが、後でGCが回収する
                pass
            raise

        return filename

    def load(self, location: str) -> bytes:
        # [CHANGED] Resolve location relative to base_dir.
        # Note: If 'location' is an absolute path (legacy data), pathlib behavior
        # (base / abs) returns abs, so backward compatibility on the same machine is preserved.
        full_path = (self.base_dir / location).resolve()

        # Security check: Ensure the path is strictly within the base_dir
        if not full_path.is_relative_to(self.base_dir):
            raise CacheCorruptedError(
                f"Access denied: {location} resolves to {full_path}, which is outside {self.base_dir}"
            )

        if not full_path.exists():
            raise CacheCorruptedError(f"Local blob lost: {full_path}")

        try:
            with open(full_path, "rb") as f:
                return f.read()
        except OSError as e:
            raise CacheCorruptedError(f"Failed to read blob: {e}")

    def delete(self, location: str) -> None:
        """
        Delete the file at the given location.

        Note:
            For performance reasons, this method does not synchronously remove
            empty parent directories. Directory cleanup is deferred to the
            asynchronous maintenance task (`prune_empty_dirs` / `beautyspot gc`).
        """
        full_path = (self.base_dir / location).resolve()

        if not full_path.is_relative_to(self.base_dir):
            return

        try:
            os.remove(full_path)
        except FileNotFoundError:
            pass
        except (PermissionError, OSError) as e:
            # 他のプロセスによるロックや権限の問題をログに残すが、処理は継続する
            logging.warning(
                f"Failed to delete blob at {full_path}: {e}. It will be handled by subsequent GC."
            )

    def list_keys(self) -> Iterator[str]:
        """
        Yields relative paths of all .bin files, including subdirectories.
        Example: 'hash.bin' or 'subdir/hash.bin'
        """
        if not self.base_dir.exists():
            return

        # rglob で再帰的に探索
        for entry in self.base_dir.rglob("*.bin"):
            if entry.is_file():
                # base_dir からの相対パスを返す
                yield str(entry.relative_to(self.base_dir).as_posix())

    def get_mtime(self, location: str) -> float:
        full_path = (self.base_dir / location).resolve()
        if not full_path.is_relative_to(self.base_dir):
            raise ValueError(f"Access denied: {location}")
        try:
            return full_path.stat().st_mtime
        except OSError as e:
            raise CacheCorruptedError(f"Failed to get mtime for blob: {e}")

    def clean_temp_files(self, max_age_seconds: int = 86400) -> int:
        """
        Remove '.spot_tmp' files that are older than max_age_seconds.
        Provides a fail-safe against leaked temporary files due to file locks.
        """
        if not self.base_dir.exists():
            return 0

        removed_count = 0
        now = time.time()

        for entry in self.base_dir.rglob("*.spot_tmp"):
            if entry.is_file():
                try:
                    # 猶予期間（デフォルト24時間）を経過しているかチェック
                    if now - entry.stat().st_mtime > max_age_seconds:
                        entry.unlink()
                        removed_count += 1
                except OSError:
                    # アンチウイルスソフト等で現在もロックされている場合はスキップ
                    pass

        return removed_count

    def prune_empty_dirs(self) -> int:
        """
        Recursively remove empty directories under base_dir.
        Also removes directories containing only system generated files (.DS_Store, etc).
        Returns the count of removed directories.

        Note:
            base_dir 自体は削除しません。base_dir が削除されると以降の
            save() で FileNotFoundError が発生するためです。
        """
        if not self.base_dir.exists():
            return 0

        IGNORED_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
        removed_count = 0

        # os.walk(topdown=False) で深い階層から順に処理
        for root, dirs, files in os.walk(self.base_dir, topdown=False):
            path = Path(root)

            # base_dir 自体は絶対に削除しない
            if path == self.base_dir:
                continue

            existing_files = set(files)

            # 無視リスト以外のファイルがある場合 -> 削除不可
            if existing_files - IGNORED_FILES:
                continue

            # 無視リストにあるファイルしか残っていない場合、それらを消して空にする
            for f in existing_files:
                try:
                    (path / f).unlink()
                except OSError:
                    pass

            # ディレクトリ削除を試みる
            try:
                path.rmdir()
                removed_count += 1
            except OSError:
                pass

        return removed_count


class S3Storage(BlobStorageBase):
    def __init__(
        self,
        s3_uri: str,
        s3_opts: dict[str, Any] | None = None,
    ):
        if not boto3:
            raise ImportError("Run `pip install beautyspot[s3]` to use S3 storage.")

        parts = s3_uri.replace("s3://", "").split("/", 1)
        self.bucket_name = parts[0]
        raw_prefix = parts[1].rstrip("/") if len(parts) > 1 else ""
        self.prefix = raw_prefix if raw_prefix else "blobs"

        opts = s3_opts or {}
        self.s3 = boto3.client("s3", **opts)

    @staticmethod
    def _parse_s3_uri(location: str) -> tuple[str, str]:
        """Parse an s3:// URI into (bucket, key). Raises ValueError for invalid URIs."""
        if not location.startswith("s3://"):
            raise ValidationError(f"Expected an s3:// URI, got: {location!r}")
        path = location[len("s3://") :]
        parts = path.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValidationError(
                f"Invalid S3 URI (expected s3://bucket/key): {location!r}"
            )
        return parts[0], parts[1]

    def save(self, key: str, data: ReadableBuffer) -> str:
        s3_key = f"{self.prefix}/{key}.bin"
        buffer = io.BytesIO(data)
        # upload_fileobj は大容量データ(>5GB)に対してマルチパートアップロードを
        # 自動的に使用し、put_object の 5GB 上限を回避する。
        self.s3.upload_fileobj(buffer, self.bucket_name, s3_key)
        return f"s3://{self.bucket_name}/{s3_key}"

    def load(self, location: str) -> bytes:
        bucket, key = self._parse_s3_uri(location)
        try:
            resp = self.s3.get_object(Bucket=bucket, Key=key)
            body = resp["Body"]
            try:
                return body.read()
            finally:
                body.close()
        except ClientError as e:
            raise CacheCorruptedError(f"S3 blob lost: {location}") from e

    def delete(self, location: str) -> None:
        bucket, key = self._parse_s3_uri(location)
        try:
            self.s3.delete_object(Bucket=bucket, Key=key)
        except ClientError as e:
            # S3 の delete_object は存在しないオブジェクトに対してもエラーを返さないため、
            # ここに到達するのは権限エラーやネットワーク障害などの深刻なケース。
            # 握り潰さずにログへ記録し、GC が後続で回収できるようにする。
            logging.warning(
                f"Failed to delete S3 object {location}: {e}. "
                "It will be handled by subsequent GC."
            )

    def get_mtime(self, location: str) -> float:
        bucket, key = self._parse_s3_uri(location)
        try:
            resp = self.s3.head_object(Bucket=bucket, Key=key)
            # LastModified is a datetime object, convert to POSIX timestamp
            return resp["LastModified"].timestamp()
        except ClientError as e:
            raise CacheCorruptedError(
                f"S3 blob lost or inaccessible: {location}"
            ) from e

    def list_keys(self) -> Iterator[str]:
        """Yields s3:// URIs for all objects in the prefix."""
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                yield f"s3://{self.bucket_name}/{obj['Key']}"


def create_storage(path: str, options: dict | None = None) -> BlobStorageBase:
    if path.startswith("s3://"):
        return S3Storage(path, options)

    return LocalStorage(path)
