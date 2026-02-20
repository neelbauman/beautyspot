# src/beautyspot/types.py 

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

@dataclass(frozen=True)
class SaveErrorContext:
    """
    バックグラウンドでのキャッシュ保存処理 (wait=False) が失敗した際に、
    エラーハンドラーへ渡されるコンテキスト情報です。

    Attributes:
        func_name: キャッシュ保存対象となった関数の名前
        cache_key: 生成されたキャッシュキー (SHA-256)
        input_id: 入力引数から生成された識別子
        version: キャッシュのバージョン指定文字列
        content_type: 保存データのMIMEタイプなどのコンテンツタイプ文字列
        save_blob: Blobストレージへの保存が指定/判定されていたか
        expires_at: 計算されたキャッシュの有効期限
        result: キャッシュしようとした実際の戻り値のオブジェクト
        
    Warning:
        `result` には評価済みのオブジェクトがそのまま格納されます。
        巨大なデータ（例: 数GBのDataFrameやテンソル）を返す関数の場合、
        このエラーコンテキストをグローバルなリストや長寿命のオブジェクトに
        保持し続けると、メモリリークの原因となる可能性があります。
        エラーハンドラー内でのログ出力や一時的な検査のみに留めることを強く推奨します。
    """
    func_name: str
    cache_key: str
    input_id: str
    version: Optional[str]
    content_type: Optional[str]
    save_blob: Optional[bool]
    expires_at: Optional[datetime]
    result: Any
