# TaskDB (Database)

`beautyspot` は、タスクのメタデータ、実行ステータス、およびシリアライズされた実行結果（小規模なデータの場合）を保存するためにデータベースを使用します。

::: beautyspot.db

## 概要

`beautyspot` のデータベースレイヤーは、抽象基底クラス `TaskDB` によって定義されています。これにより、デフォルトの SQLite 以外のバックエンド（PostgreSQL, Redis 等）をユーザーが独自に実装して注入することが可能です。

## 主なクラス

### TaskDB
すべてのデータベースバックエンドが継承すべき抽象インターフェースです。

!!! info "実装時の注意点 (Thread Safety)"
    `Spot` クラスが `io_workers > 1` で初期化されている場合、`save`, `get`, `delete` などのメソッドは複数のスレッドから同時に呼び出される可能性があります。
    そのため、カスタム DB 実装はスレッドセーフである必要があります。スレッド間で単一の接続を共有するのではなく、メソッド呼び出しごとに接続を作成するか、接続プールを使用することを推奨します。

### SQLiteTaskDB
SQLite を使用したデフォルトの実装です。

- **接続タイムアウト**: 並列実行時の `database is locked` エラーを回避するため、デフォルトで 30 秒のタイムアウトが設定されています。
- **WAL モード**: 書き込みと読み込みの並行性を高めるため、内部的に `PRAGMA journal_mode=WAL;` を有効化しています。

## 使用例

```python
from beautyspot.db import SQLiteTaskDB

# デフォルト設定での初期化
db = SQLiteTaskDB(".beautyspot/tasks.db")

# タイムアウトをカスタマイズして初期化
db = SQLiteTaskDB(".beautyspot/tasks.db", timeout=60.0)

```

## スキーマ定義

`init_schema()` メソッドによって、以下のカラムを持つ `tasks` テーブルが作成されます：

| カラム名 | 説明 |
| --- | --- |
| `cache_key` | タスクのユニークな識別子 (主キー) |
| `func_name` | 実行された関数名 |
| `input_id` | 入力引数から生成された ID |
| `version` | タスクのバージョン |
| `result_type` | 結果の保存形式 (`DIRECT_BLOB` または `FILE`) |
| `content_type` | データの MIME タイプ (任意) |
| `result_value` | 外部ファイルへのパス (FILE の場合) |
| `result_data` | シリアライズされたバイナリデータ (DIRECT_BLOB の場合) |
| `updated_at` | 最終更新日時 |

