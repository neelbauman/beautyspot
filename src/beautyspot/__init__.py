# src/beautyspot/__init__.py 
from importlib.metadata import version, PackageNotFoundError
from .core import Spot as _Spot, SpotOptions
from .cachekey import KeyGen
from .storage import LocalStorage, S3Storage
from .serializer import SerializationError
from .types import ContentType

from typing import Optional, Any
from .db import TaskDB
from .storage import BlobStorageBase
from .serializer import SerializerProtocol

try:
    __version__ = version("beautyspot")
except PackageNotFoundError:
    # 開発中や未インストールの状態
    __version__ = "0.0.0+unknown"


# ユーザーが使う "Spot" を定義
class Spot(_Spot):
    """
    Beautyspotのメインエントリポイント。
    """
    def __init__(
        self,
        name: str,
        # --- 1. 依存オブジェクト (Explicit) ---
        db: Optional[TaskDB] = None,
        serializer: Optional[SerializerProtocol] = None,
        storage: Optional[BlobStorageBase] = None,
        
        # --- 2. オプション設定 (Explicit for help()) ---
        tpm: int = 10000,
        io_workers: int = 4,
        blob_warning_threshold: int = 1024 * 1024,
        executor: Optional[Any] = None,
        default_save_blob: bool = False,
        default_version: Optional[str] = None,
        default_content_type: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        
        # --- Orchestration: デフォルト実装の注入 ---
        
        # 1. DBの解決
        from beautyspot.db import SQLiteTaskDB
        resolved_db = db or SQLiteTaskDB(f".beautyspot/{name}.db")

        # 2. Serializerの解決
        from beautyspot.serializer import MsgpackSerializer
        resolved_ser = serializer or MsgpackSerializer()

        # 3. Storageの解決
        from beautyspot.storage import LocalStorage
        resolved_stg = storage or LocalStorage(".beautyspot/blobs")

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
            **kwargs, # type: ignore
        }

        # --- コアロジックの起動 ---
        # explicitな引数として core に渡す
        super().__init__(
            name=name,
            db=resolved_db,
            serializer=resolved_ser,
            storage=resolved_stg,
            **options,
        )

__all__ = [
    "Spot",
    "KeyGen",
    "LocalStorage",
    "S3Storage",
    "ContentType",
    "SerializationError",
]
