import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from beautyspot.maintenance import MaintenanceService
from beautyspot.db import TaskDBBase
from beautyspot.storage import BlobStorageBase
from beautyspot.serializer import SerializerProtocol


@pytest.fixture
def mock_db():
    return MagicMock(spec=TaskDBBase)


@pytest.fixture
def mock_storage():
    return MagicMock(spec=BlobStorageBase)


@pytest.fixture
def mock_serializer():
    serializer = MagicMock(spec=SerializerProtocol)
    # デフォルト動作: 入力をそのまま返す（パススルー）
    serializer.loads.side_effect = lambda x: x
    return serializer


@pytest.fixture
def service(mock_db, mock_storage, mock_serializer):
    return MaintenanceService(mock_db, mock_storage, mock_serializer)


class TestMaintenanceServiceDetail:
    """
    get_task_detail メソッド（旧 dashboard.py ロジック）のテスト
    """

    def test_get_task_detail_not_found(self, service, mock_db):
        """レコードが存在しない場合は None を返すこと"""
        mock_db.get.return_value = None
        assert service.get_task_detail("missing_key") is None

    def test_get_task_detail_direct_blob_success(
        self, service, mock_db, mock_serializer
    ):
        """DIRECT_BLOB 型でデータがある場合、デシリアライズして返すこと"""
        mock_db.get.return_value = {
            "result_type": "DIRECT_BLOB",
            "result_data": b"packed_data",
            "result_value": None,
        }

        # [Fix] side_effect を解除して return_value を有効にする
        mock_serializer.loads.side_effect = None
        mock_serializer.loads.return_value = "decoded_object"

        result = service.get_task_detail("key1")

        assert result["decoded_data"] == "decoded_object"
        mock_serializer.loads.assert_called_once_with(b"packed_data")

    def test_get_task_detail_file_success(
        self, service, mock_db, mock_storage, mock_serializer
    ):
        """FILE 型の場合、Storageから読み込んでデシリアライズすること"""
        mock_db.get.return_value = {
            "result_type": "FILE",
            "result_value": "path/to/blob",
            "result_data": None,
        }
        mock_storage.load.return_value = b"file_content"

        # [Fix] side_effect を解除
        mock_serializer.loads.side_effect = None
        mock_serializer.loads.return_value = "decoded_file"

        result = service.get_task_detail("key2")

        assert result["decoded_data"] == "decoded_file"
        mock_storage.load.assert_called_once_with("path/to/blob")
        mock_serializer.loads.assert_called_once_with(b"file_content")

    def test_get_task_detail_deserialize_error(self, service, mock_db, mock_serializer):
        """デシリアライズ失敗時は decoded_data が None になること（クラッシュしない）"""
        mock_db.get.return_value = {
            "result_type": "DIRECT_BLOB",
            "result_data": b"corrupted",
        }
        # side_effect で例外を投げるように上書き
        mock_serializer.loads.side_effect = Exception("Decode failed")

        result = service.get_task_detail("key3")

        assert result is not None
        assert result["decoded_data"] is None  # エラーにならず None が入る

    def test_get_task_detail_storage_error(self, service, mock_db, mock_storage):
        """Storage読み込み失敗時は decoded_data が None になること"""
        mock_db.get.return_value = {
            "result_type": "FILE",
            "result_value": "missing/file",
        }
        mock_storage.load.side_effect = Exception("File not found")

        result = service.get_task_detail("key4")

        assert result is not None
        assert result["decoded_data"] is None


class TestMaintenanceServiceDelete:
    """
    delete_task メソッドのテスト
    """

    def test_delete_task_file(self, service, mock_db, mock_storage):
        """FILE 型の場合、Storage削除とDB削除の両方が呼ばれること"""
        mock_db.get.return_value = {
            "result_type": "FILE",
            "result_value": "path/to/delete",
        }
        mock_db.delete.return_value = True

        assert service.delete_task("key_del") is True

        mock_storage.delete.assert_called_once_with("path/to/delete")
        mock_db.delete.assert_called_once_with("key_del")

    def test_delete_task_direct_blob(self, service, mock_db, mock_storage):
        """DIRECT_BLOB 型の場合、Storage削除は呼ばれないこと"""
        mock_db.get.return_value = {
            "result_type": "DIRECT_BLOB",
            "result_value": None,
        }
        mock_db.delete.return_value = True

        service.delete_task("key_blob")

        mock_storage.delete.assert_not_called()
        mock_db.delete.assert_called_once_with("key_blob")

    def test_delete_task_storage_fail_tolerant(self, service, mock_db, mock_storage):
        """Storage削除が失敗しても、DBレコード削除は強行すること（Tolerant Deletion）"""
        mock_db.get.return_value = {
            "result_type": "FILE",
            "result_value": "ghost/file",
        }
        mock_storage.delete.side_effect = Exception("S3 Error")
        mock_db.delete.return_value = True

        # 例外が発生せず、True（削除成功扱い）が返ることを期待
        assert service.delete_task("key_ghost") is True

        mock_db.delete.assert_called_once_with("key_ghost")


class TestMaintenanceFactory:
    """
    from_path ファクトリのテスト
    """

    # [Fix] patchの対象をメンテナンスモジュールではなく、実体の定義場所に変更する
    # maintenance.py ではこれらを関数内で import しているため、
    # そのインポート元を patch すれば、関数実行時に Mock が使われる
    @patch("beautyspot.db.SQLiteTaskDB")
    @patch("beautyspot.storage.create_storage")
    @patch("beautyspot.serializer.MsgpackSerializer")
    def test_from_path_assembly(self, MockSer, MockCreateStorage, MockDB):
        """パスから正しくコンポーネントを組み立てられるか"""
        # Given
        db_path = Path("/tmp/test.db")

        # When
        svc = MaintenanceService.from_path(db_path)

        # Then
        MockDB.assert_called_once_with(db_path)
        # Blobパスの推論ロジックの検証 (/tmp/blobs になるはず)
        expected_blob_path = str(db_path.parent / "blobs")
        MockCreateStorage.assert_called_once_with(expected_blob_path)
        assert isinstance(svc, MaintenanceService)
