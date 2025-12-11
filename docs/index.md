# 🌑 beautyspot
```
uv run mkdocs gh-deploy
```

- [https://neelbauman.github.io/beautyspot/](https://neelbauman.github.io/beautyspot/)
- [https://pypi.org/project/beautyspot/](https://pypi.org/project/beautyspot/)
- [https://opensource.org/licenses/MIT](https://opensource.org/licenses/MIT)

## Concept

**"You focus on the logic. We handle the rest."**

生成AIのバッチ処理やスクレイピング、重い計算処理を行う際、本質的なロジック以外に以下のようなコードを書くのは大変ですよね。

* API制限を守るための `time.sleep()` やトークン計算
* 途中停止した際のリカバリ処理（ `try-except` と `continue` ）
* 結果を保存・ロードするためのファイルI/O
* 重複リクエストを防ぐためのID管理

`beautyspot` は、あなたのコードに「黒子/ほくろ（デコレータ）」を一つ付けるだけで、これらの面倒なインフラ制御をすべて引き受ける「黒子/くろこ」です。

軽量で少ない依存性で、ローカル開発にてこのようなインフラを手軽に利用できることを目指して開発されています。

v1.0.0 では、**デフォルトでの安全性（Secure by Default）** と **拡張性（Extensibility）** を強化しました。

---

## ⚡ Installation

```bash
pip install beautyspot
```

  * **Standard:** `msgpack` が同梱され、高速かつ安全に動作します。
  * **Options:**
      * `pip install "beautyspot[s3]"`: S3ストレージを利用する場合
      * `pip install "beautyspot[dashboard]"`: ダッシュボードを利用する場合
      * `pip install "beautyspot[all]"`: 全部入り

-----

## 🚀 Quick Start

関数に `@project.task` を付けるだけで、その関数および入出力は永続化され、同じ計算を無駄に多重に繰り返すことを華麗に回避します。

```python
import time
import beautyspot as bs

# プロジェクト定義（デフォルトで "./my_experiment.db" を作成）
project = bs.Project("my_experiment")

@project.task
def heavy_process(text):
    # 実行に時間がかかる処理や、課金されるAPIコール
    time.sleep(2)
    return f"Processed: {text}"

# バッチ処理
inputs = ["A", "B", "C", "A"]

for i in inputs:
    # 1. 初回の "A", "B", "C" は実行される
    # 2. 最後の "A" は、DBからキャッシュが即座に返る（実行時間0秒）
    # 3. 途中停止しても、次回は「未完了のタスク」だけが実行される
    print(heavy_process(i))
```

## 💡 Key Features

### 1\. Handle Any Data Size (and Securely)

**"No more Pickle risks."**

v1.0.0 から、デフォルトのシリアライザに **Msgpack** を採用しました。
Python標準の `pickle` と異なり、信頼できないデータを読み込んでも任意のコード実行（RCE）のリスクがありません。

データの保存方法は `save_blob` オプションで制御しますが、**どちらの場合も型の一貫性は保たれます。**

* **Small Data (`save_blob=False`)**:
    * デフォルト。SQLite内に直接保存されます。
    * **目安: 100KB 未満** のデータ（数値、短いテキスト、小さなNumpy配列など）に最適で、高速です。
* **Large Data (`save_blob=True`)**:
    * データを外部ファイル（Local/S3）に退避し、DBには参照のみを残します。
    * **目安: 100KB 以上** のデータ（画像、音声、巨大な埋め込みベクトルなど）で推奨されます。

> **⚠️ Note:** `save_blob=False` のまま巨大なデータ（デフォルトで1MB以上）を保存しようとすると、実行時に警告ログが出力されます。

```python
# Large Data -> Blobに退避 (Msgpackで保存)
@project.task(save_blob=True)
def download_image(url):
    return requests.get(url).content
```

### 2\. Custom Type Registration

Numpy配列や自作クラスなど、デフォルトで対応していない型も、変換ロジックを登録することで安全に扱えます。
この登録は、SQLite保存 / Blob保存 のどちらでも有効です。

```python
import numpy as np

# カスタム型の変換ロジックを登録
# code: 0-127 の一意なID
project.register_type(
    type_=np.ndarray,
    code=10,
    encoder=lambda x: x.tobytes(),
    decoder=lambda b: np.frombuffer(b)
)

@project.task(save_blob=True)
def create_array():
    return np.array([1, 2, 3])
```

### 3\. Flexible Backend with Dependency Injection

**"Start simple, scale later."**

通常はパスを指定するだけで SQLite が使えますが、大規模な並列処理やテストのために、バックエンドを自由に差し替えることができます（Dependency Injection）。

```python
from beautyspot.db import SQLiteTaskDB

# A. Standard Usage (Path string)
# 内部で SQLiteTaskDB("./data.db") が生成される
project = bs.Project("app", db="./data.db")

# B. Advanced Usage (Injection)
# 独自の設定を行ったDBインスタンスや、インメモリDB、
# あるいは自作の PostgresTaskDB などを注入可能
db_instance = SQLiteTaskDB("./data.db")
project = bs.Project("app", db=db_instance)
```

> 📖 **Guide:** PostgreSQL や MySQL を使用するカスタムアダプタの作成方法は [docs/advanced/custom\_backend.md](https://www.google.com/search?q=docs/advanced/custom_backend.md) を参照してください。

### 4\. Declarative Rate Limiting

APIの制限（例：1分間に1万トークン）を守るために、複雑なスリープ処理を書く必要はありません。
**GCRA (Generic Cell Rate Algorithm)** ベースの高性能なリミッターが、バースト（集中アクセス）を防ぎながらスムーズに実行を制御します。

```python
# 1分間に 50,000 トークンまでに制限
project = bs.Project("openai_batch", tpm=50000)

def calc_cost(text):
    return len(text)

@project.task
@project.limiter(cost=calc_cost)  # リトライ時も含めて自動制御
def call_api(text):
    return api.generate(text)
```

-----

## ⚠️ Migration Guide (v0.x -\> v1.0.0)

v1.0.0 ではシリアライザが `pickle` から `msgpack` に変更されたため、**v0.x で作成されたキャッシュ（特に `save_blob=True` のデータ）とは互換性がありません。**

アップデート時は、古い `.db` ファイルおよび `blobs/` ディレクトリを削除し、クリーンな状態で開始することを推奨します。

-----

## 📊 Dashboard (Result Viewer)

**"Minimal viewer, not a full tracer."**

ダッシュボードは、あくまで\*\*「実行状況（戻り値）の確認」**と**「キャッシュDBが破綻していないかの確認」\*\*に特化しています。
Blobとして退避された巨大な戻り値も、ここから自動的に復元してプレビュー可能です（Mermaid, Graphviz, Image, JSON等）。

```bash
# プロジェクトのDBファイルを指定して起動
$ beautyspot ui ./my_experiment.db
```

> **Note:**
> 付属のダッシュボードは、デフォルトの **SQLite バックエンド専用** です。
> カスタムバックエンド（PostgreSQL等）を使用している場合、このダッシュボードは利用できません。その場合は Metabase や SQL クライアント等の利用を推奨します。

-----

## 🤝 License

MIT License

