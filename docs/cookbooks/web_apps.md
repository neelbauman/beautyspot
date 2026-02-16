# 🌐 Web Applications (FastAPI / Gunicorn)

Web アプリケーションにおいて `beautyspot` を導入する際の、ライフサイクル管理とマルチプロセス環境での最適化ガイドです。

## 🚀 1. FastAPI との統合 (Lifespan 構成)

FastAPI の `lifespan` を使用して、アプリケーションの起動時に `Spot` インスタンスを初期化し、終了時に実行中のバックグラウンドタスクを安全に完了させます。

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import beautyspot as bs

# プロセス全体で共有する Spot インスタンス
spot = bs.Spot(
    name="my_web_api",
    tpm=60,                # レート制限
    default_wait=False,    # 保存を非同期化してレスポンス速度を優先
    io_workers=8
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    yield
    # 終了時: 実行中の保存タスク（Background IO）が完了するのを待つ
    # これにより、シャットダウン時のキャッシュ消失リスクを低減します
    spot.shutdown(wait=True)

app = FastAPI(lifespan=lifespan)

@spot.mark(save_blob=True)
async def get_prediction(text: str):
    # 重い処理...
    return {"result": "data"}

@app.get("/predict")
async def predict(text: str):
    return await get_prediction(text)

```

## 🦄 2. Gunicorn (Multi-process) 運用での設計

Gunicorn 等でマルチワーカー構成をとる場合、各ワーカープロセスが独立した `Spot` インスタンスを持ちます。この環境では以下の 2 点に留意してください。

### レート制限（TPM）の調整

現在の `beautyspot` のレートリミッターはメモリ内で管理されるため、制限は**プロセス単位**で適用されます。

* **設計指針:** 外部 API の総制限が毎分 100 回で、ワーカー数が 4 の場合、各ワーカーの `tpm` には `25` 前後を設定することを推奨します。

### SQLite の書き込み競合

デフォルトの `TaskDB` は SQLite を使用します。

* **設計指針:** 大規模な同時書き込みが発生すると `database is locked` が発生する可能性があります。書き込み頻度が高い場合は、`save_blob=True` を活用して重いデータを外部ストレージ（S3 等）に逃がし、メタデータの書き込み時間を最小化してください。

## ⚡ 3. 非ブロッキング IO と永続性のトレードオフ

レスポンスタイムを最小化するために `default_wait=False` を設定する場合、速度と引き換えに以下のトレードオフが発生します。

| 特性 | `default_wait=True` (デフォルト) | `default_wait=False` |
| --- | --- | --- |
| **レスポンス速度** | 低（保存完了まで待機） | **高（即座に返却）** |
| **保存の確実性** | **極めて高い** | 中（保存完了前にプロセスが強制終了されると消失） |
| **ユースケース** | バッチ処理、整合性が必須のタスク | **Web API、ユーザー待機が発生する処理** |

> **Tip:** Web アプリケーションでは `default_wait=False` を推奨しますが、`spot.shutdown(wait=True)` を lifespan 内で呼び出すことで、通常のデプロイや再起動による消失リスクを大幅に軽減できます。

