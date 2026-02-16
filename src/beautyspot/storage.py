# src/beautyspot/storage.py

import os
import io
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, TypeAlias, Iterator

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


class LocalStorage(BlobStorageBase):
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _validate_key(self, key: str):
        # Prevent Path Traversal
        if ".." in key or "/" in key or "\\" in key:
            raise ValueError(
                f"Invalid key: '{key}'. Keys must not contain path separators."
            )

    def save(self, key: str, data: ReadableBuffer) -> str:
        self._validate_key(key)
        filename = f"{key}.bin"
        filepath = self.base_dir / filename
        temp_path = self.base_dir / f"{filename}.tmp"

        with open(temp_path, "wb") as f:
            f.write(data)

        temp_path.replace(filepath)
        return str(filepath.absolute())

    def load(self, location: str) -> bytes:
        if not os.path.exists(location):
            raise FileNotFoundError(f"Local blob lost: {location}")

        # Security check
        abs_location = os.path.abspath(location)
        abs_base = os.path.abspath(self.base_dir)

        if not abs_location.startswith(abs_base):
            raise ValueError(
                f"Access denied: {location} is outside of storage directory."
            )

        with open(location, "rb") as f:
            return f.read()

    def delete(self, location: str) -> None:
        try:
            os.remove(location)
        except FileNotFoundError:
            pass

    def list_keys(self) -> Iterator[str]:
        """Yields absolute paths of all .bin files in the directory."""
        if not self.base_dir.exists():
            return
        for entry in self.base_dir.glob("*.bin"):
            # delete() relies on full path to find the file
            yield str(entry.absolute())


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

    def delete(self, location: str) -> None:
        parts = location.replace("s3://", "").split("/", 1)
        try:
            self.s3.delete_object(Bucket=parts[0], Key=parts[1])
        except ClientError:
            pass

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

