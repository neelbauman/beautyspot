import os
import time
from pathlib import Path
from beautyspot.storage import LocalStorage
from beautyspot.maintenance import MaintenanceService
from beautyspot.db import SQLiteTaskDB
from beautyspot.serializer import MsgpackSerializer


def test_local_storage_clean_temp_files(tmp_path: Path):
    """
    LocalStorage.clean_temp_files が、指定した時間より古い .spot_tmp
    ファイルのみを正確に削除し、新しいファイルや他の拡張子のファイルは
    保持することを確認する。
    """
    storage = LocalStorage(base_dir=tmp_path)
    now = time.time()

    # 1. 25時間前の古い一時ファイル（削除されるべき）
    old_tmp = tmp_path / "old.spot_tmp"
    old_tmp.write_bytes(b"old data")
    os.utime(old_tmp, (now - 90000, now - 90000))  # 25時間前

    # 2. 1時間前の新しい一時ファイル（現在別プロセスが書き込み中と見なし保持されるべき）
    new_tmp = tmp_path / "new.spot_tmp"
    new_tmp.write_bytes(b"new data")
    os.utime(new_tmp, (now - 3600, now - 3600))  # 1時間前

    # 3. 25時間前の正規のBlobファイル（拡張子が違うので保持されるべき）
    valid_bin = tmp_path / "valid.bin"
    valid_bin.write_bytes(b"valid data")
    os.utime(valid_bin, (now - 90000, now - 90000))

    # 削除処理を実行（デフォルトの24時間=86400秒を基準とする）
    removed_count = storage.clean_temp_files(max_age_seconds=86400)

    # 検証
    assert removed_count == 1
    assert not old_tmp.exists(), "Old temporary file should be deleted."
    assert new_tmp.exists(), "Recent temporary file should be kept."
    assert valid_bin.exists(), "Regular .bin files should never be touched."


def test_maintenance_clean_garbage_includes_tmp_files(tmp_path: Path):
    """
    MaintenanceService.clean_garbage() の呼び出しパイプラインに、
    一時ファイルのクリーンアップ処理が正しく統合されていることを確認する。
    """
    db_path = tmp_path / "tasks.db"
    blob_dir = tmp_path / "blobs"

    db = SQLiteTaskDB(db_path)
    db.init_schema()
    storage = LocalStorage(blob_dir)
    serializer = MsgpackSerializer()

    maintenance = MaintenanceService(db, storage, serializer)

    # 古い一時ファイルを準備
    old_tmp = blob_dir / "leaked.spot_tmp"
    old_tmp.write_bytes(b"leaked data")

    now = time.time()
    os.utime(old_tmp, (now - 100000, now - 100000))

    # GCを実行
    deleted_expired, deleted_orphans = maintenance.clean_garbage(
        tmp_max_age_seconds=86400
    )

    # 検証: tmpファイルの削除数は戻り値(DBレコード数, 孤立Blob数)には含まれないが、実体は消えているはず
    assert not old_tmp.exists()
