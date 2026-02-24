# src/beautyspot/__init__.py

import logging
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Optional, Callable
from concurrent.futures import Executor

from beautyspot.core import Spot as _Spot

from beautyspot.types import (
    SaveErrorContext,
    PreExecuteContext,
    CacheHitContext,
    CacheMissContext,
)
from beautyspot.cachekey import KeyGen
from beautyspot.lifecycle import LifecyclePolicy, Rule, Retention
from beautyspot.limiter import TokenBucket, LimiterProtocol
from beautyspot.content_types import ContentType
from beautyspot.db import TaskDBBase, SQLiteTaskDB
from beautyspot.exceptions import (
    BeautySpotError,
    CacheCorruptedError,
    SerializationError,
    ConfigurationError,
)
from beautyspot.storage import (
    BlobStorageBase,
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


def Spot(
    name: str,
    db: Optional[TaskDBBase] = None,
    serializer: Optional[SerializerProtocol] = None,
    limiter: Optional[LimiterProtocol] = None,
    storage_backend: Optional[BlobStorageBase] = None,
    storage_policy: Optional[StoragePolicyProtocol] = None,
    executor: Optional[Executor] = None,
    # --- Configuration Options ---
    lifecycle_policy: Optional[LifecyclePolicy] = None,
    eviction_rate: float = 0.0,
    blob_warning_threshold: int = 1024 * 1024,
    default_save_blob: bool = False,
    tpm: int = 10000,
    io_workers: int = 4,
    default_version: Optional[str] = None,
    default_content_type: Optional[str] = None,
    default_wait: bool = True,
    drain_timeout: float = 5.0,
    drain_poll_interval: float = 0.5,
    on_background_error: Optional[Callable[[Exception, SaveErrorContext], None]] = None,
) -> _Spot:
    """
    Beautyspotのメインエントリポイント（Factory Function）。
    依存関係の解決とデフォルト設定の適用を行います。
    """

    # 0. デフォルトパス使用時のみワークスペースをセットアップ
    #    カスタムパスを渡した場合、不要な .beautyspot/ を作らない
    _default_workspace = Path(".beautyspot")
    if db is None or storage_backend is None:
        _Spot._setup_workspace(_default_workspace)

    # 1. コンポーネントの解決 (DI)
    resolved_db = db or SQLiteTaskDB(_default_workspace / f"{name}.db")
    resolved_ser = serializer or MsgpackSerializer()
    resolved_stg = storage_backend or LocalStorage(_default_workspace / "blobs" / name)
    resolved_limiter = limiter or TokenBucket(tokens_per_minute=tpm)

    # 2. Storage Policy の解決 (Factory側でロジックを担保)
    #    ユーザーがポリシーを直接渡した場合はそれを優先
    resolved_policy: StoragePolicyProtocol

    if storage_policy is not None:
        resolved_policy = storage_policy
    elif default_save_blob:
        # レガシーフラグ互換: 常にBlob保存
        resolved_policy = AlwaysBlobPolicy()
    else:
        # デフォルト動作: 警告のみ (ロガー注入)
        logger = logging.getLogger("beautyspot")
        resolved_policy = WarningOnlyPolicy(
            warning_threshold=blob_warning_threshold, logger=logger
        )

    # 3. Coreへ渡すオプションの整理
    # SpotOptionsの型定義に合わせてパッキングしますが、
    # core.Spot が受け取らないレガシー引数はここでは渡さないように注意します。

    return _Spot(
        name=name,
        db=resolved_db,
        serializer=resolved_ser,
        storage_backend=resolved_stg,
        storage_policy=resolved_policy,
        limiter=resolved_limiter,
        # その他のオプション
        lifecycle_policy=lifecycle_policy,
        eviction_rate=eviction_rate,
        executor=executor,
        io_workers=io_workers,
        default_version=default_version,
        default_content_type=default_content_type,
        default_wait=default_wait,
        drain_timeout=drain_timeout,
        drain_poll_interval=drain_poll_interval,
        on_background_error=on_background_error,
    )


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
    # --- Protocols & Base Classes (for custom implementations) ---
    "TaskDBBase",
    "BlobStorageBase",
    "SerializerProtocol",
    "StoragePolicyProtocol",
    "LimiterProtocol",
    # --- Default Implementations ---
    "SQLiteTaskDB",
    "LocalStorage",
    "MsgpackSerializer",
    "TokenBucket",
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
