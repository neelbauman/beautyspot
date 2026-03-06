import pytest
from unittest.mock import MagicMock
from beautyspot.core import Spot
from beautyspot.cache import CacheManager
from beautyspot.limiter import LimiterProtocol

def test_sync_save_error_raises():
    cache_mock = MagicMock(spec=CacheManager)
    limiter_mock = MagicMock(spec=LimiterProtocol)
    
    # DB initialization mock
    cache_mock.db = MagicMock()
    cache_mock.db.init_schema.return_value = None
    
    # make_cache_key mock
    cache_mock.make_cache_key.return_value = ("input_id_1", "cache_key_1")
    cache_mock.calculate_expires_at.return_value = None
    
    # cache.get mock (miss)
    from beautyspot.cache import CACHE_MISS
    cache_mock.get.return_value = CACHE_MISS
    
    # Herd wait mock (is_executor=True)
    from beautyspot.cache import HerdWaitResult
    import threading
    event = threading.Event()
    herd_result = HerdWaitResult(is_executor=True, result=None, event=event, result_box=[], is_error=False)
    cache_mock.wait_herd_sync.return_value = herd_result
    
    # cache.set mock raises Exception
    cache_mock.set.side_effect = RuntimeError("Mock DB Save Error")

    # Instance
    spot = Spot(name="test_spot", cache=cache_mock, limiter=limiter_mock, save_sync=True)
    
    @spot.mark()
    def my_func():
        return "result"
        
    with pytest.raises(RuntimeError, match="Mock DB Save Error"):
        my_func()

