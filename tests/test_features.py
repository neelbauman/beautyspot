# tests/test_features.py

import pytest
import asyncio
from beautyspot import Spot


@pytest.fixture
def spot(tmp_path):
    return Spot(name="feat_test", db=str(tmp_path / "test.db"))


def test_versioning(spot):
    """versionを変更するとキャッシュが無効化(再計算)されるか"""
    call_count = 0

    # バージョン "v1" で定義
    @spot.mark(version="v1")
    def func_v1(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    assert func_v1(10) == 20
    assert call_count == 1

    # 2回目: キャッシュヒット
    assert func_v1(10) == 20
    assert call_count == 1

    # ロジックが変わったとして、バージョン "v2" に変更
    # (同じ関数名で定義しなおすことでシミュレーション)
    @spot.mark(version="v2")
    def func_v2(x):  # func_v1 と同じ関数名(func_name)として登録される
        nonlocal call_count
        call_count += 1
        return x * 2

    # バージョン違い: キャッシュミスして再実行されるはず
    assert func_v2(10) == 20
    assert call_count == 2


def test_error_handling(spot):
    """例外発生時はキャッシュされないことの確認"""
    call_count = 0

    @spot.mark
    def flakey_task(x):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First run fails")
        return x

    # 1回目: 失敗 (例外はそのまま外へ出る)
    with pytest.raises(ValueError):
        flakey_task(1)

    # 2回目: 再実行される (キャッシュされていないため成功する)
    assert flakey_task(1) == 1
    assert call_count == 2

    # 3回目: 成功結果がキャッシュされている
    assert flakey_task(1) == 1
    assert call_count == 2


@pytest.mark.asyncio
async def test_async_task(spot):
    """非同期タスク(@task async def)のサポート確認"""
    import msgpack
    # Base64インポートは不要になったため削除

    @spot.mark
    async def async_add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    # await で呼べること
    res = await async_add(10, 20)
    assert res == 30

    # 結果が保存されていること
    hist = spot.db.get_history()
    assert len(hist) == 1

    row = hist.iloc[0]
    
    # 修正: DIRECT_B64 -> DIRECT_BLOB
    assert row["result_type"] == "DIRECT_BLOB"

    # 修正: Base64デコードではなく、result_data(bytes)を直接unpack
    packed = row["result_data"]
    assert msgpack.unpackb(packed) == 30

