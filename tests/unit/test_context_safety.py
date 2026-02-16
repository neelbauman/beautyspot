import pytest
import asyncio
from unittest.mock import MagicMock
from beautyspot.core import ScopedMark, Spot

@pytest.mark.asyncio
async def test_scoped_mark_context_isolation():
    """
    Verify that ScopedMark uses contextvars to maintain state isolation between tasks.
    
    Scenario:
        - Task A enters the `with` block of a ScopedMark instance.
        - Task A passes the "guarded function" to Task B.
        - While Task A is still inside the block (sleeping), Task B tries to call the function.
        - Task B should fail with RuntimeError because it is not in the same context context,
          even though the ScopedMark instance is technically "active" in Task A.
    """
    # --- Setup Mocks ---
    mock_db = MagicMock()
    mock_storage = MagicMock()
    mock_serializer = MagicMock()
    
    # Spotの最小限のセットアップ
    spot = Spot(
        name="test_spot",
        db=mock_db,
        storage=mock_storage,
        serializer=mock_serializer,
        # テスト用にExecutorを無効化または同期実行させる設定があれば良いが、
        # ここではコアロジックのモックで対応
    )
    
    # 実行されるターゲット関数
    async def target_func():
        return "success"
    
    # Spot.mark がそのまま関数を返すようにモック（装飾ロジックをスキップ）
    # ScopedMark は spot.mark を呼んでキャッシュ機能を追加しようとするが、
    # ここでは「ガード機能」のテストに集中するため、キャッシュ機能はバイパスする。
    spot.mark = MagicMock(side_effect=lambda f, **kwargs: f)

    # --- Test Execution ---
    
    # 1. ScopedMark インスタンス生成
    # 通常は spot.cached_run で生成される
    scoped_mark = ScopedMark(spot, (target_func,))
    
    # 同期用イベント
    task_a_inside = asyncio.Event()
    task_b_done = asyncio.Event()
    
    # ガード付き関数を共有するための変数
    shared_guarded_func = None

    async def task_a_logic():
        nonlocal shared_guarded_func
        # Task A がコンテキストに入る
        with scoped_mark as guarded_func:
            shared_guarded_func = guarded_func
            
            # 自分が中に入ったことを通知
            task_a_inside.set()
            
            # Task B が検証を終えるまでここで待機（コンテキストを開いたままにする）
            await task_b_done.wait()

    async def task_b_logic():
        # Task A がコンテキストに入るのを待つ
        await task_a_inside.wait()
        
        # Task A はまだ with ブロックの中にいる。
        # もしフラグ管理が単純な bool なら、ここで実行できてしまう。
        # ContextVar なら、Task B のコンテキストでは False なので失敗するはず。
        try:
            await shared_guarded_func()
        except RuntimeError as e:
            assert "outside of its 'cached_run' context" in str(e)
            return "caught_error"
        except Exception as e:
            return f"unexpected_error: {type(e)}"
        finally:
            # Task A を解放
            task_b_done.set()
            
        return "unexpected_success"

    # 両方のタスクを並行実行
    task_a = asyncio.create_task(task_a_logic())
    task_b = asyncio.create_task(task_b_logic())
    
    results = await asyncio.gather(task_a, task_b)
    
    # Task A は正常終了、Task B はエラーを捕捉して終了していること
    assert results[1] == "caught_error", "Task B should have raised RuntimeError due to context isolation"

