import asyncio
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from beautyspot.cache import CACHE_MISS, CacheManager
from beautyspot.db import TaskDBBase
from beautyspot.storage import BlobStorageBase, StoragePolicyProtocol
from beautyspot.serializer import SerializerProtocol
from beautyspot.lifecycle import LifecyclePolicy, _FOREVER
from beautyspot.exceptions import CacheCorruptedError


@pytest.fixture
def mock_db():
    return MagicMock(spec=TaskDBBase)

@pytest.fixture
def mock_storage():
    return MagicMock(spec=BlobStorageBase)

@pytest.fixture
def mock_serializer():
    mock = MagicMock(spec=SerializerProtocol)
    mock.dumps.return_value = b"mock_data"
    mock.loads.return_value = "mock_result"
    return mock

@pytest.fixture
def mock_policy():
    mock = MagicMock(spec=StoragePolicyProtocol)
    mock.should_save_as_blob.return_value = False
    return mock

@pytest.fixture
def cache_manager(mock_db, mock_storage, mock_serializer, mock_policy):
    return CacheManager(
        db=mock_db,
        storage=mock_storage,
        serializer=mock_serializer,
        storage_policy=mock_policy,
        lifecycle_policy=LifecyclePolicy.default(),
    )

def test_cache_manager_init_default_lifecycle(mock_db, mock_storage, mock_serializer, mock_policy):
    manager = CacheManager(
        db=mock_db,
        storage=mock_storage,
        serializer=mock_serializer,
        storage_policy=mock_policy,
    )
    assert manager.lifecycle_policy is not None
    assert isinstance(manager.lifecycle_policy, LifecyclePolicy)


def test_make_cache_key_default(cache_manager):
    iid, ck = cache_manager.make_cache_key(
        func_identifier="test_func",
        args=(1, 2),
        kwargs={"a": 3},
        resolved_key_fn=None,
        version=None
    )
    assert iid is not None
    assert ck is not None
    assert isinstance(ck, str)

def test_make_cache_key_with_resolved_key_fn(cache_manager):
    mock_key_fn = MagicMock(return_value="custom_id")
    iid, ck = cache_manager.make_cache_key(
        func_identifier="test_func",
        args=(1,),
        kwargs={},
        resolved_key_fn=mock_key_fn,
        version="v1"
    )
    assert iid == "custom_id"
    mock_key_fn.assert_called_once_with(1)

def test_calculate_expires_at_forever(cache_manager):
    assert cache_manager.calculate_expires_at("test_func", "test", _FOREVER) is None


def test_calculate_expires_at_with_string(cache_manager):
    res = cache_manager.calculate_expires_at("test_func", "test", "1h")
    assert res is not None
    assert isinstance(res, datetime)

def test_calculate_expires_at_fallback(cache_manager):
    cache_manager.lifecycle_policy.resolve_with_fallback = MagicMock(return_value=timedelta(hours=2))
    res = cache_manager.calculate_expires_at("test_func", "test", None)
    assert res is not None

def test_get_cache_miss(cache_manager, mock_db):
    mock_db.get.return_value = None
    assert cache_manager.get("key") is CACHE_MISS

def test_get_direct_blob_success(cache_manager, mock_db, mock_serializer):
    mock_db.get.return_value = {
        "result_type": "DIRECT_BLOB",
        "result_value": None,
        "result_data": b"packed_data",
    }
    res = cache_manager.get("key")
    assert res == "mock_result"
    mock_serializer.loads.assert_called_once_with(b"packed_data")

def test_get_direct_blob_no_data(cache_manager, mock_db):
    mock_db.get.return_value = {
        "result_type": "DIRECT_BLOB",
        "result_value": None,
        "result_data": None,
    }
    assert cache_manager.get("key") is CACHE_MISS

def test_get_file_success(cache_manager, mock_db, mock_storage, mock_serializer):
    mock_db.get.return_value = {
        "result_type": "FILE",
        "result_value": "blob_path",
        "result_data": None,
    }
    mock_storage.load.return_value = b"blob_data"
    res = cache_manager.get("key")
    assert res == "mock_result"
    mock_storage.load.assert_called_once_with("blob_path")
    mock_serializer.loads.assert_called_once_with(b"blob_data")

def test_get_file_no_value(cache_manager, mock_db):
    mock_db.get.return_value = {
        "result_type": "FILE",
        "result_value": None,
        "result_data": None,
    }
    assert cache_manager.get("key") is CACHE_MISS

def test_get_unknown_type(cache_manager, mock_db):
    mock_db.get.return_value = {
        "result_type": "UNKNOWN_TYPE",
        "result_value": "val",
        "result_data": None,
    }
    assert cache_manager.get("key") is CACHE_MISS

def test_get_corrupted_error(cache_manager, mock_db, mock_serializer):
    mock_db.get.return_value = {
        "result_type": "DIRECT_BLOB",
        "result_value": None,
        "result_data": b"bad_data",
    }
    mock_serializer.loads.side_effect = CacheCorruptedError("bad")
    assert cache_manager.get("key") is CACHE_MISS

