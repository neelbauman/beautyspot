# 🌑 beautyspot

[https://pypi.org/project/beautyspot/](https://pypi.org/project/beautyspot/)
[https://opensource.org/licenses/MIT](https://opensource.org/licenses/MIT)

## Concept

**"You focus on the logic. We handle the rest."**

生成AIのバッチ処理やスクレイピングを行う際、本質的なロジック以外に以下のようなコードを書いていませんか？

  * API制限を守るための `time.sleep()` やトークン計算
  * 途中停止した際のリカバリ処理（ `try-except` と `continue` ）
  * 結果を保存・ロードするためのファイルI/O
  * 重複リクエストを防ぐためのID管理

`beautyspot` は、あなたのコードに「黒子/ほくろ（デコレータ）」を一つ付けるだけで、
これらの面倒なインフラ制御をすべて引き受ける「黒子/くろこ」です。

デコレータ1行でこれらをすべて引き受け、あなたのコードを「純粋なロジック」の状態に保ちます。

-----

## ⚡ Installation

最軽量版:

```bash
pip install beautyspot
```

S3 などのクラウドストレージを利用する場合:

```bash
pip install "beautyspot[s3]"
```

Dashboard機能を利用する場合:

```bash
pip install "beautyspot[dashboard]"
```

全部入り:

```bash
pip install "beautyspot[all]"
```

-----

## 🚀 Quick Start

関数に `@project.task` を付けるだけで、その関数は「永続化」され、二度と同じ計算を行わなくなります。

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

### 1\. Handle Any Data Size

**"Keep it clean, to be confortable."**

関数の戻り値が巨大になる場合（画像、音声、大規模なHTMLなど）、DBを圧迫しないよう `save_blob=True` を指定してください。`beautyspot` が自動的にデータを外部ストレージ（ファイルシステムやS3）へ逃がし、DBには軽量な参照のみを残します。

```python
# Small Data -> DBに直入れ (Default)
# 数値、短いテキスト、メタデータなど
@project.task
def calc_score(text):
    return 0.8

# Large Data -> Blobに退避 (Explicit Choice)
# 画像バイナリや巨大なJSONなど
@project.task(save_blob=True)
def download_image(url):
    return requests.get(url).content
```

### 2\. Portability with Control

**"Write once, run anywhere with control."**

レート制限やキャッシュのロジックは、呼び出し側のフレームワークではなく、**関数そのもの（デコレータ）** に内包されます。
そのため、一度 `beautyspot` でラップした関数は、コードを一切書き換えることなく、あらゆる実行環境で「制御された状態」で再利用できます。

**The Logic (共通ロジック):**

```python
# logic.py
@project.task
def generate_text(prompt):
    # 冪等性が担保された関数
    return api.call(prompt)
```

**Context A: CLI Batch Script**

```python
# 単純なループで呼ぶだけ。
# 中断しても、次回は「未完了のタスク」だけが実行されます。
for prompt in large_list:
    print(generate_text(prompt))
```

**Context B: FastAPI Worker**

```python
# Web APIのバックグラウンドタスクとして呼ぶ。
# 既に誰かが同じ入力をしていれば、APIを叩かずに即座に完了します。
@app.post("/generate")
async def api_endpoint(prompt: str, tasks: BackgroundTasks):
    tasks.add_task(generate_text, prompt)
    return {"status": "accepted"}
```

### 3\. Declarative Rate Limiting

**"Token Base, self managed rate control."**

APIの制限（例：1分間に1万トークン）を守るために、複雑なスリープ処理を書く必要はありません。
並行実行モデル（Thread, AsyncIO）に関わらず、`tpm` (Tokens Per Minute) を宣言するだけで、`beautyspot` がグローバルな交通整理を行います。

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

## 📊 Dashboard (Result Viewer)

**"Minimal viewer, not a full tracer."**

`beautyspot` は、すべての入出力を記録するトレーシングツール（MLflow, Langfuse等）とは異なります。
実行制御という役割を軽量に実現することを重視し、**入力データ（引数）は保存せず、ハッシュ値のみを管理します。**

そのため、入出力を対比して生成AIのプロンプトエンジニアリングを頑張るみたいな
使い方には向いていません。

ダッシュボードは、あくまで\*\*「実行状況（戻り値）の確認」**と**「キャッシュDBが破綻していないかの確認」\*\*に特化しています。

一応、Blobとして退避された巨大な戻り値も、ここから自動的に復元してプレビュー可能です。


```bash
# プロジェクトのDBファイルを指定して起動
$ beautyspot ui ./my_experiment.db
```

-----

## ⚙️ Configuration

### Storage Switching (Local \<-\> S3)

S3互換のストレージを、blobの保存先として指定することができます。

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

