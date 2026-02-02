import msgpack
from typing import Any, Callable, Dict, Type, Tuple


class SerializationError(Exception):
    """Raised when an object cannot be serialized or deserialized."""

    pass


class MsgpackSerializer:
    """
    A secure and extensible serializer based on MessagePack.

    Allows registering custom types via `register()`.
    Automatically handles packing/unpacking of custom type payloads.
    """

    def __init__(self):
        # Type -> (ExtCode, Encoder)
        self._encoders: Dict[Type, Tuple[int, Callable[[Any], Any]]] = {}
        # ExtCode -> Decoder
        self._decoders: Dict[int, Callable[[Any], Any]] = {}

    def register(
        self,
        type_: Type,
        code: int,
        encoder: Callable[[Any], Any],
        decoder: Callable[[Any], Any],
    ):
        """
        Register a custom serializer for a specific type.

        The encoder must return a msgpack-serializable object (dict, list, str, int, etc.).
        The serializer will automatically pack it into bytes.
        """
        if code in self._decoders:
            raise ValueError(f"ExtCode {code} is already registered.")

        self._encoders[type_] = (code, encoder)
        self._decoders[code] = decoder

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
            # Subclass support
            for t, (c, e) in self._encoders.items():
                if isinstance(obj, t):
                    target_code, target_encoder = c, e
                    break

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
        try:
            result = msgpack.packb(obj, default=self._default_packer, use_bin_type=True)
            assert result is not None
            return result
        except Exception as e:
            if isinstance(e, SerializationError):
                raise e
            raise SerializationError("Failed to serialize object tree.") from e

    def loads(self, data: bytes) -> Any:
        try:
            return msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
        except Exception as e:
            if isinstance(e, SerializationError):
                raise e
            raise SerializationError("Failed to deserialize data.") from e
