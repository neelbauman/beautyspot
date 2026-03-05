# tests/unit/test_signature_preservation.py
"""SPEC-001: デコレート関数のシグネチャ保持テスト"""

import inspect


def test_mark_preserves_sync_function_name(spot):
    """@mark がデコレートした同期関数の __name__ を保持すること"""

    @spot.mark
    def my_important_function(x, y):
        return x + y

    assert my_important_function.__name__ == "my_important_function"


def test_mark_preserves_sync_function_doc(spot):
    """@mark がデコレートした同期関数の __doc__ を保持すること"""

    @spot.mark
    def documented_func(x):
        """This is the docstring."""
        return x

    assert documented_func.__doc__ == "This is the docstring."


def test_mark_preserves_sync_function_signature(spot):
    """@mark がデコレートした同期関数の inspect.signature を保持すること"""

    @spot.mark
    def func_with_params(a: int, b: str = "hello", *, c: float = 1.0) -> str:
        return f"{a}{b}{c}"

    sig = inspect.signature(func_with_params)
    params = list(sig.parameters.keys())
    assert params == ["a", "b", "c"]
    assert sig.parameters["a"].annotation is int
    assert sig.parameters["b"].default == "hello"
    assert sig.parameters["c"].kind == inspect.Parameter.KEYWORD_ONLY


def test_mark_preserves_async_function_name(spot):
    """@mark がデコレートした非同期関数の __name__ を保持すること"""

    @spot.mark
    async def async_task(x):
        return x * 2

    assert async_task.__name__ == "async_task"


def test_mark_preserves_async_function_signature(spot):
    """@mark がデコレートした非同期関数の inspect.signature を保持すること"""

    @spot.mark
    async def async_func(a: int, b: list[str]) -> dict:
        return {"a": a}

    sig = inspect.signature(async_func)
    params = list(sig.parameters.keys())
    assert params == ["a", "b"]
    assert sig.parameters["a"].annotation is int


def test_mark_preserves_wrapped_attribute(spot):
    """@mark がデコレートした関数に __wrapped__ 属性が設定されること"""

    def original(x):
        return x

    decorated = spot.mark(original)
    assert hasattr(decorated, "__wrapped__")
    assert decorated.__wrapped__ is original


def test_mark_with_options_preserves_signature(spot):
    """@mark(options) 形式でもシグネチャが保持されること"""

    @spot.mark(version="v1", save_blob=True)
    def parametric_func(data: bytes, count: int = 10) -> list:
        return [data] * count

    assert parametric_func.__name__ == "parametric_func"
    sig = inspect.signature(parametric_func)
    assert "data" in sig.parameters
    assert "count" in sig.parameters
    assert sig.parameters["count"].default == 10
