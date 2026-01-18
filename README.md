# 🌑 beautyspot v2

- [公式ドキュメント](https://neelbauman.github.io/beautyspot/)
- [PyPI](https://pypi.org/project/beautyspot/)
- [ライセンス](https://opensource.org/licenses/MIT)

**"You focus on the logic. We handle the rest."**

`beautyspot` は、データ分析パイプラインやバッチ処理のための「黒子（Kuroko）」ライブラリです。
たった1行のデコレータを追加するだけで、あなたの関数に「永続化キャッシュ」「レート制限」「リカバリ機能」「大規模データの退避」といったインフラ機能を与えます。

**v2.0 Update:**
クラス名を `Project` から **`Spot`** へ、デコレータを `@task` から **`@mark`** へ刷新しました。より直感的で、世界観に統一感のある API に生まれ変わりました。

---

## ⚡ Installation

```bash
pip install beautyspot

```

* **Standard:** `msgpack` が同梱され、高速かつ安全に動作します。ローカルでの基本的なキャッシュ機能のみ。
* **Options:**
* `pip install "beautyspot[all]"`: 全部入り
* `pip install "beautyspot[s3]"`: S3互換ストレージを利用する場合
* `pip install "beautyspot[dashboard]"`: ダッシュボードを利用する場合



---

## 🚀 Quick Start

関数に `@spot.mark` を付けるだけで、その場所（Spot）は管理下に置かれ、無駄なリクエストや計算が繰り返されることを華麗に回避します。

```python
import time
import beautyspot as bs

# 1. Spot (現場/コンテキスト) を定義
# デフォルトで "./my_experiment.db" (SQLite) が作成されます
spot = bs.Spot("my_experiment")

# 2. Mark (印) を付ける
@spot.mark
def heavy_process(text):
    # 実行に時間がかかる処理や、課金されるAPIコール
    time.sleep(2)
    return f"Processed: {text}"

# バッチ処理
inputs = ["A", "B", "C", "A"]

for i in inputs:
    # 1. 初回の "A", "B", "C" は実行される
    # 2. 最後の "A" は、DBからキャッシュが即座に返る（実行時間0秒）
    print(heavy_process(i))

```

---

## 💡 Key Features

### 1. Spot & Mark Architecture (New in v2.0)

v2.0 では、概念を再定義しました。

* **Spot (`bs.Spot`):** データの保存先、DB接続、レート制限の設定などを管理する「実行コンテキスト」。
* **Mark (`@spot.mark`):** 「この関数は Spot の管理下に置く」という宣言。

### 2. Secure by Default (Msgpack)

**"No more Pickle risks."**
v1.0 以降、デフォルトのシリアライザに **Msgpack** を採用しています。
Python標準の `pickle` と異なり、信頼できないデータを読み込んでも任意のコード実行（RCE）のリスクがありません。

```python
# Msgpack非対応のカスタム型も、安全に登録可能
spot.register_type(
    type_=MyClass,
    code=10, 
    encoder=lambda x: x.to_bytes(),
    decoder=lambda b: MyClass.from_bytes(b)
)

```

### 3. Hybrid Storage Strategy

関数の戻り値が巨大になる場合（画像、音声、大規模なHTMLなど）、`save_blob=True` を指定してください。
`beautyspot` が自動的にデータを外部ストレージ（Local/S3/GCS）へ逃がし、DBには軽量な参照のみを残します。

```python
# Large Data -> Blobに退避
@spot.mark(save_blob=True)
def download_image(url):
    return requests.get(url).content

```

### 4. Dependency Injection (Flexible Backend)

**"Start simple, scale later."**
プロトタイプ段階では SQLite とローカルファイルで。本番運用では Redis と S3 で。
コード（ロジック）を一切書き換えることなく、`Spot` への注入（Injection）を変えるだけでインフラを移行できます。

```python
from beautyspot.db import SQLiteTaskDB
from beautyspot.storage import S3Storage

# 本番構成: メタデータはSQLite、実データはS3へ
spot = bs.Spot(
    "production_app",
    db=SQLiteTaskDB("./meta.db"),
    storage=S3Storage("s3://my-bucket/cache")
)

```

### 5. Declarative Rate Limiting

APIの制限（例：1分間に60リクエスト）を守るために、複雑なスリープ処理を書く必要はありません。
**GCRA (Generic Cell Rate Algorithm)** ベースの高性能なリミッターが、バーストを防ぎながらスムーズに実行を制御します。

```python
spot = bs.Spot("api_client", tpm=60)  # 60 Tokens Per Minute

@spot.mark
@spot.limiter(cost=1)  # 自動的にレート制限がかかる
def call_api(text):
    return api.generate(text)

```

---

## ⚠️ Migration Guide (v1.x -> v2.0)

v2.0 では API の破壊的変更が行われました。以下の通りにコードを修正してください。

| Feature | v1.x (Old) | v2.0 (New) |
| --- | --- | --- |
| **Class** | `project = bs.Project("name")` | `spot = bs.Spot("name")` |
| **Decorator** | `@project.task` | `@spot.mark` |
| **Imperative** | `project.run(func, ...)` | `spot.run(func, ...)` |

※ データベーススキーマやキャッシュファイルの構造には変更がないため、v1.x で作成した `.db` ファイルや Blob はそのまま読み込み可能です。

---

## 📊 Dashboard

キャッシュされたデータや実行履歴を可視化する簡易ダッシュボードが付属しています。

```bash
# DBファイルを指定して起動
$ beautyspot ui ./.beautyspot/my_experiment.db

```

---

## 🤝 License

MIT License

