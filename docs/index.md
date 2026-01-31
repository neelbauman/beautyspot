# beautyspot

![beautyspot_logo](statics/img/beautyspot_logo_with_typo.jpeg)

- [公式ドキュメント](https://neelbauman.github.io/beautyspot/)
- [PyPI](https://pypi.org/project/beautyspot/)
- [ライセンス](https://opensource.org/licenses/MIT)

## Concept

**"You focus on the logic. We handle the rest."**

生成AIのバッチ処理やスクレイピング、重い計算処理を行う際、本質的なロジック以外に以下のようなコードを書くのは大変ですよね。

* API制限を守るための `time.sleep()` やトークン計算
* 途中停止した際のリカバリ処理（ `try-except` と `continue` ）
* 結果を保存・ロードするためのファイルI/O
* 重複リクエストを防ぐためのID管理

`beautyspot` は、あなたのコードに「黒子/ほくろ（デコレータ）」を一つ付けるだけで、これらの面倒なインフラ制御をすべて引き受ける「黒子/くろこ」です。

軽量で少ない依存性で、ローカル開発にてこのようなインフラを手軽に利用できることを目指して開発されています。

v2.0.0 では、APIを直感的な **Spot & Mark** の概念に刷新し、実行時の柔軟な制御を可能にする **cached_run** を導入しました。

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



---

## 🚀 Quick Start

関数に `@spot.mark` を付けるだけで、その関数および入出力は永続化され、同じ計算を無駄に多重に繰り返すことを華麗に回避します。

```python
import time
import beautyspot as bs

# 1. Spot (現場/実行コンテキスト) を定義
# デフォルトで "./my_experiment.db" を作成
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
    # 3. 途中停止しても、次回は「未完了のタスク」だけが実行される
    print(heavy_process(i))

```

## 💡 Key Features

`beautyspot` は、単なるキャッシュライブラリではありません。
「実行コンテキスト（Spot）」という概念を通じて、データの永続化、セキュリティ、流量制御、そしてインフラの抽象化を一手に引き受ける「黒子（Kuroko）」です。

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

# --- 1. Custom Components Implementation (省略: 詳細は公式ドキュメント参照) ---
# RedisTaskDB, GCSStorage クラスの実装...

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
    decoder=lambda b: AnalysisResult(**{k:v for k,v in json.loads(b).items() if k in ["s","t"]})
)

# --- 4. The "Marked" Logic ---

@spot.mark(
    save_blob=True,                     # 1. 結果はGCSへ (Blob)
    input_key_fn=KeyGen.from_path_stat, # 2. ファイルのタイムスタンプを見てキャッシュ判定
    version="v2.0.1",                   # 3. ロジック変更時はここを変えてキャッシュ無効化
    content_type="application/json"     # 4. ダッシュボード表示用ヒント
)
@spot.limiter(cost=1)                   # 5. レート制限を適用
def analyze_log_file(file_path: str) -> AnalysisResult:
    """
    重い処理の実体。
    """
    print(f"Processing {file_path}...")
    time.sleep(0.5) 
    return AnalysisResult(score=0.95, summary=f"Processed {os.path.basename(file_path)}")

# --- 5. Execution ---

if __name__ == "__main__":
    files = ["/data/log1.txt", "/data/log2.txt"]
    
    # バッチ処理として実行
    for f in files:
        result = analyze_log_file(f)
        print(f"Result: {result.summary}")

```

## 📊 Dashboard (Result Viewer)

**"Minimal viewer, not a full tracer."**

ダッシュボードは、あくまで**「実行状況（戻り値）の確認」**と**「キャッシュDBが破綻していないかの確認」**に特化しています。

```bash
# プロジェクトのDBファイルを指定して起動
$ beautyspot ui ./my_experiment.db

```

---

## 🤝 License

MIT License

