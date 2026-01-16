# src/beautyspot/cachekey.py

import hashlib
import os
import msgpack
from typing import Any, Union

ReadableBuffer = Union[bytes, bytearray, memoryview]

def _safe_sort_key(obj: Any):
    """
    Helper for sorting mixed types.
    Returns a tuple (priority, type_name, str_repr) to ensure consistent ordering
    even across different types that are not natively comparable in Python 3.
    """
    if obj is None:
        return (0, "")
    return (1, str(type(obj)), str(obj))

def canonicalize(obj: Any) -> Any:
    """
    Recursively converts an object into a canonical form suitable for stable Msgpack serialization.
    
    Strategies:
    1. Dict -> Sorted List of entries (fixes order).
    2. Set -> Sorted List (fixes order).
    3. Numpy-like -> Tuple with raw bytes (efficient & exact).
    4. Object -> Dict via __dict__ or __slots__ (avoids memory address).
    """
    # 1. Primitives (No change needed)
    if obj is None or isinstance(obj, (int, float, bool, str, bytes)):
        return obj

    # 2. Dict -> List of [k, v], sorted by key
    if isinstance(obj, dict):
        return [
            [canonicalize(k), canonicalize(v)]
            for k, v in sorted(obj.items(), key=lambda i: _safe_sort_key(i[0]))
        ]

    # 3. List/Tuple -> Recursive canonicalization
    if isinstance(obj, (list, tuple)):
        return [canonicalize(x) for x in obj]

    # 4. Set -> Sorted List
    if isinstance(obj, (set, frozenset)):
        normalized_items = [canonicalize(x) for x in obj]
        return sorted(normalized_items, key=_safe_sort_key)

    # 5. Numpy Array Handling (Duck Typing)
    # Check for numpy-like attributes to avoid importing numpy directly.
    # We use 'tobytes()' to get the full raw data, avoiding the "..." truncation issue of str().
    if hasattr(obj, "shape") and hasattr(obj, "dtype") and hasattr(obj, "tobytes"):
        try:
            # Format: ("__numpy__", shape, dtype, raw_bytes)
            # This ensures distinct hashes for arrays with different contents.
            return ("__numpy__", obj.shape, str(obj.dtype), obj.tobytes())
        except Exception:
            # Fallback if method call fails
            pass

    # 6. Custom Objects (Pydantic, Dataclasses, etc.)
    if hasattr(obj, "__dict__"):
        return canonicalize(obj.__dict__)
    
    if hasattr(obj, "__slots__"):
        return [
            [k, canonicalize(getattr(obj, k))]
            for k in sorted(obj.__slots__)
            if hasattr(obj, k)
        ]

    # 7. Last Resort: String representation
    # Warning: May contain memory addresses or be truncated.
    return str(obj)


class KeyGen:
    """
    Generates stable cache keys (SHA-256) for various inputs.
    """

    @staticmethod
    def from_path_stat(filepath: str) -> str:
        """Fast: path + size + mtime (SHA-256)"""
        if not os.path.exists(filepath):
            return f"MISSING_{filepath}"
        stat = os.stat(filepath)
        identifier = f"{filepath}_{stat.st_size}_{stat.st_mtime}"
        return hashlib.sha256(identifier.encode()).hexdigest()

    @staticmethod
    def from_file_content(filepath: str) -> str:
        """Strict: file content hash (SHA-256)"""
        if not os.path.exists(filepath):
            return f"MISSING_{filepath}"
        
        hasher = hashlib.sha256()
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
        Generates a stable SHA-256 hash from function arguments using recursive canonicalization.
        Uses Msgpack for efficient binary serialization.
        """
        try:
            # 1. Normalize structure (removes Dict/Set order ambiguity)
            normalized = [
                canonicalize(args),
                canonicalize(kwargs)
            ]
            
            # 2. Serialize to bytes (Deterministic because structure is fixed)
            packed = msgpack.packb(normalized)
            
            # 3. Hash (SHA-256)
            return hashlib.sha256(packed).hexdigest()
            
        except Exception:
            # Fallback for truly unserializable objects or recursion errors
            return hashlib.sha256(str((args, kwargs)).encode()).hexdigest()

