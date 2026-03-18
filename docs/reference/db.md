# TaskDB (Database)

`beautyspot` は、タスクのメタデータ、実行ステータス、およびシリアライズされた実行結果（小規模なデータの場合）を保存するためにデータベースを使用します。

::: beautyspot.db

## 概要

`beautyspot` のデータベースレイヤーは、抽象基底クラス `TaskDBBase` によって定義されています。これにより、デフォルトの SQLite 以外のバックエンド（PostgreSQL, Redis 等）をユーザーが独自に実装して注入することが可能です。

## 主なクラス

### TaskDBBase
すべてのデータベースバックエンドが継承すべき基本インターフェースです。タスクの保存・取得（`save`, `get`, `delete` 等）を定義します。

!!! info "実装時の注意点 (Thread Safety)"
    `Spot` クラスが `io_workers > 1` で初期化されている場合、`save`, `get`, `delete` などのメソッドは複数のスレッドから同時に呼び出される可能性があります。
    そのため、カスタム DB 実装はスレッドセーフである必要があります。スレッド間で単一の接続を共有するのではなく、メソッド呼び出しごとに接続を作成するか、接続プールを使用することを推奨します。

### TaskDBMaintenable (プロトコル)
データのライフサイクルを管理するための高度な保守用インターフェースです。`MaintenanceService` や CLI から呼び出されます。
実装は以下のメソッドを提供する必要があります。

* **`delete_expired()`**: `expires_at` を過ぎたレコードを削除します。
* **`prune(older_than_days)`**: 指定日数より古いレコードを削除します。
* **`get_outdated_tasks(cutoff_date)`**: 指定日時より古いタスクのリストを取得します。

### SQLiteTaskDB
SQLite を使用したデフォルトの実装です。`TaskDBBase` および `TaskDBMaintenable` を実装しています。

- **接続タイムアウト**: 並列実行時の `database is locked` エラーを回避するため、デフォルトで 30 秒のタイムアウトが設定されています。
- **WAL モード**: 書き込みと読み込みの並行性を高めるため、内部的に `PRAGMA journal_mode=WAL;` を有効化しています。
- **自動マイグレーション**: 古いバージョンのデータベースを開いた場合、不足しているカラム（`content_type`, `version`, `expires_at` 等）を自動的に検出し、`ALTER TABLE` を使用してスキーマを更新します。
- **タイムゾーン管理**: 内部的にすべてのタイムスタンプを UTC の ISO フォーマット（`_ensure_utc_isoformat`）に統一して保存・比較します。

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
| `func_name` | 実行された関数名（短い名前） |
| `func_identifier` | 実行された関数の完全修飾名（`module.qualname`） |
| `input_id` | 入力引数から生成された ID |
| `version` | タスクのバージョン |
| `result_type` | 結果の保存形式 (`DIRECT_BLOB` または `FILE`) |
| `content_type` | データの MIME タイプ (任意) |
| `result_value` | 外部ファイルへのパス (FILE の場合) |
| `result_data` | シリアライズされたバイナリデータ (DIRECT_BLOB の場合) |
| `updated_at` | 最終更新日時 |
| `expires_at` | 期限切れ日時（任意） |

!!! note "func_identifier について"
    `func_identifier` は `module.qualname` 形式の完全修飾名で、同名関数の衝突を避けるために使われます。
    既存データは `func_identifier` が NULL の場合があるため、表示やフィルタでは `func_name` にフォールバックされます。
