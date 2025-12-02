# src/beautyspot/storage.py

import os
import io
from abc import ABC, abstractmethod
from typing import Any

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None


class CacheCorruptedError(Exception):
    """Raised when blob data cannot be deserialized (e.g. code changes)."""
    pass


class BlobStorageBase(ABC):
    @abstractmethod
    def save(self, key: str, data: Any) -> str: pass
    @abstractmethod
    def load(self, location: str) -> Any: pass


class LocalStorage(BlobStorageBase):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def save(self, key: str, data: Any) -> str:
        filename = f"{key}.bin"
        filepath = os.path.join(self.base_dir, filename)
        temp_path = filepath + ".tmp"

        with open(temp_path, 'wb') as f:
            f.write(data)

        os.replace(temp_path, filepath)
        return filepath

    def load(self, location: str) -> bytes:
        if not os.path.exists(location):
            raise FileNotFoundError(f"Local blob lost: {location}")

        with open(location, 'rb') as f:
            return f.read()
        
        # try:
        #     with open(location, 'rb') as f:
        #         return pickle.load(f)
        # except (pickle.UnpicklingError, AttributeError, EOFError, ImportError, IndexError) as e:
        #     # クラス定義変更やファイル破損時
        #     raise CacheCorruptedError(f"Failed to unpickle {location}: {e}") from e


class S3Storage(BlobStorageBase):
    def __init__(self, s3_uri: str, s3_opts: dict | None = None):
        if not boto3:
            raise ImportError("Run `pip install beautyspot[s3]` to use S3 storage.")
        
        parts = s3_uri.replace("s3://", "").split("/", 1)
        self.bucket_name = parts[0]
        self.prefix = parts[1].rstrip("/") if len(parts) > 1 else "blobs"
        
        opts = s3_opts or {}
        self.s3 = boto3.client('s3', **opts)

    def save(self, key: str, data: Any) -> str:
        s3_key = f"{self.prefix}/{key}.bin"
        buffer = io.BytesIO(data)
        self.s3.put_object(Bucket=self.bucket_name, Key=s3_key, Body=buffer)
        return f"s3://{self.bucket_name}/{s3_key}"

    def load(self, location: str) -> bytes:
        parts = location.replace("s3://", "").split("/", 1)
        try:
            resp = self.s3.get_object(Bucket=parts[0], Key=parts[1])
            return resp['Body'].read()
        except ClientError as e:
            raise FileNotFoundError(f"S3 blob lost: {location}") from e
        # except (pickle.UnpicklingError, AttributeError, EOFError, ImportError, IndexError) as e:
        #     raise CacheCorruptedError(f"Failed to unpickle S3 object {location}: {e}") from e


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

