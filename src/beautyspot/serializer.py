# src/beautyspot/serializer.py

import threading
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
    def dumps(self, obj: Any, /) -> bytes: ...
    def loads(self, data: bytes, /) -> Any: ...


@runtime_checkable
class TypeRegistryProtocol(Protocol):
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

    Thread Safety:
        This class is entirely thread-safe. An internal lock protects the LRU cache
        and type registry, making it safe to share a single instance across multiple
        threads or use it within asynchronous background tasks (e.g., wait=False).

    Note:
        To prevent memory leaks in environments where types are generated dynamically
        (e.g., namedtuples, dynamic Pydantic models), subclass resolution results
        are cached using an LRU strategy with a configurable maximum size.
    """

    def __init__(self, max_cache_size: int = 1024):
        self._encoders: Dict[Type, Tuple[int, Callable[[Any], Any]]] = {}
        self._decoders: Dict[int, Callable[[Any], Any]] = {}
        self._subclass_cache: OrderedDict[
            Type, Tuple[int, Callable[[Any], Any]] | None
        ] = OrderedDict()
        self._max_cache_size = max_cache_size

        # 内部状態を保護するためのスレッドロックを追加
        self._lock = threading.Lock()

    def register(
        self,
        type_class: Type,
        code: int,
        encoder: Callable[[Any], Any],
        decoder: Callable[[Any], Any],
    ):
        if not (0 <= code <= 127):
            raise ValueError(f"ExtCode must be between 0 and 127, got {code}.")
        if code in self._decoders:
            raise ValueError(f"ExtCode {code} is already registered.")

        # 登録時の状態変更をロックで保護
        with self._lock:
            self._encoders[type_class] = (code, encoder)
            self._decoders[code] = decoder
            self._subclass_cache.clear()

    def _enforce_cache_size(self):
        """
        Evict the oldest items if the cache exceeds the maximum size.
        Note: 呼び出し元で `self._lock` が取得されている前提で動作します。
        """
        while len(self._subclass_cache) > self._max_cache_size:
            self._subclass_cache.popitem(last=False)

    # src/beautyspot/serializer.py

    def _default_packer(self, obj: Any) -> Any:
        obj_type = type(obj)
        target_code = None
        target_encoder = None

        with self._lock:
            if obj_type in self._encoders:
                target_code, target_encoder = self._encoders[obj_type]
            elif obj_type in self._subclass_cache:
                cached = self._subclass_cache[obj_type]
                self._subclass_cache.move_to_end(obj_type)
                if cached is not None:
                    target_code, target_encoder = cached
            else:
                # 案3: MROをスキャンして登録済みの基底クラスを探す
                for base in obj_type.__mro__:
                    if base in self._encoders:
                        target_code, target_encoder = self._encoders[base]
                        self._subclass_cache[obj_type] = (target_code, target_encoder)
                        self._enforce_cache_size()
                        break
                else:
                    self._subclass_cache[obj_type] = None
                    self._enforce_cache_size()

        # Execute & Wrap (ロックの外側でユーザーのエンコーダ関数を実行する)
        if target_encoder:
            try:
                intermediate = target_encoder(obj)
            except Exception as e:
                raise SerializationError(
                    f"Error occurred within the custom encoder for type '{obj_type.__name__}'."
                ) from e

            try:
                payload = msgpack.packb(
                    intermediate, default=self._default_packer, use_bin_type=True
                )
                return msgpack.ExtType(target_code, payload)
            except (TypeError, SerializationError) as e:
                raise SerializationError(
                    f"Encoder for '{obj_type.__name__}' returned a value that msgpack cannot serialize.\n"
                    f"Hint: Ensure your encoder returns a primitive type (dict, list, str, int, bytes, etc.).\n"
                    f"      returned type: {type(intermediate).__name__}"
                ) from e

        raise SerializationError(
            f"Object of type '{obj_type.__name__}' is not serializable.\n"
            f"Value: {str(obj)[:200]}...\n"
            "Hint: Use `spot.register(...)` to handle this custom type."
        )

    def _ext_hook(self, code: int, data: bytes) -> Any:
        # デコード処理は状態の変更(書き込み)を伴わないため、ロックは不要です
        if code in self._decoders:
            try:
                intermediate = msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
                return self._decoders[code](intermediate)
            except Exception as e:
                raise SerializationError(
                    f"CRITICAL: Failed to decode custom type (ExtCode={code}).\n"
                    "The cached data might be corrupted or incompatible with the current decoder."
                ) from e
        return msgpack.ExtType(code, data)

    def dumps(self, obj: Any) -> bytes:
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
        try:
            return msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
        except Exception as e:
            if isinstance(e, SerializationError):
                raise e
            raise SerializationError("Failed to deserialize data.") from e
