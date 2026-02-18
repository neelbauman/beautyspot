![beautyspot_logo](docs/statics/img/beautyspot_logo_with_typo_1.jpeg)

# beautyspot

* [公式ドキュメント](https://neelbauman.github.io/beautyspot/)
* [PyPI](https://pypi.org/project/beautyspot/)
* [ライセンス](https://opensource.org/licenses/MIT)

---

`beautyspot` は、Python 関数の実行結果を透過的にキャッシュし、複雑なデータパイプラインや実験の再実行を高速化するための OSS ライブラリです。v2.0 では、インフラのオーバーヘッドを最小化する非同期保存機能と、柔軟なコンポーネント構成を可能にする DI（依存性注入）アーキテクチャが導入されました。

## 📦 Installation

```bash
uv add beautyspot
# or
pip install beautyspot

```

## ✨ Key Features

* **Non-blocking Caching**: キャッシュの保存をバックグラウンドで実行し、メイン処理のレイテンシを排除します。
* **Dependency Injection**: DB、ストレージ、シリアライザを自由に入れ替え可能な柔軟な設計。
* **Smart Lifecycle Management**: `with` ブロックを使用して、バックグラウンドタスクの完了を確実に同期できます。
* **Type-safe Serialization**: `msgpack` をベースとした、カスタムクラス対応の高速なシリアライズ。
* **Rate Limiting**: API コールなどの実行頻度をトークンバケットアルゴリズムで制御。

## 🚀 Quick Start (v2.0)

v2.0 からは `Spot` インスタンスにコンポーネントを注入して使用します。

```python
import beautyspot as bs

# カスタム
# from beautyspot.db import SQLiteTaskDB
# from beautyspot.storage import LocalStorage
# from beautyspot.serializer import MsgpackSerializer

# 1. コンポーネントの準備
# db = SQLiteTaskDB(".beautyspot/tasks.db")
# storage = LocalStorage(".beautyspot/blobs")
# serializer = MsgpackSerializer()

# 2. Spot の初期化 (default_wait=False で高速化)
spot = bs.Spot(
    name="my_app",
#    db=db,
#    storage=storage,
#    serializer=serializer,
    default_wait=False  # 保存を待たずに次へ進む
)

# 3. タスクの登録
@spot.mark(version="v1")
def heavy_computation(x: int):
    # 重い処理...
    return x * 10

# 4. 実行
with spot:
    result = heavy_computation(5)
    # ブロックを抜ける際、未完了の保存タスクが完了するのを待機します

```

## ⚡ Performance & Lifecycle

### Non-blocking Persistence

`wait=False` オプションを使用すると、計算が終了した瞬間に結果が返されます。シリアライズやクラウドストレージへのアップロードは裏側で並列実行されるため、関数の応答速度が劇的に向上します。

### Context-based Flush

`with spot:` ブロックは同期ポイントとして機能します。ブロックを抜ける際に、そのインスタンスが抱えているすべてのバックグラウンドタスクが完了するのを待機するため、データロストを防げます。また、一度抜けても `Spot` インスタンスは再利用可能です。

## 🛠 Advanced Usage

### Maintenance Service

キャッシュの削除やクリーンアップは、実行担当の `Spot` から切り離され、`MaintenanceService` に集約されました。

```python
from beautyspot.maintenance import MaintenanceService

admin = MaintenanceService(spot.db, spot.storage, spot.serializer)
admin.delete_task(cache_key="...")

```

## ⚠️ Migration Guide (v1.x -> v2.0)

v2.0 は破壊的変更を含むメジャーアップデートです。

* **`Project` -> `Spot**`: クラス名が変更されました。
* **`@task` -> `@mark**`: デコレータ名が変更されました。
* **`run()` メソッドの廃止**: 今後は `@mark` または `cached_run()` を使用してください。

## 📖 Documentation

詳細なガイドや API リファレンスについては、[Documentation (MkDocs)](https://www.google.com/search?q=mkdocs.yml) を参照してください。

## 📄 License

This project is licensed under the MIT License.

---

# What's next ?

### 1. 依存性の注入（DI）の「設定」の宣言化

現在、`Spot` インスタンスの初期化は非常に命令的（Imperative）です。
`README.md` の例 を見ると、ユーザーは以下のようにコンポーネントを自分で組み立てて注入する必要があります。

```python
# 現在の "How" アプローチ
db = SQLiteTaskDB(".beautyspot/tasks.db")
storage = LocalStorage(".beautyspot/blobs")
serializer = MsgpackSerializer()

spot = bs.Spot(name="my_app", db=db, storage=storage, serializer=serializer, ...)

```

これだと、ユーザーは「ローカル環境で動かしたい」という意図（What）を実現するために、具体的なクラスの組み立て方（How）を知っていなければなりません。

**改善案: Configuration Profiles**
設定ファイル（`pyproject.toml` や `beautyspot.yml`）や、プリセットを用いた宣言的な初期化を導入するのはどうでしょうか？

```python
# 改善後の "What" アプローチ（イメージ）
# "local-dev" というプロファイルを指定するだけ
spot = bs.Spot.from_profile("local-dev")

```

これにより、ユーザーはインフラの詳細から解放されます。

### 2. シリアライザ選択の自動ネゴシエーション (Content Negotiation)

現在、`core.py` では `serializer` を一つ受け取っています。
ユーザーは特定の型を扱うために `@spot.register` で手動でエンコーダ/デコーダを登録するか、カスタムシリアライザを実装する必要があります。これは「How」の負担が大きいです。

**改善案: Semantic Content Type**
ユーザーは「この関数は画像を返す」「これはPandas DataFrameを返す」という事実（What）だけを宣言し、最適なシリアライズ方式（msgpack なのか、parquet なのか、png なのか）は `beautyspot` が自動で決定する仕組みです。

```python
# ユーザーは "dataframe" であることだけを宣言
@spot.mark(content_type="dataframe")
def process_data(df):
    ...

```

システム側で「DataFrameならParquetで保存するのが効率的だ」と判断し、適切なバックエンド処理を行います。これは `core.py` の `_save_result_sync` 内のロジックを拡張することで実現できそうです。

### 3. キャッシュ無効化の「タグベース」管理

現在の `MaintenanceService` では、削除のために `cache_key` を指定するか、ADR 30 のように時間の経過（Retention）を待つしかありません。

「特定のデータセットに関連するキャッシュをすべて消したい」という要求（What）に対し、現在はユーザーが関連するキーを自力で管理・検索する（How）必要があります。

**改善案: Cache Tagging**
タスク定義時にタグを宣言できるようにします。

```python
@spot.mark(tags=["dataset_v1", "experiment_A"])
def train_model(): ...

```

そして、削除時はタグを指定します。
`spot.invalidate(tags=["experiment_A"])`

これにより、依存関係やグルーピングの管理という「How」をツール側に移譲できます。

