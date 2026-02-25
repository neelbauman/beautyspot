---
title: Recursive Storage Cleanup and Zombie Project Collection
status: Accepted
date: 2026-02-17
context: Enhancing Maintenance Capability
---

# Recursive Storage Cleanup and Zombie Project Collection

## Context and Problem Statement / コンテキスト

これまでの `beautyspot clean` コマンドの実装には、以下の課題がありました。

1.  **ディレクトリの残留:** `clean` コマンドは個別のファイル削除のみを行い、空になったディレクトリを削除していませんでした。
2.  **隠しファイルの阻害:** macOS の `.DS_Store` などのシステムファイルが存在する場合、ディレクトリが空とみなされず、削除できないケースがありました。
3.  **ゾンビプロジェクト:** ユーザーが手動で DB ファイル (`.db`) のみを削除した場合、対応する Blob ディレクトリが管理外のゴミ（ゾンビプロジェクト）として残り続け、削除する手段がありませんでした。

## Decision Drivers / 要求

* **Complete Cleanup**: 不要なファイルだけでなく、空のディレクトリ構造も含めて完全に削除し、ファイルシステムをクリーンに保つこと。
* **Robustness**: システム生成ファイル（`.DS_Store` 等）に惑わされず、意図した通りにクリーンアップを実行できること。
* **Garbage Collection**: メタデータ（DB）を失った実データ（Blob）を検出し、安全に一括削除できること。

## Considered Options / 検討

* **Option 1**: ファイル削除のみを継続し、ディレクトリの整理はユーザーに任せる。
* **Option 2**: 2段階のクリーンアップ戦略（ファイル削除 ＋ 再帰的な空ディレクトリ整理）と、ゾンビプロジェクト回収用の `gc` コマンドを導入する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

ストレージのクリーンアップ戦略を以下のように刷新します。

### 1. Two-Phase Cleanup Strategy (clean command)
`clean` コマンドを2段階に分割します。
* **Phase 1 (File Deletion):** DB参照のない孤立ファイルを削除。
* **Phase 2 (Directory Pruning):** `LocalStorage` に `prune_empty_dirs()` メソッドを追加し、再帰的に空ディレクトリを一括削除。

### 2. Robust Directory Pruning
システム生成ファイル（`.DS_Store`, `Thumbs.db`, `desktop.ini`）のみが存在する場合、それらを「実質的な空」とみなし、強制的に削除した上で親ディレクトリを削除します。

### 3. Zombie Project Garbage Collection (gc command)
DBファイルが失われたプロジェクトを回収するための `gc` コマンドを実装します。対応する `.db` ファイルが存在しないディレクトリを「ゾンビプロジェクト」と判定し、`shutil.rmtree` で強制的に一括削除します。

## Consequences / 決定

* **Positive**:
    * **完全なクリーンアップ:** ユーザーはコマンド一つで不要なディレクトリ構造まで一掃できる。
    * **運用性の向上:** 手動操作で発生した残骸を簡単に解消できる。
    * **責務の分離:** ファイル削除とディレクトリ整理を分離し、OS 固有の処理を `Storage` クラス内に隠蔽できた。
* **Negative**:
    * **IOオーバーヘッド:** `os.walk` による再帰探索を行うため、ファイル数が膨大な場合にオーバーヘッドが発生する。
