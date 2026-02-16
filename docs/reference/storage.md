# Storage

`beautyspot.storage` は、バイナリデータの永続化を抽象化するインターフェースと、その具体的な実装を提供します。

::: beautyspot.storage

## 概要

`beautyspot` は、キャッシュ結果をデータベース内に保存するか、外部ストレージに保存するかを自動的、あるいは明示的に切り替えることができます。`BlobStorageBase` を継承することで、独自のストレージバックエンド（例：Google Cloud Storage, Azure Blob Storage）を実装することも可能です。

## インターフェース: `BlobStorageBase`

すべてのストレージ実装が提供すべき基本メソッドです。

* **`save(key, data)`**: データを保存し、その場所を示す一意のロケーション（パスや URI）を返します。
* **`load(location)`**: 指定されたロケーションからバイナリデータを取得します。
* **`delete(location)`**: 指定されたロケーションのデータを削除します。
* **`list_keys()`**: ストレージ内のすべてのロケーションを列挙します（ガベージコレクション用）。

## 標準実装

### LocalStorage

ローカルのファイルシステムを使用する実装です。

* **自動生成**: コンストラクタで指定されたディレクトリが存在しない場合は自動的に作成します。
* **安全性**: パス・トラバーサル攻撃を防ぐため、キーにパス区切り文字が含まれていないかバリデーションを行います。
* **アトミックな書き込み**: 一時ファイルに書き込んだ後でリネーム（replace）を行うことで、書き込み中のクラッシュによるデータ破損を防ぎます。

### S3Storage

AWS S3 または互換ストレージを使用する実装です。

* **依存関係**: 使用には `boto3` が必要です。
* **URI 形式**: `s3://bucket-name/prefix` 形式の URI をサポートします。

## ファクトリ関数: `create_storage`

パスの形式（`s3://` で始まるかどうか）を判別し、適切なストレージインスタンスを動的に生成します。`MaintenanceService.from_path` などで内部的に利用されています。

## 使用例

### 明示的な初期化

```python
from beautyspot.storage import LocalStorage, S3Storage

# ローカルストレージ
local_store = LocalStorage("./.beautyspot/blobs")

# S3ストレージ
s3_store = S3Storage("s3://my-bucket/cache", s3_opts={"region_name": "ap-northeast-1"})

```

### Spot への注入

```python
from beautyspot import Spot
from beautyspot.storage import create_storage

# ファクトリ関数を使用してストレージを準備
storage = create_storage("./.beautyspot/blobs")

spot = Spot(
    name="my_app",
    db=db,
    serializer=serializer,
    storage=storage,
    default_save_blob=True  # デフォルトですべてのタスクを外部ストレージに保存
)

```

## 例外

* **`CacheCorruptedError`**: コードの変更などにより、取得した Blob データのデシリアライズに失敗した場合に送出されます。

