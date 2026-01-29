# Caching Strategies

`beautyspot` の強力な機能の一つは、関数の引数に基づいて柔軟にキャッシュキーを生成できることです。
デフォルトではすべての引数を安全にハッシュ化しますが、実世界のユースケースに合わせて、より宣言的かつ高度な制御が可能です。

## デフォルトの挙動

`Spot.mark` でデコレートされた関数は、引数 (`args`, `kwargs`) の内容が少しでも変わると「別のタスク」として扱われます。
`beautyspot` は引数の構造（辞書、リスト、Numpy配列、Pydanticモデルなど）を再帰的に **正規化 (Canonicalize)** し、順序に依存しない安定したハッシュを生成します。

```python
@spot.mark
def process(data):
    # data の内容（dictの順序などが違っても中身が同じなら）に基づいて
    # 同一のキャッシュキーが生成されます。
    ...

```

---

## 高度な制御: KeyGen Policy

v2.0 以降、`KeyGen` クラスを使用して、引数ごとのキャッシュ戦略を宣言的に定義できるようになりました。

### 1. 特定の引数を無視する (`KeyGen.ignore`)

ログ出力フラグ、デバッグ用のオプション、あるいはロガーインスタンスなど、**計算結果（＝キャッシュすべき値）に影響を与えない引数** は、ハッシュ計算から除外すべきです。これらが変わるたびにキャッシュミスが発生するのを防ぎます。

```python
from beautyspot.cachekey import KeyGen

# verbose や logger が変わっても、data が同じならキャッシュはヒットします
@spot.mark(input_key_fn=KeyGen.ignore("verbose", "logger"))
def heavy_task(data, verbose=False, logger=None):
    if verbose:
        print("Processing...")
    return data * 2

```

### 2. ファイルベースのキャッシュ

引数としてファイルパスを受け取る場合、デフォルトでは「パスの文字列」だけがハッシュ化されます。
ファイル名が同じでも「ファイルの中身」が変わった時に再計算させたい（あるいはその逆）場合は、以下の戦略を使用します。

| 戦略 | メソッド | 説明 | ユースケース |
| --- | --- | --- | --- |
| **Strict** | `KeyGen.file_content` | ファイルの中身を全読み込みしてハッシュ化します。 | 設定ファイル、小さなデータセット |
| **Fast** | `KeyGen.path_stat` | サイズと更新日時(mtime)のみを確認します。高速です。 | 巨大なログファイル、映像データ |

### 3. 戦略の組み合わせ (`KeyGen.map`)

`KeyGen.map` を使うと、引数ごとに異なる戦略を詳細に定義できます。これが最も柔軟な方法です。

```python
@spot.mark(input_key_fn=KeyGen.map(
    # data_path はメタデータ(サイズ+日付)でチェック（高速化）
    data_path=KeyGen.PATH_STAT,
    
    # config_path は中身を厳密にチェック（確実性）
    config_path=KeyGen.FILE_CONTENT,
    
    # debug_mode は計算結果に関係ないので無視
    debug_mode=KeyGen.IGNORE
))
def analyze(data_path, config_path, debug_mode=False):
    # ... 重い分析処理 ...
    pass

```

!!! note "Note"
`KeyGen` ポリシーは、関数がどのように呼び出されたか（位置引数かキーワード引数か）に関わらず、引数名に基づいて正しく適用されます。

## カスタムキー生成（Advanced）

上記のポリシーでカバーできない特殊なケースでは、独自の関数を `input_key_fn` に渡すことも可能です。

```python
def custom_key_generator(*args, **kwargs):
    # 独自のロジックで文字列を返す
    return f"custom-{args[0].id}"

@spot.mark(input_key_fn=custom_key_generator)
def my_func(obj):
    ...

```

