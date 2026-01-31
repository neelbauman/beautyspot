![beautyspot_logo](docs/statics/img/beautyspot_logo_with_typo_1.jpeg)

# beautyspot v2

* [公式ドキュメント](https://neelbauman.github.io/beautyspot/)
* [PyPI](https://pypi.org/project/beautyspot/)
* [ライセンス](https://opensource.org/licenses/MIT)

**"You focus on the logic. We handle the rest."**

`beautyspot` は、データ分析パイプラインやバッチ処理のための「黒子（Kuroko）」ライブラリです。
たった1行のデコレータを追加するだけで、あなたの関数に「永続化キャッシュ」「レート制限」「リカバリ機能」「大規模データの退避」といったインフラ機能を与えます。

**v2.0 Update:**
クラス名を `Project` から **`Spot`** へ、デコレータを `@task` から **`@mark`** へ刷新しました。より直感的で、世界観に統一感のある API に生まれ変わりました。
また、実行時のキャッシュ制御を行う **`cached_run`** が導入されました。

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

## 🛠️ Usage Patterns

`beautyspot` は、利用シーンに合わせて2つのアプローチを提供します。

### 1. Definition Time (`@spot.mark`)

アプリケーションのコアロジックや、常にキャッシュしたい関数に使用します。

```python
@spot.mark
def rigid_task(data):
    # ...
    return result

```

### 2. Execution Time (`with spot.cached_run`)

既存のライブラリ関数や、特定のブロック内だけで設定を変えてキャッシュしたい場合に使用します。
v2.0 から導入された推奨パターンです。

```python
from external_lib import simulation

# このブロック内だけ、simulation関数はキャッシュ機能付きになります
with spot.cached_run(simulation, version="v2") as sim:
    result = sim(data)

# 複数の関数もサポート
with spot.cached_run(func_a, func_b) as (task_a, task_b):
    task_a()
    task_b()

```

---

## 💡 Key Features

### 1. Spot & Mark Architecture (New in v2.0)

v2.0 では、概念を再定義しました。

* **Spot (`bs.Spot`):** データの保存先、DB接続、レート制限の設定などを管理する「実行コンテキスト」。
* **Mark (`@spot.mark`):** 「この関数は Spot の管理下に置く」という宣言。

### 2. Declarative Caching Strategies (New in v2.0)

**"Cache what matters."**

関数の引数に応じて、どのようにキャッシュキーを生成するかを宣言的に定義できます。
「ログ設定は無視する」「ファイルの中身を見て判定する」といった高度な制御が可能です。

```python
from beautyspot.cachekey import KeyGen

# verboseフラグは無視し、config_pathは中身を読んでハッシュ化
@spot.mark(input_key_fn=KeyGen.map(
    verbose=KeyGen.IGNORE,
    config_path=KeyGen.FILE_CONTENT
))
def run_simulation(config_path, verbose=True):
    ...

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
| **Imperative** | `project.run(func, ...)` | `with spot.cached_run(func) as task: task(...)` |

※ `spot.run` は v2.0 で非推奨となりました。今後は `cached_run` を使用してください。

---

## 📊 Dashboard

キャッシュされたデータや実行履歴を可視化する簡易ダッシュボードが付属しています。

```bash
# この依存関係が必要
uv add beautyspot[dashboard]

# DBファイルを指定して起動
beautyspot ui ./.beautyspot/my_experiment.db

```

---

## 🤝 License

MIT License

