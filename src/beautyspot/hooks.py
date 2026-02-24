# src/beautyspot/hooks.py

import inspect
import functools
import threading
from collections.abc import Callable
from typing import Any

from beautyspot.types import PreExecuteContext, CacheHitContext, CacheMissContext


class HookBase:
    """
    beautyspotのタスク実行ライフサイクルに介入するためのベースクラス。
    ユーザーはこのクラスを継承し、必要なメソッドのみをオーバーライドして使用します。

    Note:
        このクラスはスレッドセーフではありません。複数のスレッドから同時に
        同じフックインスタンスが呼ばれる可能性がある場合は、
        ``ThreadSafeHookBase`` を使用してください。
    """

    def pre_execute(self, context: PreExecuteContext) -> None:
        """関数実行（およびキャッシュ確認）の直前に呼び出されます。"""

    def on_cache_hit(self, context: CacheHitContext) -> None:
        """キャッシュから値が正常に取得され、元の関数実行がスキップされた直後に呼び出されます。"""

    def on_cache_miss(self, context: CacheMissContext) -> None:
        """キャッシュが存在せず、元の関数が実行され結果が得られた直後に呼び出されます。"""


def _wrap_with_lock(fn: Callable[..., Any]) -> Callable[..., Any]:
    """インスタンスの ``_lock`` で ``fn`` を保護するラッパーを返す。"""

    @functools.wraps(fn)
    def wrapper(self: Any, context: Any) -> None:
        with self._lock:
            fn(self, context)

    return wrapper


class ThreadSafeHookBase(HookBase):
    """スレッドセーフなフックベースクラス。

    内部で ``threading.Lock`` を使用し、各コールバックの排他制御を行います。
    ``HookBase`` と同じメソッド名 (``pre_execute``, ``on_cache_hit``,
    ``on_cache_miss``) をオーバーライドするだけで使用できます。

    Example::

        class MyHook(ThreadSafeHookBase):
            def __init__(self):
                super().__init__()
                self.count = 0

            def pre_execute(self, context):
                self.count += 1  # ロックは自動適用される
    """

    _HOOK_METHODS: frozenset[str] = frozenset(
        name
        for name, _ in inspect.getmembers(HookBase, predicate=inspect.isfunction)
        if not name.startswith("__")
    )

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for name in ThreadSafeHookBase._HOOK_METHODS:
            if name in cls.__dict__:
                setattr(cls, name, _wrap_with_lock(cls.__dict__[name]))

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        # super().__init__() が呼ばれなかった場合の安全網。
        # _lock が未初期化のまま _wrap_with_lock から参照されると AttributeError になるため、
        # __getattr__ (通常の属性検索で見つからない場合のみ呼ばれる) でフォールバック生成する。
        if name == "_lock":
            lock = threading.Lock()
            object.__setattr__(self, "_lock", lock)
            return lock
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )
