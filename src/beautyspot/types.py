# src/beautyspot/types.py

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Optional


@dataclass(frozen=True)
class SaveErrorContext:
    """
    キャッシュ保存処理 (wait=False/True) が失敗した際に、
    エラーハンドラーへ渡されるコンテキスト情報です。

    Attributes:
        func_name: キャッシュ保存対象となった関数の名前
        cache_key: 生成されたキャッシュキー (SHA-256)
        input_id: 入力引数から生成された識別子
        version: キャッシュのバージョン指定文字列
        content_type: 保存データのMIMEタイプなどのコンテンツタイプ文字列
        save_blob: Blobストレージへの保存が指定/判定されていたか
        expires_at: 計算されたキャッシュの有効期限
        result_type: キャッシュしようとした戻り値の型名
        result_size: キャッシュしようとした戻り値のメモリサイズ概算（取得可能な場合のみ）
    """

    func_name: str
    cache_key: str
    input_id: str
    version: Optional[str]
    content_type: Optional[str]
    save_blob: Optional[bool]
    expires_at: Optional[datetime]
    result_type: str
    result_size: Optional[int]


@dataclass(frozen=True)
class HookContextBase:
    """すべてのフックに共通する基本コンテキスト情報。

    Attributes:
        kwargs: 関数に渡されたキーワード引数。読み取り専用の ``MappingProxyType``
            として提供されるため、フック内での変更はできません。
    """

    func_name: str
    input_id: str
    cache_key: str
    args: tuple
    kwargs: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Bug Fix (D4): frozen=True でも dict の内容は変更可能なため、
        # MappingProxyType でラップしてフックによる意図しない変更を防ぐ。
        if not isinstance(self.kwargs, MappingProxyType):
            object.__setattr__(self, "kwargs", MappingProxyType(self.kwargs))


@dataclass(frozen=True)
class PreExecuteContext(HookContextBase):
    """関数実行前、またはキャッシュ確認前に渡されるコンテキスト。"""

    pass


@dataclass(frozen=True)
class CacheHitContext(HookContextBase):
    """キャッシュから正常に結果が取得された際に渡されるコンテキスト。"""

    result: Any
    version: Optional[str]


@dataclass(frozen=True)
class CacheMissContext(HookContextBase):
    """キャッシュミスとなり、元の関数が実行された後に渡されるコンテキスト。"""

    result: Any
    version: Optional[str]
