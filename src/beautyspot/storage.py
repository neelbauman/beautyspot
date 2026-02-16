# src/beautyspot/storage.py

import os
import io
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, TypeAlias

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception


ReadableBuffer: TypeAlias = bytes | bytearray | memoryview


class CacheCorruptedError(Exception):
    """Raised when blob data cannot be deserialized (e.g. code changes)."""

    pass


class BlobStorageBase(ABC):
    """
    Abstract base class for large object storage (BLOBs).
    
    Implementations must handle serialization of the location identifier
    returned by save(), which will be stored in the TaskDB.
    """

    @abstractmethod
    def save(self, key: str, data: ReadableBuffer) -> str:
        """
        Persist the data associated with the given key.

        Args:
            key (str): A unique identifier for the content (e.g. hash).
            data (bytes): The binary data to store.

        Returns:
            str: A location identifier (e.g. file path, S3 URI).
                 This string MUST be retrievable by self.load(location).
        """
        pass

    @abstractmethod
    def load(self, location: str) -> bytes:
        """
        Retrieve data from the specified location.

        Args:
            location (str): The location identifier returned by save().

        Returns:
            bytes: The retrieved binary data.

        Raises:
            FileNotFoundError: If the data no longer exists.
        """
        pass

    @abstractmethod
    def delete(self, location: str) -> None:
        """
        Delete the blob at the specified location.

        Implementations should attempt to delete the resource.
        If the file does not exist, it SHOULD fail silently or log a warning,
        but MUST NOT raise an error (idempotency).
        """
        pass


class LocalStorage(BlobStorageBase):
    def __init__(self, base_dir: str | Path):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _validate_key(self, key: str):
        # Prevent Path Traversal
        if ".." in key or "/" in key or "\\" in key:
            raise ValueError(
                f"Invalid key: '{key}'. Keys must not contain path separators."
            )

    def save(self, key: str, data: ReadableBuffer) -> str:
        self._validate_key(key)
        filename = f"{key}.bin"
        filepath = os.path.join(self.base_dir, filename)
        temp_path = filepath + ".tmp"

        with open(temp_path, "wb") as f:
            f.write(data)

        os.replace(temp_path, filepath)
        return filepath

    def load(self, location: str) -> bytes:
        if not os.path.exists(location):
            raise FileNotFoundError(f"Local blob lost: {location}")

        # Security check: ensure location is within base_dir
        # However, 'location' here is the full path returned by save().
        # If the user passes a manipulated path to load(), it could be an issue.
        # But load() takes 'location' which is supposed to be the return value of save().
        # Let's check if we can validate it.

        # Actually, the interface says 'location' -> Any.
        # In LocalStorage, save returns filepath.
        # If we want to be strict, we should check if filepath is inside base_dir.

        abs_location = os.path.abspath(location)
        abs_base = os.path.abspath(self.base_dir)

        if not abs_location.startswith(abs_base):
            raise ValueError(
                f"Access denied: {location} is outside of storage directory."
            )

        with open(location, "rb") as f:
            return f.read()


    def delete(self, location: str) -> None:
        # location は save() が返したフルパスであることを期待
        if os.path.exists(location):
            # 安全のため、base_dir 内かチェックしても良いが、
            # load() 同様、一旦は信頼して削除する
            try:
                os.remove(location)
            except OSError as e:
                # 権限エラーなどは呼び出し元に伝えるべきかもしれないが、
                # キャッシュ削除の文脈では「消そうとしたが消せなかった」はWarningで済ますことが多い
                print(e)
                pass


class S3Storage(BlobStorageBase):
    def __init__(
        self, s3_uri: str,
        s3_opts: dict[str, Any] | None = None,
    ):
        if not boto3:
            raise ImportError("Run `pip install beautyspot[s3]` to use S3 storage.")

        parts = s3_uri.replace("s3://", "").split("/", 1)
        self.bucket_name = parts[0]
        self.prefix = parts[1].rstrip("/") if len(parts) > 1 else "blobs"

        opts = s3_opts or {}
        self.s3 = boto3.client("s3", **opts)

    def save(self, key: str, data: ReadableBuffer) -> str:
        s3_key = f"{self.prefix}/{key}.bin"
        buffer = io.BytesIO(data)
        self.s3.put_object(Bucket=self.bucket_name, Key=s3_key, Body=buffer)
        return f"s3://{self.bucket_name}/{s3_key}"

    def load(self, location: str) -> bytes:
        parts = location.replace("s3://", "").split("/", 1)
        try:
            resp = self.s3.get_object(Bucket=parts[0], Key=parts[1])
            return resp["Body"].read()
        except ClientError as e:
            raise FileNotFoundError(f"S3 blob lost: {location}") from e
        # except (pickle.UnpicklingError, AttributeError, EOFError, ImportError, IndexError) as e:
        #     raise CacheCorruptedError(f"Failed to unpickle S3 object {location}: {e}") from e

    def delete(self, location: str) -> None:
        parts = location.replace("s3://", "").split("/", 1)
        try:
            self.s3.delete_object(Bucket=parts[0], Key=parts[1])
        except ClientError:
            # S3のdelete_objectは存在しなくてもエラーにならないが、権限エラー等はキャッチ
            pass


def create_storage(path: str, options: dict | None = None) -> BlobStorageBase:
    """
    Factory function to create a storage backend based on the path protocol.

    Args:
        path: Storage path or URI (e.g., "./data", "s3://my-bucket/prefix").
        options: Extra options passed to the backend (e.g., boto3 client args).
    """
    if path.startswith("s3://"):
        return S3Storage(path, options)

    # 将来的な拡張ポイント (例: gs://, azure://)
    # if path.startswith("gs://"):
    #     return GCSStorage(path, options)

    return LocalStorage(path)
