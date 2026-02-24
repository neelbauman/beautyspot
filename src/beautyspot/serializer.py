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

    Thread Safety (No-GIL Compatible):
        This class is entirely thread-safe and avoids lock contention on the critical
        path (during serialization/deserialization). It achieves this by using:
        1.  **Copy-on-Write (CoW)** for the shared type registry (`_encoders`, `_decoders`).
            Registrations are rare, but reads happen per-node. CoW ensures readers always
            see a consistent, immutable snapshot of the registry without locking.
        2.  **Thread-Local Storage** for the LRU subclass cache (`_local.subclass_cache`).
            This eliminates lock contention completely when traversing deep object trees
            concurrently across multiple threads.

    Note:
        To prevent memory leaks in environments where types are generated dynamically
        (e.g., namedtuples, dynamic Pydantic models), subclass resolution results
        are cached using an LRU strategy with a configurable maximum size per thread.
    """

    def __init__(self, max_cache_size: int = 1024):
        # 共有レジストリ（Copy-on-Write）
        self._encoders: Dict[Type, Tuple[int, Callable[[Any], Any]]] = {}
        self._decoders: Dict[int, Callable[[Any], Any]] = {}
        
        self._max_cache_size = max_cache_size

        # スレッドローカルなLRUキャッシュ
        self._local = threading.local()

        # 書き込み（register）を直列化するためのロック
        self._write_lock = threading.Lock()

    def _get_local_cache(self) -> OrderedDict[Type, Tuple[int, Callable[[Any], Any]] | None]:
        """現在のスレッド固有のLRUキャッシュを取得（必要なら初期化）する"""
        if not hasattr(self._local, "subclass_cache"):
            self._local.subclass_cache = OrderedDict()
        return self._local.subclass_cache

    def _enforce_cache_size(self, cache: OrderedDict):
        """スレッドローカルキャッシュのサイズを制限する"""
        while len(cache) > self._max_cache_size:
            cache.popitem(last=False)

    def register(
        self,
        type_class: Type,
        code: int,
        encoder: Callable[[Any], Any],
        decoder: Callable[[Any], Any],
    ):
        if not (0 <= code <= 127):
            raise ValueError(f"ExtCode must be between 0 and 127, got {code}.")

        with self._write_lock:
            if code in self._decoders:
                raise ValueError(f"ExtCode {code} is already registered.")
            if type_class in self._encoders:
                existing_code = self._encoders[type_class][0]
                raise ValueError(
                    f"Type '{type_class.__name__}' is already registered "
                    f"(code={existing_code}). "
                    "Registering the same type twice would silently overwrite the "
                    "encoder while leaving the old decoder orphaned."
                )
            
            # Copy-on-Write (CoW)
            # 現在の辞書のコピーを作成し、新しい要素を追加
            new_encoders = self._encoders.copy()
            new_decoders = self._decoders.copy()
            
            new_encoders[type_class] = (code, encoder)
            new_decoders[code] = decoder
            
            # 参照をアトミックに差し替え
            self._encoders = new_encoders
            self._decoders = new_decoders

    # src/beautyspot/serializer.py

    def _default_packer(self, obj: Any) -> Any:
        obj_type = type(obj)
        target_code = None
        target_encoder = None

        # Lock-free read: スナップショットへの参照を取得
        current_encoders = self._encoders
        local_cache = self._get_local_cache()

        if obj_type in current_encoders:
            target_code, target_encoder = current_encoders[obj_type]
        elif obj_type in local_cache:
            cached = local_cache[obj_type]
            local_cache.move_to_end(obj_type)
            if cached is not None:
                target_code, target_encoder = cached
        else:
            # MROをスキャンして登録済みの基底クラスを探す
            for base in obj_type.__mro__:
                if base in current_encoders:
                    target_code, target_encoder = current_encoders[base]
                    local_cache[obj_type] = (target_code, target_encoder)
                    self._enforce_cache_size(local_cache)
                    break
            else:
                local_cache[obj_type] = None
                self._enforce_cache_size(local_cache)

        # Execute & Wrap
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
        # Lock-free read: スナップショットへの参照を取得
        decoder = self._decoders.get(code)

        if decoder is not None:
            try:
                intermediate = msgpack.unpackb(data, ext_hook=self._ext_hook, raw=False)
                return decoder(intermediate)
            except SerializationError:
                # Bug Fix (Bug7): 再帰的な _ext_hook から来た SerializationError を
                # 再度ラップすると、元のエラーメッセージが「CRITICAL:...」で上書きされ
                # 根本原因が隠れてしまう。そのままチェーンを保持して再送出する。
                raise
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