def test_get_exception(cache_manager, mock_db, mock_serializer):
    mock_db.get.return_value = {
        "result_type": "DIRECT_BLOB",
        "result_value": None,
        "result_data": b"bad_data",
    }
    mock_serializer.loads.side_effect = ValueError("oops")
    assert cache_manager.get("key") is CACHE_MISS

def test_set_direct_blob(cache_manager, mock_db, mock_serializer):
    cache_manager.set(
        cache_key="key",
        func_name="func",
        func_identifier="f_id",
        input_id="in_id",
        version="v1",
        result="result_obj",
        content_type=None,
        save_blob=False,
    )
    mock_serializer.dumps.assert_called_once_with("result_obj")
    mock_db.save.assert_called_once_with(
        cache_key="key",
        func_name="func",
        func_identifier="f_id",
        input_id="in_id",
        version="v1",
        result_type="DIRECT_BLOB",
        content_type=None,
        result_value=None,
        result_data=b"mock_data",
        expires_at=None,
    )

def test_set_file(cache_manager, mock_db, mock_storage, mock_serializer):
    mock_storage.save.return_value = "saved_path"
    cache_manager.set(
        cache_key="key",
        func_name="func",
        func_identifier="f_id",
        input_id="in_id",
        version="v1",
        result="result_obj",
        content_type=None,
        save_blob=True,
    )
    mock_storage.save.assert_called_once_with("key", b"mock_data")
    mock_db.save.assert_called_once_with(
        cache_key="key",
        func_name="func",
        func_identifier="f_id",
        input_id="in_id",
        version="v1",
        result_type="FILE",
        content_type=None,
        result_value="saved_path",
        result_data=None,
        expires_at=None,
    )

def test_set_file_rollback_on_db_fail(cache_manager, mock_db, mock_storage):
    mock_storage.save.return_value = "saved_path"
    mock_db.save.side_effect = Exception("DB error")
    
    with pytest.raises(Exception, match="DB error"):
        cache_manager.set(
            cache_key="key",
            func_name="func",
            func_identifier="f_id",
            input_id="in_id",
            version="v1",
            result="res",
            content_type=None,
            save_blob=True,
        )
    
    mock_storage.delete.assert_called_once_with("saved_path")

def test_set_policy_decides(cache_manager, mock_db, mock_policy):
    mock_policy.should_save_as_blob.return_value = True
    cache_manager.storage.save.return_value = "p"
    
    cache_manager.set(
        cache_key="key",
        func_name="func",
        func_identifier="f_id",
        input_id="in_id",
        version="v1",
        result="res",
        content_type=None,
        save_blob=None, # let policy decide
    )
    mock_policy.should_save_as_blob.assert_called_once_with(b"mock_data")
    assert mock_db.save.call_args[1]["result_type"] == "FILE"

# --- Thundering Herd Sync ---

def test_wait_herd_sync_becomes_executor(cache_manager):
    res = cache_manager.wait_herd_sync("k1")
    assert res.is_executor is True
    assert res.event is not None
    assert isinstance(res.result_box, list)
    assert res.is_error is False

def test_wait_herd_sync_waits_for_event(cache_manager):
    # k1 is already in flight
    ev = threading.Event()
    box = []
    cache_manager._inflight["k1"] = (ev, [], box)
    
    # We will set the event in another thread to unblock
    def setter():
        time.sleep(0.1)
        box.append((True, "shared_result"))
        ev.set()
        
    t = threading.Thread(target=setter)
    t.start()
    
    res = cache_manager.wait_herd_sync("k1")
    t.join()
    
    assert res.is_executor is False
    assert res.result == "shared_result"
    assert res.is_error is False

    pass

def test_wait_herd_sync_timeout_with_recheck_hit(cache_manager, monkeypatch):
    cache_manager.HERD_POLL = 0.01
    cache_manager.HERD_TIMEOUT = 0.02
    
    ev = threading.Event()
    box = []
    cache_manager._inflight["k1"] = (ev, [], box)
    
    monkeypatch.setattr(cache_manager, "get", lambda k, s=None: "rechecked_val")
    
    res = cache_manager.wait_herd_sync("k1")
    assert res.is_executor is False
    assert res.result == "rechecked_val"

# --- Thundering Herd Async ---

@pytest.mark.asyncio
async def test_wait_herd_async_becomes_executor(cache_manager):
    loop = asyncio.get_running_loop()
    res = await cache_manager.wait_herd_async("k2", None, loop, None)
    assert res.is_executor is True
    assert res.event is not None
    assert isinstance(res.result_box, list)

