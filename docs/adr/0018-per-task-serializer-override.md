---
title: Per-Task Serializer Override
status: Accepted
date: 2026-02-02
context: Flexibility for Special Data Types
---

# Per-Task Serializer Override

## Context and Problem Statement / コンテキスト

プロジェクト全体としては安全性と互換性の観点から `msgpack` を標準シリアライザとしています。
しかし、探索的データ分析（EDA）やプロトタイピング、あるいは `msgpack` でのシリアライズが困難なサードパーティ製オブジェクトを扱う特定のタスクにおいては、Python標準の `pickle` のような柔軟なシリアライザを局所的に使用したいというニーズがあります。

## Decision Drivers / 要求

* **Flexibility**: 標準シリアライザで扱いにくい特殊なオブジェクトに対して、最適な保存方法を選択できること。
* **Locality**: プロジェクト全体の設定（セキュリティポリシー等）を損なうことなく、特定の箇所だけで設定を上書きできること。
* **Fault Tolerance**: オーバーライドされたシリアライザでエラーが発生しても、再計算によって実行を継続できること。

## Considered Options / 検討

* **Option 1**: グローバルなシリアライザ設定のみを提供し、個別の変更は認めない。
* **Option 2**: `Spot.mark()` および `Spot.cached_run()` に `serializer` 引数を追加し、局所的なオーバーライドを可能にする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

1.  **Override Mechanism:** `Spot.mark()` および `Spot.cached_run()` に、オプショナル引数 `serializer` を追加します。
2.  **Protocol:** ユーザーは `dumps(obj) -> bytes` および `loads(bytes) -> obj` メソッドを持つ任意のオブジェクトを渡すことができます。
3.  **Fallback Behavior:** 指定されたシリアライザでデシリアライズに失敗した場合、ADR-0003 の方針に従い、キャッシュ破損として扱い、タスクを再実行します。

## Consequences / 決定

* **Positive**:
    * ユーザーはプロジェクト全体の設定を変更することなく、必要な箇所だけで `pickle` 等の機能を利用できる。
    * キャッシュが読み込めなくなった場合も、自動的に再計算されるため、開発体験（DX）が損なわれない。
* **Negative**:
    * `pickle` を使用したタスクは、異なる環境間や長期間の保存において互換性が保証されない。
    * `Spot.register()` で登録したカスタム型変換は、オーバーライドされたシリアライザには適用されない。
