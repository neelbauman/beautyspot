# src/beautyspot/serializer.py

import msgpack
from collections import OrderedDict
from typing import (
    Any,
    Callable,
    Dict,
    Type,
    TypeVar,
    Tuple,
    Protocol,
    runtime_checkable,
)
from beautyspot.exceptions import SerializationError

T = TypeVar("T")


@runtime_checkable
class SerializerProtocol(Protocol):
    """
    Protocol for custom serializers.
    Any object implementing these methods can be used as a serializer.
    """

    def dumps(self, obj: Any, /) -> bytes: ...

    def loads(self, data: bytes, /) -> Any: ...


@runtime_checkable
class TypeRegistryProtocol(Protocol):
    """
    Protocol for serializers that support custom type registration.
    """

    def register(
        self,
        type_class: Type[Any],
        code: int,
        encoder: Callable[[Any], Any],
        decoder: Callable[[Any], Any],
    ) -> None: ...


class MsgpackSerializer(SerializerProtocol, TypeRegistryProtocol):
    """
    A secure and extensible serializer based on MessagePack.

    Allows registering custom types via `register()`.
    Automatically handles packing/unpacking of custom type payloads.

    Note:
        To prevent memory leaks in environments where types are generated dynamically
        (e.g., namedtuples, dynamic Pydantic models), subclass resolution results 
        are cached using an LRU strategy with a configurable maximum size.
    """

    def __init__(self, max_cache_size: int = 1024):
        # Type -> (ExtCode, Encoder)
        self._encoders: Dict[Type, Tuple[int, Callable[[Any], Any]]] = {}
        # ExtCode -> Decoder
        self._decoders: Dict[int, Callable[[Any], Any]] = {}
        # Subclass lookup cache: Type -> (ExtCode, Encoder) or None
        self._subclass_cache: OrderedDict[Type, Tuple[int, Callable[[Any], Any]] | None] = OrderedDict()
        self._max_cache_size = max_cache_size

    def register(
        self,
        type_class: Type,
        code: int,
        encoder: Callable[[Any], Any],
        decoder: Callable[[Any], Any],
    ):
        """
        Register a custom serializer for a specific type.

        The encoder should return a Python object that is natively serializable by MessagePack
        (e.g., dict, list, str, int, bytes). The serializer will then pack this intermediate
        representation into bytes.

        Args:
            type_class (Type): The Python class to register (e.g., `pd.DataFrame`).
            code (int): A unique integer ID for the MessagePack ExtType tag.
                        Must be between 0 and 127 (inclusive).
            encoder (Callable): Function converting `type_` -> serializable object.
            decoder (Callable): Function converting serializable object -> `type_`.

        Raises:
            ValueError: If the `code` is already registered.
        """
        if not (0 <= code <= 127):
            raise ValueError(f"ExtCode must be between 0 and 127, got {code}.")
        if code in self._decoders:
            raise ValueError(f"ExtCode {code} is already registered.")

        self._encoders[type_class] = (code, encoder)
        self._decoders[code] = decoder
        self._subclass_cache.clear()

    def _enforce_cache_size(self):
        """Evict the oldest items if the cache exceeds the maximum size."""
        while len(self._subclass_cache) > self._max_cache_size:
            self._subclass_cache.popitem(last=False)

    def _default_packer(self, obj: Any) -> Any:
        """
        [Wrapper Logic]
        Intercepts the user's encoder result and packs it into bytes.
        """
        obj_type = type(obj)

        # 1. Resolve Encoder
        target_code = None
        target_encoder = None

        if obj_type in self._encoders:
            target_code, target_encoder = self._encoders[obj_type]
        else:
            # Subclass support with cache
            if obj_type in self._subclass_cache:
                cached = self._subclass_cache[obj_type]
                # LRUの更新: アクセスされたものを最新として扱う
                self._subclass_cache.move_to_end(obj_type)

                if cached is not None:
                    target_code, target_encoder = cached
            else:
                for t, (c, e) in self._encoders.items():
                    if isinstance(obj, t):
                        target_code, target_encoder = c, e
                        self._subclass_cache[obj_type] = (c, e)
                        self._enforce_cache_size()
                        break
                else:
                    self._subclass_cache[obj_type] = None
                    self._enforce_cache_size()

        # 2. Execute & Wrap
        if target_encoder:
            # Step A: Run user encoder
            try:
                intermediate = target_encoder(obj)
            except Exception as e:
                # User code failed
                raise SerializationError(
                    f"Error occurred within the custom encoder for type '{obj_type.__name__}'."
                ) from e

            # Step B: Pack intermediate result
            try:
                # Wrapper logic: Intermediate -> Packed Bytes (Payload)
                payload = msgpack.packb(
                    intermediate, default=self._default_packer, use_bin_type=True
                )
                return msgpack.ExtType(target_code, payload)
            except (TypeError, SerializationError) as e:
                # msgpack raises TypeError for invalid types,
                # or SerializationError (recursive) if nested content fails.
                raise SerializationError(
                    f"Encoder for '{obj_type.__name__}' returned a value that msgpack cannot serialize.\n"
                    f"Hint: Ensure your encoder returns a primitive type (dict, list, str, int, bytes, etc.).\n"
                    f"      returned type: {type(intermediate).__name__}"
                ) from e

        # 3. Fallback for unknown types
        raise SerializationError(
            f"Object of type '{obj_type.__name__}' is not serializable.\n"
            f"Value: {str(obj)[:200]}...\n"
            "Hint: Use `spot.register(...)` to handle this custom type."
        )

    def _ext_hook(self, code: int, data: bytes) -> Any:
        """
        [Wrapper Logic]
        Unpacks the payload before passing it to the user's decoder.
        Strictly raises SerializationError on failure.
        """
        if code in self._decoders:
            try:
                # Wrapper logic: Packed Bytes -> Intermediate (e.g. Dict)
                intermediate = msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)

                # User function: Intermediate -> Object
                return self._decoders[code](intermediate)
            except Exception as e:
                # Critical failure
                raise SerializationError(
                    f"CRITICAL: Failed to decode custom type (ExtCode={code}).\n"
                    "The cached data might be corrupted or incompatible with the current decoder."
                ) from e

        # Unknown code: keep as ExtType (safe default)
        return msgpack.ExtType(code, data)

    def dumps(self, obj: Any) -> bytes:
        """
        Serialize a Python object into MessagePack bytes.

        Recursively handles custom types registered via `register()`.

        Returns:
            bytes: The packed binary data.

        Raises:
            SerializationError: If the object contains types that cannot be serialized.
        """
        try:
            result = msgpack.packb(obj, default=self._default_packer, use_bin_type=True)
            if result is None:
                raise SerializationError("msgpack.packb returned None unexpectedly.")
            return result
        except Exception as e:
            if isinstance(e, SerializationError):
                raise e
            raise SerializationError("Failed to serialize object tree.") from e

    def loads(self, data: bytes) -> Any:
        """
        Deserialize MessagePack bytes back into a Python object.

        Automatically detects and decodes custom types using registered decoders.

        Args:
            data (bytes): The packed binary data.

        Returns:
            Any: The reconstructed Python object.

        Raises:
            SerializationError: If the data is corrupted or a custom type decoder fails.
        """
        try:
            return msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
        except Exception as e:
            if isinstance(e, SerializationError):
                raise e
            raise SerializationError("Failed to deserialize data.") from e
