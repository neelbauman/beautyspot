# tests/test_features.py

import pytest
import asyncio
from beautyspot import Project


@pytest.fixture
def project(tmp_path):
    return Project(name="feat_test", db=str(tmp_path / "test.db"))


def test_versioning(project):
    """versionを変更するとキャッシュが無効化(再計算)されるか"""
    call_count = 0

    # バージョン "v1" で定義
    @project.task(version="v1")
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
    @project.task(version="v2")
    def func_v2(x):  # func_v1 と同じ関数名(func_name)として登録される
        nonlocal call_count
        call_count += 1
        return x * 2

    # バージョン違い: キャッシュミスして再実行されるはず
    assert func_v2(10) == 20
    assert call_count == 2


def test_error_handling(project):
    """例外発生時はキャッシュされないことの確認"""
    call_count = 0

    @project.task
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
async def test_async_task(project):
    """非同期タスク(@task async def)のサポート確認"""
    import msgpack
    import base64

    @project.task
    async def async_add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    # await で呼べること
    res = await async_add(10, 20)
    assert res == 30

    # 結果が保存されていること
    hist = project.db.get_history()
    assert len(hist) == 1

    row = hist.iloc[0]
    assert row["result_type"] == "DIRECT_B64"

    packed = base64.b64decode(row["result_value"])
    assert msgpack.unpackb(packed) == 30
