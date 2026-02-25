---
title: Garbage Collection Strategy for Abandoned Temporary Files
status: Accepted
date: 2026-02-24
context: Preventing Storage Leaks from Atomic Write Failures
---

# Garbage Collection Strategy for Abandoned Temporary Files

## Context and Problem Statement / コンテキスト

Blob データの保存時、アトミックな書き込みを実現するために一時ファイルを作成し、完了後にリネームする設計を採用しています。しかし、アンチウイルスソフトやバックアッププロセスの介入によりリネームが失敗するエッジケースが存在します。この際、一時ファイルの削除もロックにより失敗すると、一時ファイルがストレージ上に永久に残留し続ける（ストレージリーク）という問題がありました。

## Decision Drivers / 要求

* **Self-Healing**: 書き込み失敗やクラッシュによって残された一時ファイルを、ユーザーの介入なしに自動でクリーンアップすること。
* **Safety**: 現在書き込み中の別プロセスのファイルを誤って削除しないよう、適切な猶予期間を設けること。
* **Traceability**: 管理対象の一時ファイルを、通常のキャッシュファイルや他のファイルと容易に区別できるようにすること。

## Considered Options / 検討

* **Option 1**: 失敗した一時ファイルを無視する（ストレージリークを許容）。
* **Option 2**: 失敗時に即座にループで再試行する。長時間ロックされている場合にプロセスを停滞させるリスクがある。
* **Option 3**: 専用のサフィックスを付与し、`MaintenanceService` による遅延ガベージコレクション (GC) を導入する。

## Decision Outcome / 決定

Chosen option: **Option 3**.

アトミック書き込みのフェイルセーフとして、以下の機構を導入します。

1. **専用サフィックスの導入**: 一時ファイルの生成時に `.spot_tmp` という専用のサフィックスを付与し、追跡を容易にします。
2. **遅延ガベージコレクション (GC)**: `MaintenanceService.clean_garbage` に、一時ファイルの削除処理を統合します。
3. **Grace Period (猶予期間) の設定**: 更新時刻が指定時間（デフォルト24時間）を経過しているもののみを削除対象とし、並行プロセスへの影響を回避します。

## Consequences / 決定

* **Positive**:
    * アプリのクラッシュやファイルロックが発生しても、自動エビクションによってストレージが自己修復される。
    * ユーザーはストレージリークを意識することなく安全に運用できる。
* **Negative**:
    * 失敗した一時ファイルは最大24時間ストレージ容量を占有し続けるが、実用上の影響は皆無である。
