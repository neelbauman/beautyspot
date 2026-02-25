---
title: Tolerant Deletion Policy for Task Cleanup
status: Accepted
date: 2026-02-14
context: Reliability of Cleanup Operations
---

# Tolerant Deletion Policy for Task Cleanup

## Context and Problem Statement / コンテキスト

`spot.delete(key)` 機能は、特定のタスクに関連する「キャッシュレコード（DB）」と「実データ（Blob/File）」の両方を削除することを目的としています。

ローカルファイルシステムやS3などの外部ストレージにおいて、Blobの削除操作は様々な理由（ネットワーク障害、一時的な権限エラー、ファイルが既に手動で削除されている等）で失敗する可能性があります。

このとき、厳密な整合性を求めて「Blob削除に失敗したらDBレコードの削除もロールバック（中断）する」という実装にすると、以下の問題が発生します：

1.  **ゾンビレコード**: 物理ファイルが見つからないだけなのに、DBからレコードを消せず、ユーザーは永遠にそのタスクを「無効化」できない。
2.  **再計算の阻害**: 破損したキャッシュエントリが残り続けることで、新しい計算結果での上書きや、クリーンな状態からの再実行が妨げられる。

## Decision Drivers / 要求

* **Guaranteed Invalidation**: ストレージの状態に関わらず、ユーザーが「削除」を指示したタスクを確実に管理対象から外すこと。
* **Workflow Continuity**: 物理ファイルの欠落などの非本質的なエラーで、ユーザーのワークフローを中断させないこと。
* **Consistency Management**: DB とストレージの乖離を最小限に抑えつつ、システムの健全性を維持すること。

## Considered Options / 検討

* **Option 1**: 厳密な削除。Blob の削除に失敗した場合は例外を送出し、DB のレコード削除も行わない。
* **Option 2**: 寛容な削除（Tolerant Deletion）。DB レコードの削除を優先し、Blob 削除時のエラーはログ出力に留めて処理を継続する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

削除操作において **「メタデータの削除を優先する」** ポリシーを採用します。

1.  まず、Blob（実データ）の削除を試みる。
2.  Blobの削除中に例外が発生した場合、**処理を中断せず**、`WARNING` レベルのログを出力してエラーを捕捉する。
3.  Blob削除の成否に関わらず、DB上のタスクレコードの削除を必ず実行する。

## Consequences / 決定

* **Positive**:
    * ユーザーはストレージの状態に関わらず、`beautyspot` の管理下からタスクを確実に削除できる。
    * 「ファイルが見つからない」といった些細なエラーでワークフローが止まることを防げる。
* **Negative**:
    * **孤立ファイル (Orphaned Blobs)**: DBレコードは削除されたが、ストレージ上にファイルだけが残るケースが発生しうる。
    * 対策として、別途ガベージコレクション（GC）ツールやストレージ側のライフサイクルポリシーでの対処が必要になる場合がある。
