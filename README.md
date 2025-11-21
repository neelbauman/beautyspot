# 🌑 beautyspot

**Make your functions beautiful with beauty spots.**

[](https://www.google.com/search?q=https://pypi.org/project/beautyspot/)
[](https://opensource.org/licenses/MIT)
[](https://www.google.com/search?q=https://pypi.org/project/beautyspot/)

## 🎭 Concept

**"You focus on the logic. We handle the rest."**

生成AIのバッチ処理、スクレイピング、重いデータ解析……。

  * APIのレート制限計算
  * 途中停止した時のリカバリ処理
  * 巨大なJSONや画像の保存先管理
  * 重複リクエストの排除

`beautyspot` は、あなたのコードに「黒子/ほくろ（デコレータ）」を一つ付けるだけで、
これらの面倒なインフラ制御をすべて引き受ける「黒子/くろこ」です。

-----

## ⚡ Installation

```bash
pip install beautyspot
```

S3 などのクラウドストレージを利用する場合:

```bash
pip install "beautyspot[s3]"
```

-----

## 🚀 Quick Start

最もシンプルな例です。関数に `@project.task` を付けるだけで、その関数は「永続化」され、二度と同じ計算を行わなくなります。

```python
import time
import beautyspot as bs

# プロジェクト定義（DBや保存先を自動管理）
project = bs.Project("my_experiment")

@project.task
def heavy_process(text):
    # 実行に時間がかかる処理や、課金されるAPIコール
    time.sleep(2)
    return f"Processed: {text}"

# バッチ処理
inputs = ["A", "B", "C", "A"]  # "A" は2回ある

for i in inputs:
    # 1. 初回の "A", "B", "C" は実行される
    # 2. 最後の "A" は、DBからキャッシュが即座に返る（実行時間0秒）
    # 3. もし途中でエラーで止まっても、再実行時は完了済みをスキップする
    print(heavy_process(i))
```

-----

## 💡 Key Features

### 1\. 思考停止できる「レート制限 (Rate Limiting)」

APIの制限（例：1分間に1万トークン）を守るために、複雑なスリープ処理を書く必要はありません。
`tpm` (Tokens Per Minute) を指定して、何も考えずに並列化してください。

```python
# 1分間に 50,000 トークンまでに制限
project = bs.Project("openai_batch", tpm=50000)

def calc_cost(text):
    return len(text)

@project.task
@project.limiter(cost=calc_cost)  # リトライ時も含めて自動制御
def call_api(text):
    return api.generate(text)

# スレッドプールで適当に並列化しても、beautyspotが交通整理します
with ThreadPoolExecutor(max_workers=50) as ex:
    ex.map(call_api, huge_list)
```

### 2\. 巨大データも安心「ハイブリッド・ストレージ」

画像や巨大なJSONを扱う場合、`save_blob=True` を指定してください。
メタデータはSQLiteで高速に管理し、実データはファイルシステム（またはS3）へ自動的に退避させます。DBがパンクすることはありません。

```python
@project.task(save_blob=True)
def ocr_task(image_path):
    # 戻り値が10MBのJSONでも問題なし
    return {"text": "...", "boxes": [...]}
```

### 3\. Web API (FastAPI) のワーカーとして

バッチ処理で作ったロジックを、そのまま Web API のバックグラウンド処理に持ち込めます。
**「同じ入力なら再計算しない」** という特性により、意図せずとも強力なキャッシュ層として機能します。

```python
# api.py
from fastapi import FastAPI, BackgroundTasks
from my_batch_logic import heavy_process # beautyspotでデコレート済み

app = FastAPI()

@app.post("/generate")
async def generate(text: str, background_tasks: BackgroundTasks):
    # 1. 既に誰かが同じ入力をしていれば、DBから即座に結果取得可能
    # 2. 未実行なら、バックグラウンドで実行（APIをブロックしない）
    background_tasks.add_task(heavy_process, text)
    return {"status": "accepted"}
```

### 4. Robust Caching & Versioning

開発中にコード（クラス定義など）を変更しても、beautyspotは古いキャッシュの読み込みエラーを検知して**自動的に再計算**します。アプリはクラッシュしません。

もし、明示的にキャッシュを切り替えたい場合（ロジックを大きく変えた時など）は、`version` 引数を使ってください。

```python
@project.task(version="v2")  # v1のキャッシュは無視され、新しく計算されます。両者はキャッシュとして独立しているので、v1に戻せばv1が参照されます。
def my_task(data):
    # ...

-----

## 📊 Dashboard (Built-in UI)

処理結果やエラーログを確認するために、SQLを書く必要はありません。
付属のコマンドで、専用のダッシュボードが起動します。

```bash
# プロジェクトのDBファイルを指定して起動
$ beautyspot ui ./my_experiment.db
```

**できること:**

  * **データの復元:** 保存先がローカルでもS3でも、画面上で画像やJSONを自動復元して表示します。
  * **進捗確認:** 成功/失敗のステータス推移をグラフ化。
  * **エラー分析:** 失敗したタスクの入力データを検索・特定。

-----

## 🧠 Smart Caching

`beautyspot` は、関数の引数を自動的に解析してキャッシュキーを生成します。
v0.2.0 からは、以下のオブジェクトも設定なしで安定してキャッシュできるようになりました。

* **Pydantic Models & Dataclasses:** オブジェクトの中身（値）に基づいてハッシュ化します。
* **Sets:** 順序を自動ソートしてハッシュ化します（`{1, 2}` と `{2, 1}` は同じとみなされます）。

### Custom Cache Keys (`input_key_fn`)

巨大なDataFrameや、シリアライズできない特殊なオブジェクトを引数に取る場合、デフォルトのハッシュ計算がボトルネックになることがあります。
その場合、`input_key_fn` を使って「何をもって同一とみなすか」を定義してください。

```python
def get_article_id(article):
    # 記事の全文ではなく、IDだけをキャッシュキーにする（高速化）
    return article.id

@project.task(input_key_fn=get_article_id)
def analyze_sentiment(article):
    # ... 重い処理 ...
    return score

-----

## ⚙️ Configuration

### Environment Switching (Local \<-\> S3)

コードを書き換えることなく、開発環境と本番環境を行き来できます。

```python
import os
# 環境変数で切り替え
# Dev: "./local_blobs"
# Prod: "s3://my-bucket/v1/results"
STORAGE = os.getenv("BS_STORAGE", "./local_blobs")

project = bs.Project("my_app", storage_path=STORAGE)
```

### Async Support

`beautyspot` は、デコレートされた関数が `async def` かどうかを自動判定します。
`httpx` や `AsyncOpenAI` を使う場合も、特別な対応は不要です。

```python
@project.task
async def async_fetch(url):
    async with httpx.AsyncClient() as client:
        return await client.get(url)
```

-----

## 🛡 Architecture

`beautyspot` は、あなたの環境を汚さないよう、以下の設計思想で作られています。

  * **Non-Intrusive:** 既存のクラス設計やロジックを変更せず、デコレータのみで機能追加します。
  * **Concurrency Safe:** SQLiteのWALモードとスレッドセーフなトークンバケットにより、マルチスレッド/非同期環境でも安全に動作します。
  * **Portable:** 依存ライブラリは最小限。S3機能はオプショナルです。

-----

## 🤝 License

MIT License
