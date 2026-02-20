# tests/typing/test_inference.py

"""
Tests for type inference using static analysis.
Run this file with pyright, not pytest.
"""

from typing import assert_type, Any
import beautyspot
from beautyspot import KeyGen

spot = beautyspot.Spot("test_spot")


# --- テスト用のダミー関数 ---
def int_to_str(x: int) -> str:
    return str(x)


def str_to_int(x: str) -> int:
    return len(x)


# -----------------------------------------------------------------------------
# Case 1: @spot.mark (Decorator)
# -----------------------------------------------------------------------------
@spot.mark
def marked_func(a: int, b: int) -> int:
    return a + b


assert_type(marked_func(1, 2), int)


# -----------------------------------------------------------------------------
# Case 2: spot.cached_run (Single Function)
# -----------------------------------------------------------------------------
with spot.cached_run(int_to_str) as task_single:
    assert_type(task_single(10), str)


# -----------------------------------------------------------------------------
# Case 3: spot.cached_run (Multiple Functions / Tuple Unpacking)
# -----------------------------------------------------------------------------
with spot.cached_run(int_to_str, str_to_int) as (task_1, task_2):
    assert_type(task_1(42), str)
    assert_type(task_2("hello"), int)


# -----------------------------------------------------------------------------
# Case 4: ParamSpec & Generic (Generics Preservation)
# -----------------------------------------------------------------------------
@spot.mark
def marked_identity[T](x: T) -> T:
    return x


assert_type(marked_identity(10), int)
assert_type(marked_identity("foo"), str)


# -----------------------------------------------------------------------------
# Case 5: Async Functions & Awaitables
# -----------------------------------------------------------------------------
# Coroutine型の厳密一致チェックは実装依存(types.CoroutineType vs typing.Coroutine)で
# 不安定なため、「await可能であり、awaitした結果の型が正しいか」を検証する。


@spot.mark
async def async_worker(x: int) -> float:
    return float(x)


# async関数の中で await した結果の検証
async def _async_check():
    # ここでエラーが出なければ、正しく Awaitable[float] として推論されている
    val = await async_worker(10)
    assert_type(val, float)


# -----------------------------------------------------------------------------
# Case 6: KeyGen Policies (Complex Decorator Arguments)
# -----------------------------------------------------------------------------
@spot.mark(keygen=KeyGen.map(token=KeyGen.IGNORE))
def api_call(endpoint: str, token: str) -> dict[str, Any]:
    return {"data": "ok"}


assert_type(api_call("https://example.com", token="secret"), dict[str, Any])


# -----------------------------------------------------------------------------
# Case 7: Rate Limiter Decorator
# -----------------------------------------------------------------------------
@spot.consume(cost=5)
def limited_operation(name: str) -> int:
    return len(name)


assert_type(limited_operation("test"), int)


# 重ねがけ（Stacking Decorators）
@spot.consume(cost=1)
@spot.mark
def stacked_operation(x: int) -> str:
    return str(x)


assert_type(stacked_operation(123), str)


# -----------------------------------------------------------------------------
# Case 8: Type Registration (Class Decorator)
# -----------------------------------------------------------------------------
# クラス定義時に decoder を指定しようとすると、まだクラスが定義されていないため
# NameError または 型推論エラー(T=None) になる。
# これを防ぐために `decoder_factory` を使用する。
# factory は (cls) -> (data) -> cls という構造を持つため、T が正しく cls にバインドされる。


@spot.register(
    code=100,
    encoder=lambda x: x.val,
    # decoder=... ではなく factory を使うのが Generic class decorator の定石
    decoder=lambda x: MyCustomType(x),
)
class MyCustomType:
    def __init__(self, val: int):
        self.val = val

    def method(self) -> str:
        return str(self.val)


# コンストラクタの型チェック
instance = MyCustomType(val=42)
assert_type(instance, MyCustomType)

# メソッドの型チェック
assert_type(instance.method(), str)
