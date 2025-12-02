# tests/test_limiter.py

import pytest
import time
import threading
from unittest.mock import patch
from beautyspot.limiter import TokenBucket

def test_init_validation():
    """不正なTPM値の検出"""
    with pytest.raises(ValueError):
        TokenBucket(0)
    with pytest.raises(ValueError):
        TokenBucket(-100)

def test_max_cost_validation():
    """TPMを超えるコストのリクエストは即死させる"""
    # TPM=60 -> 最大コストも60
    bucket = TokenBucket(60) 
    with pytest.raises(ValueError):
        bucket._consume_reservation(61)

def test_gcra_actual_waiting():
    """
    【修正版】計算だけでなく、実際に指定時間待機(sleep)しているか検証する。
    TPM=60 -> 1 request / 1.0 sec (Rate=1.0)
    """
    # time.sleep もモック化して、引数を検証する
    with patch("time.monotonic") as mock_time, patch("time.sleep") as mock_sleep:
        # T=0 でスタート
        mock_time.return_value = 0.0
        
        # Patch内でインスタンス化 (self.tat = 0.0 になる)
        bucket = TokenBucket(60)
        
        # 1. コスト3 (3秒分) のリクエスト
        # 待機なしで通るが、TAT（理論到達時刻）は 0.0 -> 3.0 に進む
        bucket.consume(3)
        
        # 検証: 1回目は待機していないはず
        mock_sleep.assert_not_called()
        assert bucket.tat == 3.0
        
        # 2. 直後 (T=0.0のまま) に次のリクエスト
        # 「3秒分の借金」がある状態なので、きっちり 3.0秒 待たされるはず
        bucket.consume(1)
        
        # 検証: "3秒" 待ったか？
        mock_sleep.assert_called_with(3.0)
        
        # 待機分とコスト分が加算され、TAT は 4.0 になっているはず
        assert bucket.tat == 4.0

def test_gcra_idle_reset_mocked():
    """
    アイドル後の挙動確認
    長時間放置しても、TATが現在時刻にリセットされ、バーストしないことを確認。
    """
    with patch("time.monotonic") as mock_time, patch("time.sleep") as mock_sleep:
        # T=0
        mock_time.return_value = 0.0
        bucket = TokenBucket(60)  # 1 req / sec
        
        bucket.consume(1) # TAT -> 1.0
        
        # 1時間経過させる (T=3600.0)
        # 通常のトークンバケットなら「トークン満タン」でバーストするが、
        # GCRA では「ペースを守る」ためリセットされるべき。
        mock_time.return_value = 3600.0
        
        # アイドル明けの1発目
        bucket.consume(1)
        mock_sleep.assert_not_called()
        # TATは 1.0 + increment ではなく、Now(3600.0) + increment にリセットされる
        assert bucket.tat == 3601.0
        
        # アイドル明けの2発目 (連打)
        # 1秒の間隔を空けるために待機が発生する
        bucket.consume(1)
        mock_sleep.assert_called_with(1.0)
        assert bucket.tat == 3602.0

def test_thread_safety():
    """マルチスレッドで同時に叩いても整合性が壊れないか"""
    bucket = TokenBucket(60000)
    
    def worker():
        for _ in range(100):
            bucket.consume(1)
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    
    start_time = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    end_time = time.time()
    
    duration = end_time - start_time
    assert duration > 0

def test_cost_proportionality():
    """
    トークン数（コスト）に応じて、待機時間が正しく比例計算されているか検証する。
    TPM=60 -> 1 token = 1.0 sec
    """
    with patch("time.monotonic") as mock_time, patch("time.sleep") as mock_sleep:
        mock_time.return_value = 0.0
        bucket = TokenBucket(60)
        
        # --- Case A: Heavy Task (Cost=10) ---
        # 実行: 即時実行されるが、TATは +10.0秒 進むはず
        bucket.consume(10)
        mock_sleep.assert_not_called()
        assert bucket.tat == 10.0
        
        # --- Case B: Light Task (Cost=2) ---
        # 直後に実行: 前回のコスト分 (10秒) 待たされるはず
        bucket.consume(2)
        mock_sleep.assert_called_with(10.0) # <--- ここで計算の正確性を確認
        
        # TATは 待機分(10.0) + 今回のコスト(2.0) = 12.0 になっているはず
        # ※ 実装上は bucket.tat (10.0) += 2.0 なので 12.0
        assert bucket.tat == 12.0
        
        # --- Case C: Medium Task (Cost=5) ---
        # 直後に実行: 前回のコスト分 (2秒) ではなく、
        # "現在のTAT(12.0) - 現在時刻(0.0)" = 12.0秒 待たされる
        bucket.consume(5)
        mock_sleep.assert_called_with(12.0)
        assert bucket.tat == 17.0

def test_fractional_cost():
    """
    小数点以下のコストやレート計算の精度確認
    TPM=600 -> 10 req/sec -> 1 token = 0.1 sec
    """
    with patch("time.monotonic") as mock_time, patch("time.sleep") as mock_sleep:
        mock_time.return_value = 0.0
        bucket = TokenBucket(600)
        
        # Cost=5 -> 0.5秒分の負債
        bucket.consume(5)
        assert bucket.tat == 0.5
        
        # 次のリクエスト -> 0.5秒待機
        bucket.consume(1)
        mock_sleep.assert_called_with(0.5)