@pytest.mark.asyncio
async def test_wait_herd_async_waits_for_future(cache_manager):
    loop = asyncio.get_running_loop()
    ev = threading.Event()
    box = []
    futs = []
    cache_manager._inflight["k2"] = (ev, futs, box)
    
    async def delayed_resolve():
        await asyncio.sleep(0.05)
        box.append((True, "async_res"))
        futs[0].set_result("async_res")
        ev.set()
        
    asyncio.create_task(delayed_resolve())
    
    res = await cache_manager.wait_herd_async("k2", None, loop, None)
    assert res.is_executor is False
    assert res.result == "async_res"
    assert res.is_error is False

@pytest.mark.asyncio
async def test_wait_herd_async_future_exception(cache_manager):
    loop = asyncio.get_running_loop()
    ev = threading.Event()
    box = []
    futs = []
    cache_manager._inflight["k2"] = (ev, futs, box)
    
    async def delayed_resolve():
        await asyncio.sleep(0.05)
        # Instead of appending to box, just throw in future
        futs[0].set_exception(ValueError("async error"))
        
    asyncio.create_task(delayed_resolve())
    
    res = await cache_manager.wait_herd_async("k2", None, loop, None)
    assert res.is_executor is False
    assert isinstance(res.result, ValueError)
    assert res.is_error is True

@pytest.mark.asyncio
async def test_wait_herd_async_timeout_no_futs(cache_manager):
    loop = asyncio.get_running_loop()
    ev = threading.Event()
    # If wait_box already has items but we call wait_herd_async:
    box = [(True, "box_val")]
    futs = []
    cache_manager._inflight["k2"] = (ev, futs, box)
    
    res = await cache_manager.wait_herd_async("k2", None, loop, None)
    assert res.is_executor is False
    assert res.result == "box_val"

# --- Cleanup Inflight ---

def test_notify_and_cleanup_inflight(cache_manager):
    ev = threading.Event()
    box = [(True, "final_val")]
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    cache_manager._inflight["k3"] = (ev, [fut], box)
    
    cache_manager.notify_and_cleanup_inflight("k3", ev, box)
    
    assert "k3" not in cache_manager._inflight
    assert ev.is_set()
    
    # Run loop briefly to let call_soon_threadsafe execute
    loop.call_soon(loop.stop)
    loop.run_forever()
    
    assert fut.result() == "final_val"
    loop.close()

def test_notify_and_cleanup_inflight_error(cache_manager):
    ev = threading.Event()
    err = RuntimeError("failed")
    box = [(False, err)]
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    cache_manager._inflight["k3"] = (ev, [fut], box)
    
    cache_manager.notify_and_cleanup_inflight("k3", ev, box)
    
    assert ev.is_set()
    loop.call_soon(loop.stop)
    loop.run_forever()
    
    with pytest.raises(RuntimeError, match="failed"):
        fut.result()
    loop.close()


def test_herd_sync_context_manager_cleanup_on_exception(cache_manager):
    key = "k_sync_exc"
    try:
        with cache_manager.herd_sync(key) as herd:
            assert herd.is_executor is True
            assert key in cache_manager._inflight
            raise ValueError("intentional error")
    except ValueError:
        pass
    
    # Check that it was cleaned up even though we raised an exception
    assert key not in cache_manager._inflight


@pytest.mark.asyncio
async def test_herd_async_context_manager_cleanup_on_exception(cache_manager):
    key = "k_async_exc"
    loop = asyncio.get_running_loop()
    try:
        async with cache_manager.herd_async(key, None, loop, None) as herd:
            assert herd.is_executor is True
            assert key in cache_manager._inflight
            raise ValueError("intentional async error")
    except ValueError:
        pass
    
    # Check that it was cleaned up
    assert key not in cache_manager._inflight


def test_herd_sync_context_manager_waiter(cache_manager):
    key = "k_sync_wait"
    ev = threading.Event()
    box = []
    cache_manager._inflight[key] = (ev, [], box)
    
    def setter():
        time.sleep(0.1)
        box.append((True, "val"))
        ev.set()
    
    threading.Thread(target=setter).start()
    
    with cache_manager.herd_sync(key) as herd:
        assert herd.is_executor is False
        assert herd.result == "val"
    
    # As a waiter, we should NOT have deleted it from _inflight (the executor does that)
    assert key in cache_manager._inflight

def test_notify_and_cleanup_inflight_non_exception_error(cache_manager):
    ev = threading.Event()
    box = [(False, "string error")]
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    cache_manager._inflight["k3"] = (ev, [fut], box)
    
    cache_manager.notify_and_cleanup_inflight("k3", ev, box)
    
    assert ev.is_set()
    loop.call_soon(loop.stop)
    loop.run_forever()
    
    with pytest.raises(RuntimeError, match="Non-Exception error: 'string error'"):
        fut.result()
    loop.close()

def test_notify_cleanup_wrong_event(cache_manager):
    ev1 = threading.Event()
    ev2 = threading.Event()
    box = []
    cache_manager._inflight["k3"] = (ev1, [], box)
    
    # Should not remove from dict if event doesn't match
    cache_manager.notify_and_cleanup_inflight("k3", ev2, box)
    assert "k3" in cache_manager._inflight
    assert not ev1.is_set()
    assert ev2.is_set()
