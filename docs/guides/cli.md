# CLI & Dashboard Guide

`beautyspot` は、キャッシュされたデータの閲覧や、ディスク容量を管理するためのコマンドラインツールを提供しています。

## Dashboard (UI)

キャッシュされたタスクの実行履歴、結果、依存関係などをブラウザで視覚的に確認できます。

### Basic Usage

```bash
beautyspot ui <path_to_db>

```

* **`<path_to_db>`**: Spotを作成した際に指定したデータベースファイルのパス（デフォルトでは `.beautyspot/project_name.db` など）。

### Features

* **Task History:** 実行された関数の履歴を時系列で表示します。
* **Result Viewer:** 戻り値をその `content_type` に応じて（JSON, 画像, Markdown, Mermaid図など）適切にレンダリングします。
* **Filtering:** 関数名やResult Typeで履歴を絞り込むことができます。

---

## Maintenance Tools

長期間 `beautyspot` を使用していると、不要になったBlobファイル（画像や巨大なデータ）がディスクに残ることがあります。
以下のコマンドを使用して、ディスク容量を解放できます。

### `clean` (Garbage Collection)

データベース上に記録が存在しない「孤立したBlobファイル」を削除します。
開発中にDBファイルを削除したが、`blobs/` ディレクトリ内のファイルだけ残ってしまった場合などに有効です。

```bash
# Dry-run (削除対象を表示するだけ)
beautyspot clean --storage-path .beautyspot/blobs --db-path .beautyspot/my_spot.db --dry-run

# Execute (実際に削除)
beautyspot clean --storage-path .beautyspot/blobs --db-path .beautyspot/my_spot.db

```

### `prune` (Delete Old Tasks)

指定した期間より古いタスクデータを、データベースとBlobストレージの両方から削除します。

```bash
# 30日以上前のデータを削除 (Dry-run)
beautyspot prune --days 30 --db-path .beautyspot/my_spot.db --dry-run

# 実行 (確認プロンプトが表示されます)
beautyspot prune --days 30 --db-path .beautyspot/my_spot.db

```

!!! warning "注意"
`prune` はデータベースのレコードも削除するため、一度削除すると復元できません。
本番環境のデータに対して実行する場合は十分注意してください。

