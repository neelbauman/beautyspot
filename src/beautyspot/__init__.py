# src/beautyspot/__init__.py 
from importlib.metadata import version, PackageNotFoundError
from typing import Optional, Any

from beautyspot.core import Spot as _Spot, SpotOptions
from beautyspot.cachekey import KeyGen
from beautyspot.serializer import SerializationError
from beautyspot.content_types import ContentType
from beautyspot.db import TaskDB
from beautyspot.storage import BlobStorageBase
from beautyspot.serializer import SerializerProtocol

from beautyspot.db import SQLiteTaskDB
from beautyspot.serializer import MsgpackSerializer
from beautyspot.storage import LocalStorage

try:
    __version__ = version("beautyspot")
except PackageNotFoundError:
    # 開発中や未インストールの状態
    __version__ = "0.0.0+unknown"


# ユーザーが使う "Spot" を定義
def Spot(
    name: str,
    db: Optional[TaskDB] = None,
    serializer: Optional[SerializerProtocol] = None,
    storage: Optional[BlobStorageBase] = None,
    tpm: int = 10000,
    io_workers: int = 4,
    blob_warning_threshold: int = 1024 * 1024,
    executor: Optional[Any] = None,
    default_save_blob: bool = False,
    default_version: Optional[str] = None,
    default_content_type: Optional[str] = None,
    default_wait: bool = True,
    **kwargs: Any
) -> _Spot:
    """
    Beautyspotのメインエントリポイント。
    """
    # --- Orchestration: デフォルト実装の注入 ---
    
    # 1. DBの解決
    resolved_db = db or SQLiteTaskDB(f".beautyspot/{name}.db")

    # 2. Serializerの解決
    resolved_ser = serializer or MsgpackSerializer()

    # 3. Storageの解決
    resolved_stg = storage or LocalStorage(f".beautyspot/blobs/{name}/")

    # --- オプションのパッキングと型チェック ---
    # types.py の SpotOptions を使って、引数の整合性を（静的解析上で）担保する
    options: SpotOptions = {
        "tpm": tpm,
        "io_workers": io_workers,
        "blob_warning_threshold": blob_warning_threshold,
        "executor": executor,
        "default_save_blob": default_save_blob,
        "default_version": default_version,
        "default_content_type": default_content_type,
        "default_wait": default_wait,
        **kwargs, # type: ignore
    }

    # explicitな引数として core に渡す
    return _Spot(
        name=name,
        db=resolved_db,
        serializer=resolved_ser,
        storage=resolved_stg,
        **options,
    )

__all__ = [
    "Spot",
    "KeyGen",
    "ContentType",
    "SQLiteTaskDB",
    "LocalStorage",
    "MsgpackSerializer",
    "SerializationError",
]
