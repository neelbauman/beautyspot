# tests/test_core.py

import pytest
from beautyspot import Spot
from beautyspot.serializer import SerializationError


@pytest.fixture
def spot(tmp_path):
    # DBもBlobも一時ディレクトリに作成
    return Spot(
        name="test_spot",
        db=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs"),
    )


def test_mark_execution(spot):
    """タスク(@mark)が実行され、結果が保存されるか"""

    call_count = 0

    @spot.mark
    def add(a, b):
        nonlocal call_count
        call_count += 1
        return a + b

    # 1回目: 実行されるはず
    res1 = add(1, 2)
    assert res1 == 3
    assert call_count == 1

    # 2回目: キャッシュが返るはず (call_countが増えない)
    res2 = add(1, 2)
    assert res2 == 3
    assert call_count == 1

    # 別の入力: 実行されるはず
    res3 = add(2, 3)
    assert res3 == 5
    assert call_count == 2


def test_mark_with_blob(spot):
    """save_blob=True の動作確認"""

    @spot.mark(save_blob=True)
    def large_data():
        return "x" * 1000

    res = large_data()
    assert len(res) == 1000

    # DBにはパスが保存されているはず (中身ではなく)
    record = spot.db.get_history(limit=1)
    # result_type が FILE になっているか確認
    assert record.iloc[0]["result_type"] == "FILE"


class ComplexObj:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return self.name == other.name


def test_custom_type_mark(spot):
    """
    Spot.register_type を使用して、
    未知のオブジェクトを返すタスクが正常に動作するか確認
    """

    # 1. 未登録状態で実行 -> 失敗するはず
    @spot.mark(save_blob=True)
    def fail_task():
        return ComplexObj("test")

    with pytest.raises(SerializationError):
        fail_task()

    # 2. 型を登録
    def enc(o):
        return o.name.encode("utf-8")

    def dec(b):
        return ComplexObj(b.decode("utf-8"))

    spot.register_type(ComplexObj, 20, enc, dec)

    # 3. 登録後に実行 -> 成功するはず
    @spot.mark(save_blob=True)
    def success_task():
        return ComplexObj("success")

    res1 = success_task()
    assert res1.name == "success"

    # 4. キャッシュヒット時の復元確認
    res2 = success_task()
    assert res2.name == "success"
    assert res2 == res1
