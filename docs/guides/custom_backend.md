# 🛠️ Custom Database Backend Guide

`beautyspot` はデフォルトで SQLite を使用しますが、大規模な分散処理や、クラウドネイティブな環境（Kubernetesなど）で動作させる場合、PostgreSQL や MySQL、あるいは DynamoDB といった外部データベースを利用したくなるでしょう。

v1.0.0 から導入された **Dependency Injection (DI)** 機構を利用することで、ライブラリのコードを変更することなく、バックエンドを自由に差し替えることができます。

## 1. The Interface: `TaskDB`

カスタムバックエンドを作成するには、`beautyspot.db.TaskDB` 抽象基底クラス（Abstract Base Class）を継承し、以下の4つのメソッドを実装する必要があります。

::: beautyspot.db.TaskDB
    options:
        show_root_heading: false
        show_source: true

### 実装の要件 (Contract)

* **Thread Safety**: `Spot` はマルチスレッドで動作する可能性があります。データベースアダプタはスレッドセーフである必要があります。
* **Schema Initialization**: `init_schema()` は `Spot` 初期化時に毎回呼ばれます。「テーブルがなければ作成する（IF NOT EXISTS）」ように実装してください。
* **Idempotency**: `save()` は同じキーで何度も呼ばれる可能性があります。`INSERT OR REPLACE` (Upsert) の挙動を実装してください。

## 2. Implementation Example

ここでは例として、開発やテストに便利な「インメモリデータベース（辞書ベース）」の実装を示します。
本番環境で PostgreSQL 等を使用する場合も、基本的な構造は同じです。

```python
from typing import Any, Dict, Optional
import pandas as pd
from beautyspot.db import TaskDB

class MemoryTaskDB(TaskDB):
    """
    オンメモリで動作する揮発性のバックエンド。
    テストや、永続化が不要な一時的なスクリプトに最適です。
    """
    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}

    def init_schema(self):
        # メモリ上の辞書なのでスキーマ作成は不要
        pass

    def get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        return self._storage.get(cache_key)

    def save(
        self, 
        cache_key: str, 
        func_name: str, 
        input_id: str, 
        version: Optional[str], 
        result_type: str, 
        content_type: Optional[str], 
        result_value: str
    ):
        # 辞書に保存（Upsert）
        self._storage[cache_key] = {
            "func_name": func_name,
            "input_id": input_id,
            "version": version,
            "result_type": result_type,
            "content_type": content_type,
            "result_value": result_value,
            "updated_at": pd.Timestamp.now() # 履歴用
        }

    def get_history(self, limit: int = 1000) -> pd.DataFrame:
        if not self._storage:
            return pd.DataFrame()
        
        # 辞書からDataFrameを作成
        df = pd.DataFrame(list(self._storage.values()))
        df["cache_key"] = list(self._storage.keys())
        return df.sort_values("updated_at", ascending=False).head(limit)

```

## 3. Injection (How to use)

作成したカスタムクラスのインスタンスを、`Spot` の `db` 引数に渡すだけです。

```python
import beautyspot as bs

# 1. カスタムDBをインスタンス化
my_memory_db = MemoryTaskDB()

# 2. Spotに注入 (パス文字列ではなく、インスタンスを渡す)
spot = bs.Spot("memory_app", db=my_memory_db)

@spot.mark
def calc(x):
    return x * 2

# この結果は SQLite ファイルではなく、メモリ上に保存されます
print(calc(10)) 

```

## 4. Advanced: Using PostgreSQL / MySQL

RDBMS を使用する場合は、`sqlalchemy` や `psycopg2` を使用して `TaskDB` を実装します。
`src/beautyspot/db.py` 内の `SQLiteTaskDB` の実装が参考になります。

特に以下の点に注意してください：

* **接続管理**: `save` や `get` のたびに接続を開くか、コネクションプールを使用するかを適切に設計してください。
* **JSONシリアライズ**: `beautyspot` は結果を JSON 文字列として渡します。DB側には `TEXT` 型または `JSONB` 型のカラムを用意してください。
