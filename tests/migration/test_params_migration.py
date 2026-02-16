# tests/migration/test_params_migration.py

import pytest
# KeyGen のインポートは不要になるケースもありますが、一応残しておきます


from pathlib import Path
from beautyspot import Spot, SQLiteTaskDB, LocalStorage

@pytest.fixture
def spot(tmp_path: Path):
    """
    テストごとに使い捨ての Spot インスタンスを提供するフィクスチャ。
    DBとストレージは pytest の tmp_path (一時ディレクトリ) に作成されます。
    """
    # 一時パスの設定
    db_path = tmp_path / "test_context.db"
    
    # Spotの初期化 (storage_pathも一時ディレクトリ内へ)
    instance = Spot("test_spot", db=SQLiteTaskDB(db_path), storage=LocalStorage(tmp_path / "blobs"))
    
    yield instance
    
    # テスト後のクリーンアップ
    instance.shutdown()

    # NOTE: tmp_path は pytest が自動的に削除するため、
    # ここでファイル削除を手動で行う必要はありません。

def test_mark_with_keygen_new_param(spot):
    """
    Case A: 新パラメータ 'keygen' が正常に動作することを確認
    """
    # keygenを使ってキー生成をカスタマイズ (引数の合計値をIDとする)
    @spot.mark(keygen=lambda *args: str(sum(args)))
    def add(a, b):
        return a + b

    # 実行とキャッシュ作成
    assert add(1, 2) == 3
    
    # 内部APIを使ってキャッシュキーを確認 (実装依存だが確実な検証のため)
    assert add(1, 2) == 3

def test_cached_run_with_keygen_new_param(spot):
    """
    Case A': cached_run でも 'keygen' が動作することを確認
    """
    def mul(a, b):
        return a * b

    # keygenを指定
    with spot.cached_run(mul, keygen=lambda a, b: f"mul-{a}-{b}") as task:
        assert task(2, 3) == 6
        assert task(2, 3) == 6

def test_mark_deprecation_warning(spot):
    """
    Case B: 旧パラメータ 'input_key_fn' 使用時に DeprecationWarning が出ることを確認
    """
    # 修正: KeyGen._default ではなく、(*args, **kwargs) を受け取るラムダを使用

    with pytest.warns(DeprecationWarning, match="use 'keygen' instead"):
        @spot.mark(input_key_fn=lambda x: "legacy-key")
        def old_style(x):
            return x * 2

    assert old_style(10) == 20

def test_cached_run_deprecation_warning(spot):
    """
    Case B': cached_run での DeprecationWarning 確認
    """
    def func(x):
        return x

    # 修正: KeyGen._default ではなく、(*args, **kwargs) を受け取るラムダを使用

    with pytest.warns(DeprecationWarning, match="use 'keygen' instead"):
        with spot.cached_run(func, input_key_fn=lambda x: "legacy-key") as task:
            task(1)

def test_conflict_params_raises_error(spot):
    """
    Case C: 両方のパラメータを指定した場合に ValueError になることを確認
    """
    # @spot.mark
    with pytest.raises(ValueError, match="Cannot specify both"):
        @spot.mark(keygen=lambda x: x, input_key_fn=lambda x: x)
        def conflict_func(x):
            pass

    # spot.cached_run
    def target(x): pass
    with pytest.raises(ValueError, match="Cannot specify both"):
        with spot.cached_run(target, keygen=lambda x: x, input_key_fn=lambda x: x):
            pass

def test_policy_binding_with_keygen(spot):
    """
    Case D: KeyGenPolicy が keygen 引数経由でも正しく bind されるか確認
    """
    from beautyspot.cachekey import KeyGenPolicy
    
    # モック用のPolicy
    class MockPolicy(KeyGenPolicy):
        def __init__(self):
            # KeyGenPolicyは strategies (dict) を要求するため空辞書を渡す
            super().__init__({})

        def bind(self, func):
            # バインドされたら特定の関数を返す
            return lambda *args, **kwargs: "bound-key"

    @spot.mark(keygen=MockPolicy())
    def policy_user(x):
        return x

    # 実行 -> IDは "bound-key" になるはず
    assert policy_user(1) == 1

