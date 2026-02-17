# 28. Recursive Storage Cleanup and Zombie Project Collection

* Status: Accepted
* Date: 2026-02-17
* Context: v2.3.0

## Context and Problem Statement

これまでの `beautyspot clean` コマンドの実装には、以下の課題があった。

1.  **ディレクトリの残留:** `clean` コマンドは個別のファイル削除 (`os.remove`) のみを行い、空になったディレクトリを削除していなかった。
2.  **隠しファイルの阻害:** macOS の `.DS_Store` や Windows の `Thumbs.db` などのシステムファイルが存在する場合、ディレクトリが空とみなされず、削除できないケースがあった。
3.  **ゾンビプロジェクト:** ユーザーが手動で DB ファイル (`.db`) のみを削除した場合、対応する Blob ディレクトリ (`.beautyspot/blobs/{name}`) が管理外のゴミ（ゾンビプロジェクト）としてディスク上に残り続け、CLI から削除する手段がなかった。

## Decision

これらの課題を解決するため、ストレージのクリーンアップ戦略を以下のように変更・拡張する。

### 1. Two-Phase Cleanup Strategy (clean command)
`clean` コマンドの実行プロセスを2段階に分割する。

* **Phase 1 (File Deletion):** 従来通り、DB参照のない孤立ファイル（Orphan Blobs）を削除する。
* **Phase 2 (Directory Pruning):** `LocalStorage` に `prune_empty_dirs()` メソッドを追加し、Phase 1 完了後に実行する。これはストレージルートから再帰的にディレクトリを探索し、空のディレクトリを一括で削除する。

### 2. Robust Directory Pruning
`prune_empty_dirs()` メソッドにおいて、以下のロジックを採用する。

* ディレクトリ内にシステム生成ファイル（`.DS_Store`, `Thumbs.db`, `desktop.ini`）のみが存在する場合、それらを「実質的な空」とみなし、強制的に削除した上でディレクトリを削除する。
* これにより、OSの仕様に依存せず、確実にプロジェクトディレクトリをクリーンアップ可能にする。

### 3. Zombie Project Garbage Collection (gc command)
DBファイル自体が失われたプロジェクトを回収するための新コマンド `gc` を実装する。

* **Logic:** `.beautyspot/blobs/` 配下のディレクトリを走査し、対応する `.db` ファイルが存在しないものを「ゾンビプロジェクト」と判定する（ADR 0027 の Scope Policy に準拠）。
* **Action:** 検出されたディレクトリに対し、`shutil.rmtree` を用いて、内部のファイル整合性に関わらず強制的に一括削除を行う。

## Consequences

### Positive
* **完全なクリーンアップ:** ユーザーは `clean` コマンドを実行するだけで、不要なファイルだけでなく、不要になったディレクトリ構造（プロジェクトルート含む）もきれいに削除できる。
* **運用性の向上:** テスト失敗や手動操作で発生した「DBのないデータ残骸」を、`gc` コマンド一発で解消できるようになった。
* **安全性と保守性:** ファイル削除ロジック（`delete`）とディレクトリ掃除ロジック（`prune`）を分離したことで、コードの責務が明確になり、隠しファイル処理などの複雑性を `Storage` クラス内に隠蔽できた。

### Negative
* **IOオーバーヘッド:** `prune_empty_dirs` は `os.walk` を使用するため、ファイル数が膨大な場合に若干のオーバーヘッドが発生する。ただし、これは頻繁に実行される処理ではなくメンテナンス操作であるため、許容範囲とする。
