# 27. CLI Scope Definition and Explicit Storage Linkage

* Status: Accepted
* Date: 2026-02-17
* Context: v2.3.0 (Planned)

## Context and Problem Statement

`beautyspot` の `clean` コマンドや、将来実装予定の `gc` (Zombie Project Cleanup) 機能は、DBファイルとBlobストレージディレクトリの対応関係が「自明」であることを前提としています。
標準構成（`.beautyspot/{name}.db` と `.beautyspot/blobs/{name}/`）ではこの前提は成立しますが、ユーザーが `TaskDB` や `BlobStorage` をカスタム実装したり、パスを標準外の場所に設定した場合、CLIツールは安全に依存関係を特定できません。
この状態で推測に基づく削除を行うと、誤って無関係なデータを削除するリスクがあります。

## Decision

### 1. CLI Scope Limitation (Policy)
CLIが提供する「ストレージの自動クリーニング・削除機能」のサポート範囲を、**標準ディレクトリ構成（`.beautyspot/` 配下）を使用しているプロジェクト** に限定します。
カスタム構成（外部DB、S3バケットの共有、カスタムパス等）を利用している場合、CLIによる自動削除は保証されず、ユーザー自身の責任でリソース管理を行う必要がある旨をドキュメントに明記します。

### 2. Explicit Storage Linkage (Roadmap)
「対応関係が自明でない」問題を根本解決するため、将来のバージョンで **TaskDB内に使用しているStorageの情報をメタデータとして記録する** 仕組みを導入します。
具体的には、DB初期化時に `storage_uri` (例: `file://relative/path`, `s3://bucket/prefix`) を保存し、メンテナンスコマンド実行時に「操作対象のDBが参照しているストレージと、今消そうとしているディレクトリが一致するか」を検証可能にします。

## Consequences

### Positive
* **安全性:** 推測による誤削除（False Positive）を確実に防ぐことができる。
* **明確な責任分界点:** ツールが面倒を見る範囲と、ユーザーが管理すべき範囲が明確になる。
* **将来の拡張性:** メタデータ記録が実装されれば、カスタム構成でも安全なGCが可能になる。

### Negative
* **ユーザーの負担:** カスタム構成で利用する上級ユーザーは、`beautyspot clean` の恩恵を完全には受けられない（手動管理が必要になる場合がある）。

