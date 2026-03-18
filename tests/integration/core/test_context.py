# tests/integration/core/test_context.py

import pytest
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB


def test_spot_context_manager_reusability(tmp_path):
    """
    Spotがコンテキストマネージャとして動作し、
    終了後もExecutorが有効（再利用可能）であることを確認する。
    """
    db_path = str(tmp_path / "test.db")
    spot = Spot(name="test_cm", db=SQLiteTaskDB(db_path))

    # 1回目のコンテキスト
    with spot as p:
        assert p is spot

        @spot.mark
        def task1(x):
            return x

        task1(1)

    # 仕様変更: __exit__ で shutdown されないため、2回目もエラーなく実行できるはず
    try:
        with spot:
            task1(2)
    except RuntimeError:
        pytest.fail("Spot should be reusable after exiting a context block.")


def test_spot_explicit_shutdown(tmp_path):
    """明示的に shutdown を呼んだ後は、Executorが停止することを確認する。"""
    db_path = str(tmp_path / "test.db")
    
    error_raised = None
    def on_error(e, ctx):
        nonlocal error_raised
        error_raised = e
        
    spot = Spot(name="test_shutdown", db=SQLiteTaskDB(db_path), on_save_error=on_error)

    spot.shutdown(save_sync=True)

    @spot.mark(save_sync=False)
    def task(x):
        return x

    # シャットダウン後はバックグラウンド保存に失敗するが、実行自体は成功する
    result = task(1)
    assert result == 1
    
    assert isinstance(error_raised, RuntimeError)
    assert "shutdown" in str(error_raised).lower()
