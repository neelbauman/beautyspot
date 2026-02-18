# tests/integration/test_pipeline_e2e.py

import pytest
from typer.testing import CliRunner
from beautyspot import Spot
from beautyspot.db import SQLiteTaskDB
from beautyspot.cli import app

runner = CliRunner()


@pytest.fixture
def spot_env(tmp_path):
    """
    E2Eテスト用の環境セットアップ。
    実ファイルベースのSQLite DBを作成します。
    """
    db_path = tmp_path / "e2e_pipeline.db"
    # Spotインスタンスを作成（これがユーザーの起点となります）
    spot = Spot(name="e2e_test", db=SQLiteTaskDB(db_path))
    return spot, db_path


def test_ml_pipeline_lifecycle(spot_env):
    """
    ユーザーシナリオ: MLパイプラインの構築、実行、修正、そしてCLIによる確認。

    Steps:
    1. 初回実行: 全タスクが実行されること。
    2. キャッシュ利用: 2回目は全タスクがキャッシュから読み込まれること。
    3. ロジック変更: 中間タスクのバージョンを上げた際、それ以降のみ再実行されること。
    4. CLI連携: 保存されたDBに対してCLIコマンド(stats)が機能すること。
    """
    spot, db_path = spot_env

    # 実行回数を追跡するためのカウンタ
    call_counts = {"load": 0, "process": 0, "train": 0}

    # --- Step 1: パイプライン定義 (Initial Version) ---

    @spot.mark(version="v1")
    def load_data(source_id: str):
        """データを外部からロードする想定のタスク"""
        call_counts["load"] += 1
        return {"data": [1, 2, 3, 4, 5], "source": source_id}

    @spot.mark(version="v1")
    def preprocess(raw_data: dict):
        """データを加工するタスク"""
        call_counts["process"] += 1
        return [x * 10 for x in raw_data["data"]]

    @spot.mark(version="v1")
    def train_model(features: list):
        """モデルを学習（集計）するタスク"""
        call_counts["train"] += 1
        return sum(features)

    # --- Step 2: 初回実行 ---
    print("\n--- Phase 1: Initial Run ---")
    data = load_data("dataset_A")
    features = preprocess(data)
    result = train_model(features)

    assert result == 150  # (1+2+3+4+5)*10 = 150
    assert call_counts["load"] == 1
    assert call_counts["process"] == 1
    assert call_counts["train"] == 1

    # --- Step 3: キャッシュヒットの確認 ---
    print("\n--- Phase 2: Cache Hit Run ---")
    # 同じ入力で再実行
    result_cached = train_model(preprocess(load_data("dataset_A")))

    assert result_cached == 150
    # カウンタが増えていない = キャッシュが使われた
    assert call_counts["load"] == 1
    assert call_counts["process"] == 1
    assert call_counts["train"] == 1

    # --- Step 4: バージョンアップ（ロジック変更） ---
    print("\n--- Phase 3: Version Upgrade (Preprocess) ---")

    # 前処理のロジックを変更 (x10 -> x20) し、バージョンを上げる
    # 注意: Pythonのデコレータの仕様上、同じ関数名で上書き定義することでシミュレート
    @spot.mark(version="v2")
    def preprocess_v2(
        raw_data: dict,
    ):  # func_name="preprocess" として登録したい場合は明示が必要だが、
        # ここではフローのテストなので別関数として扱うか、
        # 実践的にはコードを書き換える挙動を模倣する。
        # ここでは依存関係の連鎖を見たいので、新しい関数として定義し、
        # パイプラインに組み込む。
        call_counts["process"] += 1
        return [x * 20 for x in raw_data["data"]]

    # パイプラインの一部を差し替えて実行
    # load_data("dataset_A") は v1 のまま呼び出し -> キャッシュヒットするはず
    # preprocess_v2 は v2 なので新規実行 -> カウントアップ
    # train_model は入力が変わるため（preprocessの結果が変わる）、キャッシュミスして再実行 -> カウントアップ

    data_v2 = load_data("dataset_A")
    features_v2 = preprocess_v2(data_v2)
    result_v2 = train_model(features_v2)

    assert result_v2 == 300  # (15)*20 = 300

    # 検証
    assert call_counts["load"] == 1  # 変わらず (Cache Hit)
    assert call_counts["process"] == 2  # +1 (New Version)
    assert call_counts["train"] == 2  # +1 (Input Changed)

    # --- Step 5: CLI インテグレーション ---
    print("\n--- Phase 4: CLI Stats Check ---")

    # 生成されたDBファイルに対してCLIコマンドを実行
    cli_result = runner.invoke(app, ["stats", str(db_path)])

    assert cli_result.exit_code == 0
    # 出力に含まれるべきキーワードの検証
    assert "Overview" in cli_result.stdout
    assert "Total Tasks" in cli_result.stdout

    # 関数名が記録されているか
    assert "load_data" in cli_result.stdout
    assert "train_model" in cli_result.stdout
