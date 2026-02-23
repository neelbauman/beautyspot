# src/beautyspot/hooks.py

from beautyspot.types import PreExecuteContext, CacheHitContext, CacheMissContext

class HookBase:
    """
    beautyspotのタスク実行ライフサイクルに介入するためのベースクラス。
    ユーザーはこのクラスを継承し、必要なメソッドのみをオーバーライドして使用します。
    """
    
    def pre_execute(self, context: PreExecuteContext) -> None:
        """関数実行（およびキャッシュ確認）の直前に呼び出されます。"""
        pass

    def on_cache_hit(self, context: CacheHitContext) -> None:
        """キャッシュから値が正常に取得され、元の関数実行がスキップされた直後に呼び出されます。"""
        pass

    def on_cache_miss(self, context: CacheMissContext) -> None:
        """キャッシュが存在せず、元の関数が実行され結果が得られた直後に呼び出されます。"""
        pass
