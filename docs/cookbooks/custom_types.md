## 🧩 . Custom Types (Pandas, Pydantic, etc...)

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
