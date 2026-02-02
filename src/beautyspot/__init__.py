# src/beautyspot/__init__.py

from importlib.metadata import version, PackageNotFoundError
from .core import Spot
from .cachekey import KeyGen
from .storage import LocalStorage, S3Storage
from .types import ContentType
from .serializer import SerializationError

try:
    __version__ = version("beautyspot")
except PackageNotFoundError:
    # 開発中や未インストールの状態
    __version__ = "0.0.0+unknown"

__all__ = [
    "Spot",
    "KeyGen",
    "LocalStorage",
    "S3Storage",
    "ContentType",
    "SerializationError",
]

