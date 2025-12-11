# src/beautyspot/utils.py

import hashlib
import os
import json
from typing import Any


def _stable_serialize_default(o: Any) -> Any:
    """
    JSON serialization fallback specifically designed for cache key generation.

    Unlike standard JSON serialization, this function prioritizes "stability"
    over "reversibility". It ensures that logically equivalent objects produce
    the same JSON string, even across different process runs.

    Strategies:
    1. Sets/Frozensets -> Sorted List (Stability for unordered collections)
    2. Bytes -> Hex String
    3. Objects -> dict representation (Avoids memory address in __repr__)
    """
    # 1. Sets are unordered, so sort them to ensure stable hash
    if isinstance(o, (set, frozenset)):
        try:
            return sorted(list(o))
        except TypeError:
            # If elements are not comparable, fall back to string repr sorted
            return sorted([str(x) for x in o])

    # 2. Bytes -> Hex string
    if isinstance(o, bytes):
        return o.hex()

    # 3. Custom Objects -> Dict
    # Pydantic models, Dataclasses, or normal classes
    if hasattr(o, "__dict__"):
        return o.__dict__

    if hasattr(o, "__slots__"):
        return {k: getattr(o, k) for k in o.__slots__ if hasattr(o, k)}

    # 4. Last resort: str()
    # This handles datetime, uuid, and other simple types reliably.
    # Warning: If __str__ contains memory address (e.g. <Obj at 0x...>), hash will be unstable.
    return str(o)


class KeyGen:
    @staticmethod
    def from_path_stat(filepath: str) -> str:
        """Fast: path + size + mtime"""
        if not os.path.exists(filepath):
            return f"MISSING_{filepath}"
        stat = os.stat(filepath)
        identifier = f"{filepath}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.md5(identifier.encode()).hexdigest()

    @staticmethod
    def from_file_content(filepath: str) -> str:
        """Strict: file content hash"""
        if not os.path.exists(filepath):
            return f"MISSING_{filepath}"
        hasher = hashlib.md5()
        # Include extension to distinguish format changes
        hasher.update(os.path.splitext(filepath)[1].lower().encode())
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        except OSError:
            return f"ERROR_{filepath}"
        return hasher.hexdigest()

    @staticmethod
    def default(args: tuple, kwargs: dict) -> str:
        """
        Fallback: Stable JSON serialization of args/kwargs.
        Handles custom objects and sets gracefully.
        """
        try:
            # Serialize with a smart default handler
            s = json.dumps(
                {"a": args, "k": kwargs},
                sort_keys=True,
                default=_stable_serialize_default,
                ensure_ascii=False,
            )
            return hashlib.md5(s.encode()).hexdigest()
        except Exception:
            # Fallback for circular references or truly unserializable objects.
            # We might want to log a warning here in the future.
            return hashlib.md5(str((args, kwargs)).encode()).hexdigest()

