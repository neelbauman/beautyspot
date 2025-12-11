# src/beautyspot/serializer.py

import msgpack
from typing import Any, Callable, Dict, Type, Tuple


class SerializationError(Exception):
    """Raised when an object cannot be serialized."""
    pass


class MsgpackSerializer:
    """
    A secure and extensible serializer based on MessagePack.

    Allows registering custom types via `register()`.
    Unknown types will raise a descriptive SerializationError instead of a generic TypeError.
    """

    def __init__(self):
        # Type -> (ExtCode, Encoder)
        self._encoders: Dict[Type, Tuple[int, Callable[[Any], bytes]]] = {}
        # ExtCode -> Decoder
        self._decoders: Dict[int, Callable[[bytes], Any]] = {}

    def register(
        self,
        type_: Type,
        code: int,
        encoder: Callable[[Any], bytes],
        decoder: Callable[[bytes], Any],
    ):
        """
        Register a custom serializer for a specific type.

        Args:
            type_: The class to handle.
            code: Unique integer ID (0-127) for this type.
            encoder: Function that converts obj -> bytes.
            decoder: Function that converts bytes -> obj.
        """
        if code in self._decoders:
            raise ValueError(f"ExtCode {code} is already registered.")

        self._encoders[type_] = (code, encoder)
        self._decoders[code] = decoder

    def _default_packer(self, obj: Any) -> Any:
        """Hook for objects not handled by default msgpack types."""
        # Check registered types
        # Note: We iterate to support subclasses if necessary,
        # though exact match is faster. Here we use exact/isinstance check order.
        obj_type = type(obj)
        if obj_type in self._encoders:
            code, encoder = self._encoders[obj_type]
            return msgpack.ExtType(code, encoder(obj))

        # Fallback: check isinstance for broader types (slower but flexible)
        for t, (code, encoder) in self._encoders.items():
            if isinstance(obj, t):
                return msgpack.ExtType(code, encoder(obj))

        # Helpful Error Message
        raise SerializationError(
            f"Object of type '{obj_type.__name__}' is not serializable.\n"
            f"Value: {str(obj)[:200]}...\n"
            "Hint: Use `project.register_type(...)` to handle this custom type."
        )

    def _ext_hook(self, code: int, data: bytes) -> Any:
        """Hook for deserializing ExtTypes."""
        if code in self._decoders:
            return self._decoders[code](data)
        # If we don't know the code, return ExtType to preserve data (safe default)
        return msgpack.ExtType(code, data)

    def dumps(self, obj: Any) -> bytes:
        return msgpack.packb(obj, default=self._default_packer, use_bin_type=True)

    def loads(self, data: bytes) -> Any:
        return msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
