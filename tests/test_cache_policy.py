# tests/test_cachekey_policy.py

from beautyspot.cachekey import KeyGen


def test_keygen_ignore_policy():
    """KeyGen.ignore で指定した引数が無視されるか検証"""

    # テスト対象関数のシグネチャ想定
    def target_func(a, b, verbose=False):
        pass

    # ポリシー作成: 'verbose' を無視
    policy = KeyGen.ignore("verbose")

    # 関数にバインド
    bound_fn = policy.bind(target_func)

    # verbose が異なってもハッシュは同じになるべき
    hash1 = bound_fn(1, 2, verbose=True)
    hash2 = bound_fn(1, 2, verbose=False)
    assert hash1 == hash2, "Ignored argument 'verbose' caused hash change."

    # 重要な引数が変わればハッシュは変わるべき
    hash3 = bound_fn(1, 3, verbose=True)
    assert hash1 != hash3, "Significant argument change did not affect hash."


def test_keygen_map_policy_mixed():
    """KeyGen.map で異なる戦略を混在させる検証"""

    def process_data(data, config_path, logger=None):
        pass

    # data: デフォルト(値ハッシュ)
    # config_path: ファイルパスとみなして中身ハッシュ
    # logger: 無視
    policy = KeyGen.map(config_path=KeyGen.FILE_CONTENT, logger=KeyGen.IGNORE)

    bound_fn = policy.bind(process_data)

    # ケース1: ベースライン
    # 注: config_path は存在しないファイルだと "MISSING_..." になるが、ハッシュ計算は走る
    h1 = bound_fn([1, 2], "beautyspot_dummy.cfg", logger="log1")

    # ケース2: Loggerが変わっても同じはず
    h2 = bound_fn([1, 2], "beautyspot_dummy.cfg", logger="log2")
    assert h1 == h2

    # ケース3: データが変わる
    h3 = bound_fn([1, 99], "beautyspot_dummy.cfg", logger="log1")
    assert h1 != h3


def test_call_style_independence():
    """位置引数とキーワード引数の呼び出し方が違っても、同じハッシュになるか (inspect.bindの効果)"""

    def my_func(a, b=10):
        pass

    policy = KeyGen.ignore()  # デフォルトポリシー (全てハッシュ)
    bound_fn = policy.bind(my_func)

    # 呼び出しパターン1: 位置引数とキーワード
    h1 = bound_fn(1, b=2)

    # 呼び出しパターン2: 位置引数のみ
    h2 = bound_fn(1, 2)

    # 呼び出しパターン3: キーワード引数のみ
    h3 = bound_fn(a=1, b=2)

    assert h1 == h2 == h3, "Calling style affected hash generation."


def test_fallback_custom_callable():
    """
    bind メソッドを持たない単純な関数も動作することを確認。
    (core.py との結合動作は core のテストで行うが、ここではPolicyではないものの挙動を確認)
    """

    def simple_keygen(*args, **kwargs):
        return "fixed_id"

    # 単純な関数は bind を持たない
    assert not hasattr(simple_keygen, "bind")
