# tests/unit/test_storage_policy.py

import logging
from unittest.mock import Mock
from beautyspot.storage import (
    ThresholdStoragePolicy,
    WarningOnlyPolicy,
    AlwaysBlobPolicy,
)


class TestThresholdStoragePolicy:
    def test_below_threshold(self):
        # 100バイトの閾値に対して、10バイトのデータ
        policy = ThresholdStoragePolicy(threshold=100)
        data = b"x" * 10
        assert policy.should_save_as_blob(data) is False

    def test_above_threshold(self):
        # 100バイトの閾値に対して、101バイトのデータ
        policy = ThresholdStoragePolicy(threshold=100)
        data = b"x" * 101
        assert policy.should_save_as_blob(data) is True

    def test_exact_threshold(self):
        # 境界値テスト: 閾値と同じサイズなら False (仕様: > threshold)
        policy = ThresholdStoragePolicy(threshold=100)
        data = b"x" * 100
        assert policy.should_save_as_blob(data) is False


class TestWarningOnlyPolicy:
    def test_behavior(self):
        # WarningOnlyPolicy はデータサイズに関わらず常に False を返すべき
        logger = Mock(spec=logging.Logger)
        policy = WarningOnlyPolicy(warning_threshold=100, logger=logger)

        # 小さいデータ
        assert policy.should_save_as_blob(b"small") is False
        logger.warning.assert_not_called()

        # 大きいデータ
        assert policy.should_save_as_blob(b"x" * 150) is False
        # 警告ログが呼ばれたか確認
        logger.warning.assert_called_once()
        args, _ = logger.warning.call_args
        assert "Large data detected" in args[0]


class TestAlwaysBlobPolicy:
    def test_always_true(self):
        policy = AlwaysBlobPolicy()
        assert policy.should_save_as_blob(b"") is True
        assert policy.should_save_as_blob(b"large" * 1000) is True
