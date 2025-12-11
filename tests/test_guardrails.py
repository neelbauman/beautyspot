# tests/test_guardrails.py

import logging
import numpy as np
from beautyspot import Project


def test_large_data_warning(tmp_path, caplog):
    """
    save_blob=False なのに閾値を超えるデータを返した時、
    正しく警告ログが出るか検証する。
    """
    # 閾値を小さく設定 (1KB)
    project = Project(
        name="guard_test", db=str(tmp_path / "test.db"), blob_warning_threshold=1024
    )

    @project.task(save_blob=False)
    def heavy_task():
        # 2KBのデータ
        return "x" * 2048

    # 実行してログをキャプチャ
    with caplog.at_level(logging.WARNING):
        res = heavy_task()

    assert len(res) == 2048

    # 警告が含まれているか
    assert "Large data detected" in caplog.text
    assert "save_blob=True" in caplog.text

    # DBには DIRECT_BLOB として保存されているはず
    hist = project.db.get_history()
    assert hist.iloc[0]["result_type"] == "DIRECT_BLOB"


def test_msgpack_consistency(tmp_path):
    """
    save_blob=False でも Numpy などのカスタム型が
    (Base64経由で) 壊れずに保存・復元できるか検証する。
    -> Base64ではなくNative BLOBになったため、それも含めて検証
    """
    project = Project(name="consistency_test", db=str(tmp_path / "test.db"))

    # Numpy用のシリアライザ登録
    project.register_type(
        np.ndarray,
        10,
        lambda x: x.tobytes(),
        lambda b: np.frombuffer(b, dtype=np.int64),
    )

    @project.task(save_blob=False)  # あえて False
    def numpy_task():
        # int64 * 3 (24bytes) なので 1KB 以下
        return np.array([1, 2, 3], dtype=np.int64)

    # 実行 & 保存
    res1 = numpy_task()
    assert isinstance(res1, np.ndarray)

    # キャッシュからの復元 (再実行)
    res2 = numpy_task()
    assert isinstance(res2, np.ndarray)  # 文字列ではなくndarrayで戻るはず
    assert np.array_equal(res1, res2)

