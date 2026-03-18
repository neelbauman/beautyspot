# src/beautyspot/__init__.py

import logging
import warnings
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Any, Optional, Callable

from beautyspot.core import Spot as _Spot
from beautyspot.cache import CacheManager as _CacheManager

from beautyspot.types import (
    SaveErrorContext,
    PreExecuteContext,
    CacheHitContext,
    CacheMissContext,
)
from beautyspot.cachekey import KeyGen
from beautyspot.lifecycle import LifecyclePolicy, Rule, Retention
from beautyspot.limiter import Gcra, LimiterProtocol
from beautyspot.content_types import ContentType
from beautyspot.db import TaskDBBase, TaskDBCore, TaskDBMaintenable, SQLiteTaskDB
from beautyspot.exceptions import (
    BeautySpotError,
    CacheCorruptedError,
    SerializationError,
    ConfigurationError,
    ValidationError,
    IncompatibleProviderError,
)
from beautyspot.storage import (
    BlobStorageBase,
    BlobStorageCore,
    BlobStorageMaintenable,
    LocalStorage,
    StoragePolicyProtocol,
    WarningOnlyPolicy,
    ThresholdStoragePolicy,
    AlwaysBlobPolicy,
)
from beautyspot.serializer import SerializerProtocol, MsgpackSerializer
from beautyspot.hooks import HookBase, ThreadSafeHookBase

try:
    __version__ = version("beautyspot")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


_UNSET: Any = object()


def _resolve_renamed(
    new_val: Any,
    old_val: Any,
    new_name: str,
    old_name: str,
    default: Any,
) -> Any:
    """新旧パラメータ名を解決するヘルパー。旧名使用時は DeprecationWarning を発行する。"""
    if new_val is not _UNSET and old_val is not _UNSET:
        raise IncompatibleProviderError(
            f"Cannot specify both '{new_name}' and deprecated '{old_name}'."
        )
    if old_val is not _UNSET:
        warnings.warn(
            f"'{old_name}' is deprecated, use '{new_name}' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        return old_val
    if new_val is not _UNSET:
        return new_val
    return default


def Spot(
    name: str,
    db: Optional[TaskDBMaintenable] = None,
    serializer: Optional[SerializerProtocol] = None,
    limiter: Optional[LimiterProtocol] = None,
    storage_backend: Optional[BlobStorageMaintenable] = None,
    storage_policy: Optional[StoragePolicyProtocol] = None,
    cache: Optional[_CacheManager] = None,
    # --- Configuration Options ---
    lifecycle_policy: Optional[LifecyclePolicy] = None,
    gc_probability: float = 0.0,
    blob_warning_threshold: int = 1024 * 1024,
    save_blob: bool = False,
    tokens_per_minute: int = 10000,
    save_sync: bool = True,
    flush_timeout: float = 5.0,
    flush_poll_interval: float = 0.5,
    on_save_error: Optional[Callable[[BaseException, SaveErrorContext], None]] = None,
    # --- Deprecated aliases (backward compat) ---
    eviction_rate: Any = _UNSET,
    tpm: Any = _UNSET,
    drain_timeout: Any = _UNSET,
    drain_poll_interval: Any = _UNSET,
    on_background_error: Any = _UNSET,
) -> _Spot:
    """
    Beautyspotのメインエントリポイント（Factory Function）。
    依存関係の解決とデフォルト設定の適用を行います。
    """

    # 0. 非推奨パラメータの解決
    effective_gc_prob: float = _resolve_renamed(
        gc_probability if gc_probability != 0.0 else _UNSET,
        eviction_rate, "gc_probability", "eviction_rate", 0.0,
    )
    effective_tpm: int = _resolve_renamed(
        tokens_per_minute if tokens_per_minute != 10000 else _UNSET,
        tpm, "tokens_per_minute", "tpm", 10000,
    )
    effective_flush_timeout: float = _resolve_renamed(
        flush_timeout if flush_timeout != 5.0 else _UNSET,
        drain_timeout, "flush_timeout", "drain_timeout", 5.0,
    )
    effective_flush_poll: float = _resolve_renamed(
        flush_poll_interval if flush_poll_interval != 0.5 else _UNSET,
        drain_poll_interval, "flush_poll_interval", "drain_poll_interval", 0.5,
    )
    effective_on_save_error = _resolve_renamed(
        on_save_error if on_save_error is not None else _UNSET,
        on_background_error, "on_save_error", "on_background_error", None,
    )

    # 1. デフォルトパス使用時のみワークスペースをセットアップ
    _default_workspace = Path(".beautyspot")

    # 2. コンポーネントの解決 (DI)
    resolved_db = db or SQLiteTaskDB(_default_workspace / f"{name}.db")
    resolved_ser = serializer or MsgpackSerializer()
    resolved_stg = storage_backend or LocalStorage(_default_workspace / "blobs" / name)
    resolved_limiter = limiter or Gcra(tokens_per_minute=effective_tpm)

    # 3. Storage Policy の解決
    resolved_policy: StoragePolicyProtocol
    if storage_policy is not None:
        resolved_policy = storage_policy
    elif save_blob:
        resolved_policy = AlwaysBlobPolicy()
    else:
        logger = logging.getLogger("beautyspot")
        resolved_policy = WarningOnlyPolicy(
            warning_threshold=blob_warning_threshold, logger=logger
        )

    # 4. CacheManager の組み立て (Composition)
    resolved_cache = cache or _CacheManager(
        db=resolved_db,
        storage=resolved_stg,
        serializer=resolved_ser,
        storage_policy=resolved_policy,
        lifecycle_policy=lifecycle_policy,
    )

    # 5. Core Spot の生成
    # _owns_db: ファクトリ関数で内部的に DB を生成した場合のみ True。
    # GC 時のファイナライザが DB シャットダウンするかを決定する。
    # コンストラクタ引数で渡すことで、ファイナライザのキャプチャタイミング問題を防ぐ。
    spot = _Spot(
        name=name,
        cache=resolved_cache,
        limiter=resolved_limiter,
        # その他のオプション
        save_sync=save_sync,
        gc_probability=effective_gc_prob,
        flush_timeout=effective_flush_timeout,
        flush_poll_interval=effective_flush_poll,
        on_save_error=effective_on_save_error,
        _owns_db=(db is None),
    )

    return spot


# isinstance(spot, bs.SpotType) のための型エクスポート
SpotType: type[_Spot] = _Spot

__all__ = [
    # --- Core ---
    "Spot",
    "SpotType",
    "KeyGen",
    "ContentType",
    "SaveErrorContext",
    # --- Exceptions ---
    "BeautySpotError",
    "CacheCorruptedError",
    "SerializationError",
    "ConfigurationError",
    "ValidationError",
    "IncompatibleProviderError",
    # --- Protocols & Base Classes (for custom implementations) ---
    "TaskDBCore",
    "TaskDBMaintenable",
    "TaskDBBase",
    "BlobStorageCore",
    "BlobStorageMaintenable",
    "BlobStorageBase",
    "SerializerProtocol",
    "StoragePolicyProtocol",
    "LimiterProtocol",
    # --- Default Implementations ---
    "SQLiteTaskDB",
    "LocalStorage",
    "MsgpackSerializer",
    "Gcra",
    "ThresholdStoragePolicy",
    "WarningOnlyPolicy",
    "AlwaysBlobPolicy",
    # --- Lifecycle ---
    "LifecyclePolicy",
    "Rule",
    "Retention",
    # --- Hooks ---
    "HookBase",
    "ThreadSafeHookBase",
    "PreExecuteContext",
    "CacheHitContext",
    "CacheMissContext",
]
