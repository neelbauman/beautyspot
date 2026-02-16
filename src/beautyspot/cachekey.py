# src/beautyspot/cachekey.py

import hashlib
import os
import msgpack
import inspect
from enum import Enum, auto
from functools import singledispatch
from typing import Any, Union, Callable, Dict, ParamSpec

ReadableBuffer = Union[bytes, bytearray, memoryview]

P = ParamSpec("P")

def _safe_sort_key(obj: Any):
    """
    Helper for sorting mixed types.
    Returns a tuple (priority, type_name, str_repr) to ensure consistent ordering
    even across different types that are not natively comparable in Python 3.
    """
    if obj is None:
        return (0, "")
    return (1, str(type(obj)), str(obj))


@singledispatch
def canonicalize(obj: Any) -> Any:
    """
    Recursively converts an object into a canonical form suitable for stable Msgpack serialization.

    This function acts as the default handler for primitives and types not explicitly registered.
    It also handles duck-typing cases like Numpy arrays and custom objects.

    Strategies:
    1. Primitives -> Return as-is.
    2. Numpy-like -> Tuple with raw bytes (efficient & exact).
    3. Custom Object (Instance) -> Dict via __dict__ or __slots__.
    4. Fallback -> String representation.
    """
    # 1. Primitives (No change needed)
    if obj is None or isinstance(obj, (int, float, bool, str, bytes)):
        return obj

    # 2. Numpy Array Handling (Duck Typing)
    # We check attributes to avoid hard dependency on numpy
    if hasattr(obj, "shape") and hasattr(obj, "dtype") and hasattr(obj, "tobytes"):
        try:
            return ("__numpy__", obj.shape, str(obj.dtype), obj.tobytes())
        except Exception:
            pass

    # 3. Custom Objects (Instance)
    if hasattr(obj, "__dict__"):
        return canonicalize(obj.__dict__)

    if hasattr(obj, "__slots__"):
        return [
            [k, canonicalize(getattr(obj, k))]
            for k in sorted(obj.__slots__)
            if hasattr(obj, k)
        ]

    # 4. Last Resort: String representation
    return str(obj)


@canonicalize.register(dict)
def _(obj: dict) -> list:
    """Dict -> List of [k, v], sorted by key"""
    return [
        [canonicalize(k), canonicalize(v)]
        for k, v in sorted(obj.items(), key=lambda i: _safe_sort_key(i[0]))
    ]


@canonicalize.register(list)
@canonicalize.register(tuple)
def _(obj: Union[list, tuple]) -> list:
    """List/Tuple -> Recursive canonicalization"""
    return [canonicalize(x) for x in obj]


@canonicalize.register(set)
@canonicalize.register(frozenset)
def _(obj: Union[set, frozenset]) -> list:
    """Set -> Sorted List"""
    normalized_items = [canonicalize(x) for x in obj]
    return sorted(normalized_items, key=_safe_sort_key)


@canonicalize.register(type)
def _(obj: type) -> Any:
    """Type/Class Handling (Structure Awareness)"""
    # Strategy A: Pydantic Model (Schema-based)
    if hasattr(obj, "model_json_schema"):  # Pydantic v2
        try:
            return ("__pydantic_v2__", canonicalize(obj.model_json_schema()))
        except Exception:
            pass
    if hasattr(obj, "schema"):  # Pydantic v1
        try:
            return ("__pydantic_v1__", canonicalize(obj.schema()))
        except Exception:
            pass

    # Strategy B: Generic Class (Structure-based)
    class_attrs = {}
    try:
        for k, v in obj.__dict__.items():
            if k.startswith("__") and k != "__annotations__":
                continue
            if callable(v):
                continue
            class_attrs[k] = v
    except AttributeError:
        pass

    return (
        "__class__",
        obj.__module__,
        obj.__qualname__,
        canonicalize(class_attrs),
    )


class Strategy(Enum):
    """
    Defines the strategy for hashing a specific argument.
    """

    DEFAULT = auto()  # Recursively canonicalize and hash (Default behavior)
    IGNORE = auto()  # Exclude from hash calculation completely
    FILE_CONTENT = auto()  # Treat as file path and hash its content (Strict)
    PATH_STAT = (
        auto()
    )  # Treat as file path and hash its metadata (Fast: path+size+mtime)


