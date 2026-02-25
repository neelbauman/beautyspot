---
title: Refactoring Complex Modules with Single Dispatch
status: Accepted
date: 2026-02-16
context: Improving Code Maintainability
---

# Refactoring Complex Modules with Single Dispatch

## Context and Problem Statement / コンテキスト

`quality_report` により、`src/beautyspot/cachekey.py` の `canonicalize` 関数が非常に高い循環的複雑度（ランク D）を持っていることが判明しました。この関数は、ハッシュ化のためのオブジェクト正規化において、`dict`, `list`, `set`, `numpy`, `type` など多岐にわたる型をチェックするために長い `if-elif-else` チェーンを使用していました。

この構造は開放閉鎖の原則 (Open-Closed Principle) に違反しており、新しい型のサポートを追加するたびにコア関数を修正する必要があるため、退行（デグレード）のリスクを高めていました。

## Decision Drivers / 要求

* **Maintainability**: 高い複雑度を解消し、各型の処理ロジックを独立させること。
* **Extensibility**: 既存のコードを変更することなく、新しい型への対応を容易にすること。
* **Readability**: 1つの関数が負うべき責任を明確にし、コードの可読性を向上させること。

## Considered Options / 検討

* **Option 1**: 現状の巨大な `if-elif` チェーンを維持する。
* **Option 2**: Python 標準ライブラリの `functools.singledispatch` を使用してリファクタリングする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`canonicalize` 関数を `functools.singledispatch` を用いて刷新します。

* **Default Dispatch**: プリミティブ型、フォールバックロジック (`str`)、およびダックタイピングによるチェック（Numpy 配列や `__dict__` を持つオブジェクト等）を処理する。
* **Registered Handlers**: `dict`, `list`, `tuple`, `set`, `frozenset`, `type` 等の特定のロジックは、装飾された独立した関数に移動する。

## Consequences / 決定

* **Positive**:
    * **複雑度の低減**: メイン関数のロジックが、焦点を絞った小さなハンドラに分割される。
    * **拡張性**: 既存コードを変更せずに、新しいハンドラを登録するだけで将来の型をサポートできる。
    * **可読性**: 各ハンドラが単一の型に対する責任に集中できる。
* **Negative**:
    * **ダックタイピングの制限**: `singledispatch` は厳密な型に基づいているため、Numpy のようなダックタイピングによるチェックは依然としてデフォルトハンドラや基底層で行う必要がある。
