---
title: Limiter Dependency Injection
status: Accepted
date: 2026-02-18
context: Decoupling Rate Limiter from Core
---

# Limiter Dependency Injection

## Context and Problem Statement / コンテキスト

以前、`core.py` の `Spot` クラスは `TokenBucket` 実装と密結合していました。`Spot` は `tpm` (tokens per minute) 整数引数を受け取り、内部で `TokenBucket` をインスタンス化していました。

この設計にはいくつかの制限がありました：
1.  **Testing**: ユニットテストが `TokenBucket` 内の本物の `time.sleep` 呼び出しに依存するため、実行が遅くなっていました。
2.  **Extensibility**: ユーザーがカスタムレートリミッター（例：Redisベースの分散リミッター）や異なるアルゴリズムを提供できませんでした。
3.  **Separation of Concerns**: `core.Spot` がリミッターのライフサイクルと設定を管理しており、単一責任の原則に違反していました。

## Decision Drivers / 要求

* **Testability**: テスト中にスリープ時間を排除するために、`MockLimiter` や `NoOpLimiter` を注入できるようにすること。
* **Flexibility**: コアロジックを修正することなく、ユーザーがカスタムリミッターを実装できるようにすること。
* **Clean Core**: `core.Spot` を簡素化し、リミッターの初期化処理を排除すること。

## Considered Options / 検討

* **Option 1**: 引き続き `Spot` クラス内でリミッターの実装をハードコードする。
* **Option 2**: 抽象プロトコル `LimiterProtocol` を導入し、依存性注入 (DI) を使用してリミッターを外部から提供する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

レートリミッターを `core.Spot` から切り離し、依存性注入 (DI) を使用します。

1.  **Protocol Definition**: `beautyspot.limiter` に `consume(cost: int)` と `consume_async(cost: int)` メソッドを規定する `LimiterProtocol` を定義します。
2.  **Explicit Inheritance**: デフォルトの `TokenBucket` 実装は、型安全性と明確さのために `LimiterProtocol` を明示的に継承します。
3.  **Injection**: `core.Spot.__init__` を、`tpm` の代わりに `limiter: LimiterProtocol` インスタンスを受け取るように変更します。
4.  **Factory Responsibility**: `__init__.py` の `Spot` ファクトリ関数が、カスタムリミッターが提供されない場合のデフォルトの `TokenBucket` 作成を担当します。

## Consequences / 決定

* **Positive**:
    * **テスト容易性**: `MockLimiter` などを注入することで、テストの高速化が可能になった。
    * **柔軟性**: 外部ストアを利用したリミッターなどを、コアを汚さずに実装可能になった。
    * **クリーンなコア**: `Spot` クラスの責務が削減され、コードが簡素化された。
* **Negative**:
    * 内部クラス `_Spot` のシグネチャが変更されるため、直接インスタンス化していたコードに影響がある（公開されている `Spot` ファクトリ経由であれば影響なし）。
