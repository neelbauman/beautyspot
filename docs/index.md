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

`beautyspot` は、単なるキャッシュライブラリではありません。
「実行コンテキスト（Spot）」という概念を通じて、データの永続化、セキュリティ、流量制御、そしてインフラの抽象化を一手に引き受ける「黒子（Kuroko）」です。

このガイドでは、各機能の詳細な解説を行い、最後にそれら全てを組み合わせた **「究極のユースケース（The Ultimate Usage）」** を構築します。

---

## 1. Core Concepts: Spot & Mark (v2.0)

v2.0 より、API はより直感的な `Spot` と `mark` という概念に刷新されました。

* **Spot (場所/現場):** データ保存先、DB接続、レート制限の設定などを管理する「実行コンテキスト」。
* **Mark (印付け):** 「この関数は Spot の管理下に置く」という宣言。

```python
import beautyspot as bs

# 1. Spot (現場) を定義
spot = bs.Spot("my_analysis")

# 2. Mark (印) を付ける
@spot.mark
def process(data):
    return data * 2

```

---

## 2. Feature Deep Dive

### 🛡️ 1. Secure Serialization (Msgpack & Custom Types)

**"No more Pickle."**
`beautyspot` はデフォルトで安全かつ高速な **Msgpack** を採用しています。

Msgpack が標準で対応していない型（例: 自作クラス）を扱う場合、`register_type` で変換ロジックを登録します。

```python
class MyModel:
    def __init__(self, name): self.name = name

# 変換ロジックの登録 (Code: 0-127)
spot.register_type(
    type_=MyModel,
    code=10,
    encoder=lambda obj: obj.name.encode('utf-8'),
    decoder=lambda data: MyModel(data.decode('utf-8'))
)

```

### 💾 2. Hybrid Storage Strategy

データのサイズに応じて、最適な保存先を自動で使い分けます。

* **Small Data:** SQLite (TaskDB) に直接 JSON/BLOB として保存。高速な検索が可能。
* **Large Data (`save_blob=True`):** 画像や巨大な配列は Storage (File/S3) に逃がし、DBにはそのパスのみを記録。DBの肥大化を防ぎます。

```python
@spot.mark(save_blob=True)  # 巨大データはBlobへ
def generate_image():
    return b"..." * 1024 * 1024

```

### 🚦 3. Rate Limiting (GCRA)

API 制限（例: 1分間に100回まで）を守るために、**GCRA (Generic Cell Rate Algorithm)** ベースのリミッターを搭載しています。
単純なスリープとは異なり、理論上の到達時刻（TAT）を計算することで、バースト（集中アクセス）を物理的に防ぎます。

```python
# TPM (Tokens Per Minute) = 60 (1秒に1回)
spot = bs.Spot("api_client", tpm=60)

@spot.mark
@spot.limiter(cost=1)  # 1回の実行で1トークン消費
def call_api():
    ...

```

### 🧩 4. Dependency Injection (Custom Backend)

`Spot` のバックエンド（DBとストレージ）は、インターフェースさえ満たせば何にでも差し替え可能です。
これにより、「ローカル実験」から「クラウド本番環境」への移行が、コードの変更なし（設定の注入のみ）で実現します。

* **TaskDB:** メタデータ管理 (SQLite, Postgres, Redis...)
* **Storage:** 実データ保存 (Local, S3, GCS...)

---

## 3. 🚀 The Advanced Use Case: "All-in-One Pipeline"

これら全ての機能を組み合わせた、高度なデータパイプラインの例を構築します。

**シナリオ:**

* **入力:** S3上の巨大なログファイル群。
* **処理:** 外部APIを使ってデータを解析（レート制限が必要）。
* **出力:** 解析結果のカスタムオブジェクト（Msgpack拡張）。
* **インフラ:**
* メタデータは **Redis** で高速に共有管理したい（Custom DB）。
* 結果のオブジェクトは **GCS (Google Cloud Storage)** に保存したい（Custom Storage）。
* ファイルの更新日時を見て、変更があった場合のみ再計算したい（Smart Caching）。



### Implementation