class KeyGenPolicy:
    """
    A policy object that binds to a function signature to generate cache keys
    based on argument-specific strategies.
    """

    def __init__(
        self,
        strategies: Dict[str, Strategy],
        default_strategy: Strategy = Strategy.DEFAULT,
    ):
        self.strategies = strategies
        self.default_strategy = default_strategy

    def bind(self, func: Callable[P, Any]) -> Callable[P, str]:
        """
        Creates a key generation function bound to the specific signature of `func`.
        """
        sig = inspect.signature(func)

        def _bound_keygen(*args: P.args, **kwargs: P.kwargs) -> str:
            # Bind arguments to names, applying defaults
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            items_to_hash = []

            # Iterate over arguments in definition order
            for name, val in bound.arguments.items():
                strategy = self.strategies.get(name, self.default_strategy)

                if strategy == Strategy.IGNORE:
                    continue

                elif strategy == Strategy.FILE_CONTENT:
                    # Expecting val to be a path-like string
                    items_to_hash.append(KeyGen.from_file_content(str(val)))

                elif strategy == Strategy.PATH_STAT:
                    items_to_hash.append(KeyGen.from_path_stat(str(val)))

                else:  # DEFAULT
                    items_to_hash.append(canonicalize(val))

            # Hash the accumulated list of canonical items
            return KeyGen.hash_items(items_to_hash)

        return _bound_keygen


class KeyGen:
    """
    Generates stable cache keys (SHA-256) for function inputs (Identity Layer).
    """

    # Constants for convenience usage in KeyGen.map()
    HASH = Strategy.DEFAULT
    IGNORE = Strategy.IGNORE
    FILE_CONTENT = Strategy.FILE_CONTENT
    PATH_STAT = Strategy.PATH_STAT

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
    def _default(args: tuple, kwargs: dict) -> str:
        """
        Generates a stable SHA-256 hash from function arguments using recursive canonicalization.
        This is the default legacy behavior sensitive to args/kwargs structure.
        """
        try:
            # 1. Normalize structure
            normalized = [canonicalize(args), canonicalize(kwargs)]

            # 2. Serialize to bytes
            packed = msgpack.packb(normalized)

            if packed is None:
                raise ValueError("msgpack.packb returned None")

            # 3. Hash (SHA-256)
            return hashlib.sha256(packed).hexdigest()

        except Exception:
            # Fallback
            return hashlib.sha256(str((args, kwargs)).encode()).hexdigest()

    @staticmethod
    def hash_items(items: list) -> str:
        """Helper to hash a list of canonicalized items."""
        packed = msgpack.packb(items)
        if packed is None:
            raise ValueError("msgpack.packb returned None")
        return hashlib.sha256(packed).hexdigest()

    # --- Factory Methods for Policies ---

    @classmethod
    def ignore(cls, *arg_names: str) -> KeyGenPolicy:
        """
        Creates a policy that ignores specific arguments (e.g., 'verbose', 'logger').
        """
        strategies = {name: Strategy.IGNORE for name in arg_names}
        return KeyGenPolicy(strategies, default_strategy=Strategy.DEFAULT)

    @classmethod
    def map(cls, **arg_strategies: Strategy) -> KeyGenPolicy:
        """
        Creates a policy with explicit strategies for specific arguments.
        """
        return KeyGenPolicy(arg_strategies, default_strategy=Strategy.DEFAULT)

    @classmethod
    def file_content(cls, *arg_names: str) -> KeyGenPolicy:
        """
        Creates a policy that treats specified arguments as file paths and hashes their content.
        """
        strategies = {name: Strategy.FILE_CONTENT for name in arg_names}
        return KeyGenPolicy(strategies, default_strategy=Strategy.DEFAULT)

    @classmethod
    def path_stat(cls, *arg_names: str) -> KeyGenPolicy:
        """
        Creates a policy that treats specified arguments as file paths and hashes their metadata (stat).
        """
        strategies = {name: Strategy.PATH_STAT for name in arg_names}
        return KeyGenPolicy(strategies, default_strategy=Strategy.DEFAULT)

