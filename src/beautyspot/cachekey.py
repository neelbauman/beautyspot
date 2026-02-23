# src/beautyspot/cachekey.py

import hashlib
import logging
import os
import msgpack
import inspect
from enum import Enum, auto
from functools import singledispatch
from typing import Any, Union, Callable, Dict, ParamSpec

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

ReadableBuffer = Union[bytes, bytearray, memoryview]

P = ParamSpec("P")


def _safe_sort_key(obj: Any):
    """
    Helper for sorting mixed types.
    Returns a tuple (priority, type_name, str_repr) to ensure consistent ordering
    even across different types that are not natively comparable in Python 3.
    """
    if obj is None:
        return (0, "", "")
    return (1, str(type(obj)), str(obj))


# ---------------------------------------------------------------------------
# Canonicalization helpers (extracted to reduce CC of the default handler)
# ---------------------------------------------------------------------------


def _canonicalize_ndarray(obj: Any) -> tuple:
    """Numpy-like array → tagged tuple with raw bytes (efficient & exact)."""
    return ("__numpy__", obj.shape, str(obj.dtype), obj.tobytes())


def _canonicalize_instance(obj: Any) -> Any:
    """Custom object instance → canonical form via __dict__ or __slots__."""
    if hasattr(obj, "__dict__"):
        return canonicalize(obj.__dict__)
    # __slots__ path
    return [
        [k, canonicalize(getattr(obj, k))]
        for k in sorted(obj.__slots__)
        if hasattr(obj, k)
    ]


def _is_ndarray_like(obj: Any) -> bool:
    """Duck-type check for numpy-like arrays (avoids hard dependency)."""
    return hasattr(obj, "shape") and hasattr(obj, "dtype") and hasattr(obj, "tobytes")


# ---------------------------------------------------------------------------
# singledispatch canonicalize
# ---------------------------------------------------------------------------


@singledispatch
def canonicalize(obj: Any) -> Any:
    """
    Recursively converts an object into a canonical form suitable for stable
    Msgpack serialization.

    Dispatch order for unregistered types:
    1. Primitives        → return as-is
    2. Numpy-like arrays → tagged tuple via duck typing
    3. Object instances  → via __dict__ / __slots__
    4. Fallback          → str()
    """
    if obj is None or isinstance(obj, (int, float, bool, str, bytes)):
        return obj

    if _is_ndarray_like(obj):
        try:
            return _canonicalize_ndarray(obj)
        except Exception:
            pass

    if hasattr(obj, "__dict__") or hasattr(obj, "__slots__"):
        return _canonicalize_instance(obj)

    return str(obj)


@canonicalize.register(dict)
def _canonicalize_dict(obj: dict) -> list:
    """Dict → List of [k, v], sorted by key."""
    return [
        [canonicalize(k), canonicalize(v)]
        for k, v in sorted(obj.items(), key=lambda i: _safe_sort_key(i[0]))
    ]


@canonicalize.register(list)
@canonicalize.register(tuple)
def _canonicalize_sequence(obj: Union[list, tuple]) -> list:
    """List / Tuple → recursive canonicalization."""
    return [canonicalize(x) for x in obj]


@canonicalize.register(set)
@canonicalize.register(frozenset)
def _canonicalize_set(obj: Union[set, frozenset]) -> list:
    """Set / Frozenset → sorted list."""
    normalized_items = [canonicalize(x) for x in obj]
    return sorted(normalized_items, key=_safe_sort_key)


@canonicalize.register(Enum)
def _canonicalize_enum(obj: Enum) -> Any:
    """Enum member → canonical value (stable across sessions)."""
    return (
        "__enum__",
        type(obj).__module__,
        type(obj).__qualname__,
        canonicalize(obj.value),
    )


@canonicalize.register(type)
def _canonicalize_type(obj: type) -> Any:
    """Type / Class handling (structure awareness)."""
    # Pydantic v2
    if hasattr(obj, "model_json_schema"):
        try:
            return ("__pydantic_v2__", canonicalize(obj.model_json_schema()))
        except Exception:
            pass
    # Pydantic v1
    if hasattr(obj, "schema"):
        try:
            return ("__pydantic_v1__", canonicalize(obj.schema()))
        except Exception:
            pass

    # Generic class (structure-based)
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


# ---------------------------------------------------------------------------
# Optional: register numpy.ndarray directly when numpy is available
# ---------------------------------------------------------------------------

try:
    import numpy as _np

    @canonicalize.register(_np.ndarray)
    def _canonicalize_np_ndarray(obj: _np.ndarray) -> tuple:
        return _canonicalize_ndarray(obj)

except ImportError:
    pass


# ---------------------------------------------------------------------------
# Strategy & Policy
# ---------------------------------------------------------------------------


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
                    try:
                        items_to_hash.append(canonicalize(val))
                    except RecursionError:
                        logger.warning(
                            f"Circular reference detected in argument '{name}'; "
                            "falling back to str-based representation for this argument."
                        )
                        items_to_hash.append(str(val))

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

        except RecursionError:
            logger.warning(
                "Circular reference detected in arguments; falling back to str-based hash. "
                "This may cause unexpected cache misses if argument repr is not stable."
            )
            return hashlib.sha256(str((args, kwargs)).encode()).hexdigest()
        except Exception:
            logger.warning(
                "Failed to canonicalize or pack arguments; falling back to str-based hash. "
                "This may cause unexpected cache misses if argument repr is not stable."
            )
            return hashlib.sha256(str((args, kwargs)).encode()).hexdigest()

    @staticmethod
    def hash_items(items: list) -> str:
        """Helper to hash a list of canonicalized items."""
        try:
            packed = msgpack.packb(items)
            if packed is None:
                raise ValueError("msgpack.packb returned None")
            return hashlib.sha256(packed).hexdigest()
        except Exception:
            logger.warning(
                "Failed to pack canonicalized items; falling back to str-based hash. "
                "This may cause unexpected cache misses if argument repr is not stable."
            )
            return hashlib.sha256(str(items).encode()).hexdigest()

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
