# 🍳 Cookbook (Recipes)

`beautyspot` を実際のプロジェクトで活用するための具体的なコードレシピ集です。
これらのスニペットをコピー＆ペーストして、プロジェクトの要件に合わせて調整してください。

---

## 🧩 1. Custom Types (Pandas, Pydantic, etc...)

Pandas DataFrame のような複雑なオブジェクトをキャッシュしたい場合、`@spot.register` デコレータを使ってシリアライズ（保存）とデシリアライズ（復元）の方法を登録します。

**Point:**
* **Parquet** 形式を使うことで、高速かつ圧縮効率の良い保存が可能です。
* クラス定義そのものをデコレートするパターンです。

```python
import pandas as pd
import io
import beautyspot as bs

spot = bs.Spot("data_science_workspace")

# --- 方法 A: 既存のクラスを登録する場合 (register_type) ---
def encode_df(df: pd.DataFrame) -> bytes:
    with io.BytesIO() as buffer:
        df.to_parquet(buffer)
        return buffer.getvalue()

def decode_df(data: bytes) -> pd.DataFrame:
    with io.BytesIO(data) as buffer:
        return pd.read_parquet(buffer)

spot.register_type(pd.DataFrame, code=20, encoder=encode_df, decoder=decode_df)

# --- 方法 B: 自作クラスを登録する場合 (@spot.register) ---
@spot.register(
    code=21,
    encoder=lambda obj: obj.to_json(),
    decoder=lambda data: MyResult.from_json(data),
)
class MyResult:
    def __init__(self, summary: dict):
        self.summary = summary
    # ... methods ...

# Usage
@spot.mark(save_blob=True)
def heavy_processing(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)

```

Beautyspot は中間表現（辞書など）のシリアライズを自動的に処理します。エンコーダからは、単に、復元可能なように作られたmsgpackでシリアライズ可能な型を返すだけで構いません。

```python
from pydantic import BaseModel
from beautyspot import Spot

spot = Spot("pydantic_app")

class User(BaseModel):
    name: str
    age: int

@spot.register(
    code=10,
    # Encoder: モデル -> 辞書
    # シリアライザがこの辞書を自動的にバイト列へパックします。
    encoder=lambda obj: obj.model_dump_json(),
    # Decoder: 辞書 -> モデル
    # シリアライザがバイト列を辞書にアンパックしてからこれを呼び出します。
    decoder=lambda data: User.model_validate_json(data),
)
class User(BaseModel):
    pass
```

---

## ⚡ 2. Imperative Caching: `with cached_run`

ライブラリの関数や、ソースコードを変更できない関数を「その場限り」でキャッシュしたい場合に最適です。

**Scenario:**
シミュレーションライブラリ `simpy` の関数を実行したいが、パラメータが同じなら計算をスキップしたい。

```python
import beautyspot as bs
from external_lib import run_simulation  # 変更できない外部関数

spot = bs.Spot("simulation_env")

# コンテキスト内でのみ、run_simulation はキャッシュ機能を持つラッパーになります
# version="v1" を指定することで、将来ロジックが変わった時にキャッシュを無効化できます
with spot.cached_run(run_simulation, version="exp-v1") as cached_sim:
    
    # 1回目: 実行される (3秒)
    result1 = cached_sim(param_a=10, param_b=20)
    
    # 2回目: キャッシュから即座に返る (0秒)
    result2 = cached_sim(param_a=10, param_b=20)

print("Done!")

```

---

## 🗝️ 3. Advanced Key Generation

引数のすべてが「計算結果」に影響するわけではありません。`KeyGen` を使って、「どの引数をキャッシュキーに含めるか」を精密に制御します。

**Case:**

* `verbose` フラグは結果に関係ないので無視したい (`IGNORE`)
* `config_path` はファイルの中身が変わったら再計算したい (`FILE_CONTENT`)

