---
title: Strict Scoping for Imperative Execution (Runtime Guard)
status: Superseded by [ADR-0032](0032-relax-cached-run-scoping.md)
date: 2026-02-01
context: Safety and Resource Management
---

# Strict Scoping for Imperative Execution (Runtime Guard)

## Context and Problem Statement / コンテキスト

`spot.cached_run()` コンテキストマネージャを使用すると、ユーザーは一時的に関数のキャッシュ挙動を適用できます。しかし、Python の `with` 文のスコープルールにより、ブロック内でバインドされた変数（例: `with ... as task:`）はブロック終了後もアクセス可能です。

これにより、ユーザーが特定のコンテキスト設定（`version="v1"` や一時的なストレージ設定など）を持つ関数ラッパーを、意図しない場所で再利用してしまうリスクがあります。これは微妙なバグやリソースリークの原因となります。

## Decision Drivers / 要求

* **Safety**: 意図しないスコープ外での「古い」または「コンテキスト固有の」ラッパーの使用を排除すること。
* **Clarity**: キャッシュ挙動が厳密に一時的なものであるというメンタルモデルを強制すること。
* **Resource Management**: 短命な `spot` インスタンスや注入されたインスタンスをより安全に使用できるようにすること。

## Considered Options / 検討

* **Option 1**: ガードを実装せず、ユーザーの注意に任せる。
* **Option 2**: **Runtime Guard** パターンを導入し、ブロック外での呼び出しを制限する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`ScopedMark` コンテキストマネージャに **Runtime Guard** パターンを実装します。

1.  **State Tracking**: コンテキストマネージャはアクティブ状態のフラグを保持する。
2.  **Wrapper Guard**: `cached_run` から返される関数は、実行前にこのフラグをチェックするガードでラップされる。
3.  **Fail Fast**: ラップされた関数が `with` ブロックの外で呼び出された場合、即座に `RuntimeError` を送出する。

## Consequences / 決定

* **Positive**:
    * 意図しないスコープ外での使用によるリスクを排除できる。
    * 「キャッシュマジック」は厳密に一時的なものであるという確信が持てる。
    * 関数参照が使用直後に無効になるため、リソース管理が安全になる。
* **Negative**:
    * ブロック内での関数呼び出しごとに、極小のオーバーヘッド（ブールフラグのチェック）が発生する。
    * ラップ処理の追加により、`ScopedMark` の実装がわずかに複雑になる。
