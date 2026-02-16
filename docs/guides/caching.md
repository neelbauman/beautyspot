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

v2.0 の核心となる「ユーザーを待たせない設計」と「洗練されたライフサイクル管理」を、ユーザーが直感的に使いこなせるようドキュメントに落とし込みましょう。

特に **`wait=False` による高速化** と、**`with spot:` による同期（Flush）** の関係を明確にすることが、v2.0 移行ユーザーへの最大のバリューになります。

---

### 1. `docs/guides/caching.md` への追記案

**テーマ: パフォーマンス最適化（非ブロッキング保存）**

```markdown
## 非ブロッキング保存 (Fire-and-Forget)

デフォルトでは、`beautyspot` はデータの整合性を保証するために、ストレージへの保存が完了してから関数を終了します。しかし、巨大なモデルや大量のデータを扱う場合、保存処理（シリアライズやアップロード）がボトルネックになることがあります。

v2.0 では、`wait=False` オプションを使用することで、保存処理をバックグラウンドに逃がし、メイン処理を即座に続行できます。

### 基本的な使い方

`Spot` 初期化時にグローバル設定とするか、個別のタスクごとに設定可能です。

```python
# グローバル設定: すべてのタスクを待たずにバックグラウンド保存する
spot = Spot(name="my_app", default_wait=False)

@spot.mark
def heavy_task(data):
    # 重い計算...
    return result 
    # 計算が終わった瞬間に return される（保存完了を待たない）

```

### 個別のタスクで制御する

特定のタスクだけ保存完了を待ちたい（例：確実に保存されたことを確認して次のステップへ進みたい）場合は、引数で上書きします。

```python
@spot.mark(wait=True)  # このタスクだけは保存完了までブロックする
def critical_task():
    ...

```

