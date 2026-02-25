---
title: Background Loop Shutdown Strategy on Garbage Collection
status: Proposed
date: 2026-02-24
context: Balancing Resource Cleanup and Data Integrity during GC
---

# Background Loop Shutdown Strategy on Garbage Collection

## Context and Problem Statement / コンテキスト

`beautyspot` はキャッシュの永続化をバックグラウンドスレッドにオフロードしています。コンテキストマネージャを使用した場合は安全にタスクがドレインされますが、インスタンスをグローバルに生成して使い捨てた場合など、ガベージコレクション (GC) によってインスタンスが破棄される際の振る舞いが課題となっていました。GC のタイミングで未完了の I/O タスクを待機すべきか、それとも破棄すべきかを決定する必要があります。

## Decision Drivers / 要求

* **Responsiveness**: GC は任意のタイミングで発生するため、メインスレッドを予期せずフリーズさせないこと。
* **Predictability**: リソース管理の責務を明確にし、マジックに頼りすぎない予測可能なライフサイクルを提供すること。
* **Observability**: 適切でない管理によってデータが破棄された場合に、開発者がそれを検知できるようにすること。

## Considered Options / 検討

* **Option 1**: GC 時にもタスクの完了を待機する。メインスレッドがフリーズするリスクがある。
* **Option 2**: 未完了タスクを即座に破棄（キャンセル）し、警告を発行する。メインスレッドの安定性を最優先する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

ガベージコレクション (`weakref.finalize`) によるインスタンス破棄時には、**未完了のタスクを待機せず、即座に破棄する（Fail-fast & Non-blocking）** ことを決定しました。

同時に、タスクが破棄された場合は `logger.warning` および `ResourceWarning` を発行し、ユーザーに対してコンテキストマネージャや明示的な `shutdown()` の使用を強く促します。

## Consequences / 決定

* **Positive**:
    * `beautyspot` が原因でアプリケーションの GC やシャットダウンがハングアップしないことが保証される。
    * ライフサイクル管理の重要性をユーザーに明示的に伝えることができる。
* **Negative**:
    * 不適切な使い方をした場合、キャッシュが永続化されない（データロスト）事象が発生する。
* **Mitigation**:
    * ドキュメントにてコンテキストマネージャの利用をベストプラクティスとして周知し、安全な管理方法を強調する。