```python
import os
import json
import time
from typing import Any, Dict, Optional

import redis
from google.cloud import storage as gcs

import beautyspot as bs
from beautyspot.db import TaskDB
from beautyspot.storage import BlobStorageBase
from beautyspot.cachekey import KeyGen

# --- 1. Custom Components Implementation ---

class RedisTaskDB(TaskDB):
    """メタデータをRedisで管理するカスタムDB"""
    def __init__(self, host="localhost", port=6379):
        self.r = redis.Redis(host=host, port=port, decode_responses=True)

    def init_schema(self): pass  # Schema-less

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        data = self.r.get(f"task:{cache_key}")
        return json.loads(data) if data else None

    def save(self, cache_key, func_name, input_id, version, result_type, 
             content_type, result_value=None, result_data=None):
        # 簡略化のため result_data (bytes) は無視する実装例
        record = {
            "func_name": func_name, "input_id": input_id, "version": version,
            "result_type": result_type, "content_type": content_type,
            "result_value": result_value
        }
        self.r.set(f"task:{cache_key}", json.dumps(record))
    
    def get_history(self, limit=1000): return [] # 省略

class GCSStorage(BlobStorageBase):
    """実データをGCSに保存するカスタムストレージ"""
    def __init__(self, bucket_name, prefix="cache"):
        self.bucket = gcs.Client().bucket(bucket_name)
        self.prefix = prefix

    def save(self, key: str, data: bytes) -> str:
        blob = self.bucket.blob(f"{self.prefix}/{key}.bin")
        blob.upload_from_string(data)
        return f"gs://{self.bucket.name}/{blob.name}"

    def load(self, location: str) -> bytes:
        # gs://bucket/path... からデータをロード
        blob_path = location.split("/", 3)[-1]
        return self.bucket.blob(blob_path).download_as_bytes()

# --- 2. Custom Data Type ---

class AnalysisResult:
    """API解析結果を保持するカスタムクラス"""
    def __init__(self, score: float, summary: str):
        self.score = score
        self.summary = summary

# --- 3. Constructing the "Spot" ---

# 依存性の注入 (Dependency Injection)
my_db = RedisTaskDB(host="redis-server")
my_storage = GCSStorage(bucket_name="my-app-blobs")

# Spotの初期化
# tpm=60: API制限 (1分間に60回) を設定
spot = bs.Spot(
    name="production_pipeline",
    db=my_db,
    storage=my_storage,
    tpm=60
)

# カスタム型の登録
spot.register_type(
    type_=AnalysisResult,
    code=20,
    encoder=lambda o: json.dumps({"s": o.score, "t": o.summary}).encode(),
    decoder=lambda b: AnalysisResult(**{k:v for k,v in json.loads(b).items() if k in ["s","t"]}) # 簡易実装
)

# --- 4. The "Marked" Logic ---

@spot.mark(
    save_blob=True,                     # 1. 結果はGCSへ (Blob)
    input_key_fn=KeyGen.from_path_stat, # 2. ファイルのタイムスタンプを見てキャッシュ判定
    version="v2.0.1",                   # 3. ロジック変更時はここを変えてキャッシュ無効化
    content_type="application/json"     # 4. ダッシュボード表示用ヒント
)
@spot.limiter(cost=1)                   # 5. レート制限を適用 (RedisDB使用時もBucketはメモリ上で動作)
def analyze_log_file(file_path: str) -> AnalysisResult:
    """
    重い処理の実体。
    - ファイルに変更がなければ、Redisへの問い合わせだけでGCSのパスが返る (実行時間ほぼ0)
    - 変更があれば、API制限を守りながら実行し、結果をGCSに保存して返す
    """
    print(f"Processing {file_path}...")
    
    # Simulate API Call setup
    time.sleep(0.5) 
    
    # Return custom object
    return AnalysisResult(score=0.95, summary=f"Processed {os.path.basename(file_path)}")

# --- 5. Execution ---

if __name__ == "__main__":
    files = ["/data/log1.txt", "/data/log2.txt"]
    
    for f in files:
        # 初回: 実行される
        # 2回目: Redisからキャッシュメタデータを取得 -> GCSから実体をダウンロードして復元
        result = analyze_log_file(f)
        print(f"Result: {result.summary}")

```

### この構成のメリット

1. **スケーラビリティ:** Redis を使うことで、複数のワーカープロセス（あるいはサーバー）間でキャッシュ状況を共有できます（※注: TokenBucketの状態共有には別途Redis対応の実装が必要ですが、メタデータ共有はこれだけで可能です）。
2. **安全性:** Msgpack を使っているため、GCS上のデータが改ざんされても RCE (Remote Code Execution) のリスクがありません。
3. **コスト削減:** `save_blob=True` と `input_key_fn` により、ファイルに変更がない限り、高価な API コールと GCS への書き込みが発生しません。
4. **コードの分離:** ビジネスロジック (`analyze_log_file`) には、DB接続やS3アップロードのコードが一切含まれていません。すべて `@spot` デコレータの裏側に隠蔽されています。

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

