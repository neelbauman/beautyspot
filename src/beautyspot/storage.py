# src/beautyspot/storage.py

import os
import pickle
import io
from abc import ABC, abstractmethod
from typing import Any

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

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
        filename = f"{key}.pkl"
        filepath = os.path.join(self.base_dir, filename)
        # Atomic Write pattern
        temp_path = filepath + ".tmp"
        with open(temp_path, 'wb') as f:
            pickle.dump(data, f)
        os.replace(temp_path, filepath)
        return filepath

    def load(self, location: str) -> Any:
        if not os.path.exists(location):
            raise FileNotFoundError(f"Local blob lost: {location}")
        with open(location, 'rb') as f:
            return pickle.load(f)

class S3Storage(BlobStorageBase):
    def __init__(self, s3_uri: str, s3_opts: dict | None = None):
        if not boto3:
            raise ImportError("Run `pip install beautyspot[s3]` to use S3 storage.")
        
        # Parse "s3://bucket/prefix..."
        parts = s3_uri.replace("s3://", "").split("/", 1)
        self.bucket_name = parts[0]
        self.prefix = parts[1].rstrip("/") if len(parts) > 1 else "blobs"
        
        opts = s3_opts or {}
        self.s3 = boto3.client('s3', **opts)

    def save(self, key: str, data: Any) -> str:
        s3_key = f"{self.prefix}/{key}.pkl"
        buffer = io.BytesIO()
        pickle.dump(data, buffer)
        buffer.seek(0)
        self.s3.put_object(Bucket=self.bucket_name, Key=s3_key, Body=buffer)
        return f"s3://{self.bucket_name}/{s3_key}"

    def load(self, location: str) -> Any:
        parts = location.replace("s3://", "").split("/", 1)
        try:
            resp = self.s3.get_object(Bucket=parts[0], Key=parts[1])
            return pickle.loads(resp['Body'].read())
        except ClientError as e:
            raise FileNotFoundError(f"S3 blob lost: {location}") from e
