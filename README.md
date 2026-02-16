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

