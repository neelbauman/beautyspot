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
        """元の関数が実行され結果が得られた直後に呼び出されます。

        .. note::
            このフックは関数実行の直後、キャッシュへの**永続化完了前**に呼ばれます。
            ``save_sync=False`` の場合、フック呼び出し後にバックグラウンドで
            保存が失敗する可能性があります。保存の成否を確認したい場合は
            ``on_background_error`` コールバックを使用してください。
        """


def _wrap_with_lock(fn: Callable[..., Any]) -> Callable[..., Any]:
    """インスタンスの ``_lock`` で ``fn`` を保護するラッパーを返す。"""

    @functools.wraps(fn)
    def wrapper(self: Any, context: Any) -> None:
        with self._lock:
            fn(self, context)

    return wrapper


class ThreadSafeHookBase(HookBase):
    """スレッドセーフなフックベースクラス。

    内部で ``threading.RLock`` を使用し、各コールバックの排他制御を行います。
    ``HookBase`` と同じメソッド名 (``pre_execute``, ``on_cache_hit``,
    ``on_cache_miss``) をオーバーライドするだけで使用できます。

    .. note::
        再入可能ロック (``RLock``) を使用しているため、
        サブクラスが ``super()`` 経由で親の同名メソッドを呼び出しても
        デッドロックしません。

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
        # Bug Fix: Lock → RLock
        # サブクラスが super() 経由で同名のラップ済みメソッドを呼び出すと、
        # 同一スレッドが同じロックを再取得しようとしてデッドロックする。
        # RLock (再入可能ロック) を使用することでこれを防ぐ。
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        # super().__init__() が呼ばれなかった場合の安全網。
        # _lock が未初期化のまま _wrap_with_lock から参照されると AttributeError になるため、
        # __getattr__ (通常の属性検索で見つからない場合のみ呼ばれる) でフォールバック生成する。
        if name == "_lock":
            lock = threading.RLock()
            object.__setattr__(self, "_lock", lock)
            return lock
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )
