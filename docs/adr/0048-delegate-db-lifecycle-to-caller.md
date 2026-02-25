---
title: Delegate Database Lifecycle Management to Caller
status: Accepted
date: 2026-02-24
context: Correcting Resource Ownership in DI Architecture
---

# Delegate Database Lifecycle Management to Caller

## Context and Problem Statement / コンテキスト

`Spot` クラスは `TaskDBBase` インスタンスを DI で受け取っているにもかかわらず、シャットダウン処理内で強制的に `db.shutdown()` を呼び出していました。これにより、複数の `Spot` インスタンスで 1 つの DB を共有する場合、一方の `Spot` が破棄されると他の `Spot` も DB にアクセスできなくなるという重大なバグが生じていました。これは DI の導入と、GC 時の強制破棄戦略が複雑に絡み合った結果の技術的負債でした。

## Decision Drivers / 要求

* **Shared Resource Support**: 複数の `Spot` インスタンス間で単一の DB インスタンスを安全に共有できるようにすること。
* **Principle of Ownership**: リソースを注入した側がそのライフサイクル（クローズ処理）に責任を持つという、DI の原則を徹底すること。
* **Stability**: バックグラウンドタスクが実行されている最中に、DB コネクションが予期せず閉じられることを防ぐこと。

## Considered Options / 検討

* **Option 1**: `Spot` が引き続き DB のシャットダウンを担当する。インスタンス共有時にクラッシュするリスクがある。
* **Option 2**: `Spot` クラスから `db.shutdown()` の呼び出しを削除し、DB を生成・注入した側の責任とする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`Spot` クラス内部から `db.shutdown()` の呼び出しを完全に削除します。リソース（DB インスタンス）を生成して注入した側が、そのライフサイクルの全責任を負うという原則を厳格に適用します。

## Consequences / 決定

* **Positive**:
    * 複数の `Spot` インスタンスでの DB 共有が安全に行えるようになり、関心の分離が明確になった。
    * バックグラウンドタスク実行中に DB が不意に閉じられることによるエラーやデータロストのリスクが解消された。
* **Negative**:
    * アプリケーション側で DB を適切にクローズし忘れると、コネクションリークが発生する可能性がある。
* **Mitigation**:
    * ドキュメントにて、カスタム DB を使用する場合のライフサイクル管理の責任について明確に警告し、適切な使用例を示す。
