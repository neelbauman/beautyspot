# tests/test_core.py

import pytest
from beautyspot import Project

@pytest.fixture
def project(tmp_path):
    # DBもBlobも一時ディレクトリに作成
    return Project(
        name="test_project",
        db_path=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs")
    )

def test_task_execution(project):
    """タスクが実行され、結果が保存されるか"""
    
    call_count = 0

    @project.task
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

def test_task_with_blob(project):
    """save_blob=True の動作確認"""
    
    @project.task(save_blob=True)
    def large_data():
        return "x" * 1000

    res = large_data()
    assert len(res) == 1000
    
    # DBにはパスが保存されているはず (中身ではなく)
    # Project経由では隠蔽されているので、内部DBを覗き見る
    record = project.db.get_history(limit=1)
    # result_type が FILE になっているか確認
    assert record.iloc[0]["result_type"] == "FILE"

