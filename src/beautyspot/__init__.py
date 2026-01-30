# src/beautyspot/__init__.py

from .core import Spot
from .cachekey import KeyGen
from .storage import LocalStorage, S3Storage
from .types import ContentType
from .serializer import SerializationError

__all__ = ["Spot", "KeyGen", "LocalStorage", "S3Storage", "ContentType", "SerializationError",]
__version__ = "2.2.5"

