---
title: Bounded LRU Cache for Subclass Resolution in Serializer
status: Accepted
date: 2026-02-24
context: Preventing Memory Leaks in Dynamic Environments
---

# Bounded LRU Cache for Subclass Resolution in Serializer

## Context and Problem Statement / コンテキスト

`MsgpackSerializer` の `_default_packer` において、クラスの解決結果を保存するキャッシュ辞書が、動的に型が生成される環境（動的な Pydantic モデル等）で無制限に肥大化し、メモリリークを引き起こす懸念がありました。
また、この辞書へのアクセスは非常に高頻度であるため、厳密なスレッドセーフティ（ロック）を導入すると、シリアライズ性能のボトルネック（ロック競合）を招く恐れがありました。

## Decision Drivers / 要求

* **Memory Safety**: 動的な型生成が繰り返される環境下でも、キャッシュサイズが一定の上限を超えないようにし、メモリリークを防止すること。
* **High Performance**: シリアライズのホットパス（実行頻度の高い経路）において、ロックのオーバーヘッドを最小限に抑えること。
* **Zero Dependencies**: 標準ライブラリのみで完結させること。

## Considered Options / 検討

* **Option 1**: 現状維持（無制限の `dict`）。メモリリークのリスクがある。
* **Option 2**: 厳密なスレッドセーフな LRU キャッシュの導入。パフォーマンス低下のリスクがある。
* **Option 3**: `OrderedDict` を利用した上限付き LRU キャッシュを、楽観的（ロックフリー）なアプローチで実装する。

## Decision Outcome / 決定

Chosen option: **Option 3**.

標準ライブラリの `collections.OrderedDict` を利用し、上限サイズ（デフォルト 1024）を持つ **LRU (Least Recently Used) キャッシュ** を導入します。マルチスレッド環境下でのアクセスに対しては、意図的にロックフリーなアプローチを維持します。

## Consequences / 決定

* **Positive**:
    * キャッシュサイズが上限に保たれ、メモリ肥大化を確実に防止できる。
    * ロックのオーバーヘッドが発生しないため、高いシリアライズ性能を維持できる。
* **Negative**:
    * スレッドセーフではないため、マルチスレッド下で稀に LRU の順序が乱れたり、重複した解決処理が走る可能性がある。ただし、プロセスクラッシュには至らず、実用上の影響も軽微であるため許容する。