```python
from beautyspot.cachekey import KeyGen

# ポリシーの定義
key_policy = KeyGen.map(
    # 引数名 'verbose' と 'logger' はハッシュ計算から除外
    verbose=KeyGen.IGNORE,
    logger=KeyGen.IGNORE,
    
    # 引数名 'config_path' はファイルの中身を読んでハッシュ化
    config_path=KeyGen.FILE_CONTENT
)

@spot.mark(input_key_fn=key_policy)
def train_model(data, config_path, verbose=False, logger=None):
    if verbose:
        print("Training started...")
    # ...
    return model

```

---

## ☁️ 4. Cloud Storage via Rclone (Google Drive as S3)

**"無限のストレージを、無料で。"**

[Rclone](https://rclone.org/) を使って Google Drive などを S3 互換 API として公開し、それを `beautyspot` の保存先として利用するテクニックです。

### Step 1: Rclone の準備

以下のコマンドで、最新の安定版（Stable）をインストールします。

```bash
curl https://rclone.org/install.sh | sudo bash
```

rcloneで、Google Drive をリモート接続先として設定します。

```bash
rclone config

# 以後、指示に従ってGoogle Driveを選択。gdriveという名前で作成する。
```

ターミナルで Rclone を S3 ゲートウェイモードで起動します。

```bash
# Google Drive のリモート名が "gdrive" の場合
rclone serve s3 gdrive: \
    --addr 127.0.0.1:8080 \
    --auth-key my_access_key,my_secret_key \
    --vfs-cache-mode full \
    --vfs-cache-max-age 24h
```

### Step 2: Spot の設定

`s3_opts` で `endpoint_url` をローカルに向けます。

Google Drive へのアクセス制限を考えて、late limit をかけても良いでしょう。

```python
import beautyspot as bs

spot = bs.Spot(
    name="gdrive_project",
    tpm=60,
    # s3://{bucket_name} の形式で指定
    # Rcloneの場合、Google Drive直下のフォルダ名がバケット名として認識されます
    # Google Drive 直下に observability-storage という名前のディレクトリを作成した場合の Example
    storage_path="s3://observability-storage",
    
    # S3互換接続のためのオプション (Boto3 clientへの引数となります)
    s3_opts={
        "endpoint_url": "http://localhost:8080",
        "aws_access_key_id": "my_access_key",       # Rcloneの --auth-key で指定したID #pragma: allowlist secret
        "aws_secret_access_key": "my_secret_key",   # Rcloneの --auth-key で指定したSecret #pragma: allowlist secret
        "region_name": "us-east-1"        # ダミーでOKですが指定推奨
    }
)

@spot.mark(save_blob=True, version="v0.1.0")
@spot.limiter(cost=1)
def generate_large_dataset():
    # 戻り値は自動的に Google Drive 上の 'beautyspot-data' フォルダ内に保存されます
    return b"..." * 1024 * 1024


if __name__ == "__main__":
    generate_large_dataset()

```

---

## 🕸️ 5. Web Scraping & Rate Limiting

スクレイピングにおける「マナー（アクセス頻度制限）」と「効率（キャッシュ）」を同時に実現します。

```python
import requests
import beautyspot as bs

# TPM (Tokens Per Minute) = 20 -> 3秒に1回のリクエスト制限
spot = bs.Spot("crawler", tpm=20)

@spot.mark
@spot.limiter(cost=1)
def fetch_page(url: str):
    print(f"Accessing {url}...")
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

# 連続で呼び出しても、自動的に待機時間が挿入されます
urls = [f"[https://example.com/page/](https://example.com/page/){i}" for i in range(10)]
for u in urls:
    html = fetch_page(u)

```

## 🧪 6. Testing

テスト実行時は、本番DBを汚さないように `tmp_path` やメモリ内DBを使用します。

```python
import pytest
import beautyspot as bs

@pytest.fixture
def spot(tmp_path):
    # テストごとに独立したDBとBlobストレージを作成
    return bs.Spot(
        name="test",
        db=str(tmp_path / "test.db"),
        storage_path=str(tmp_path / "blobs")
    )

def test_caching(spot):
    count = 0
    
    @spot.mark
    def func(x):
        nonlocal count
        count += 1
        return x * 2

    assert func(10) == 20
    assert count == 1
    
    # 2回目はキャッシュヒット
    assert func(10) == 20
    assert count == 1 

```
