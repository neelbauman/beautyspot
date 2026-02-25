---
title: Thread-safe LRU Cache for Serializer
status: Accepted
date: 2026-02-24
context: Ensuring Stability in Multi-threaded Environments
---

# Thread-safe LRU Cache for Serializer

## Context and Problem Statement / コンテキスト

`MsgpackSerializer` は動的型生成時のメモリリークを防ぐために、内部で `OrderedDict` を用いた LRU キャッシュを運用しています。しかし、バックグラウンド保存や Web フレームワークでの利用など、マルチスレッド環境からの並行アクセスが日常的に発生します。ロックを持たない `OrderedDict` への並行操作は、`RuntimeError` やデータの破損を引き起こす致命的なバグの温床となっていました。

## Decision Drivers / 要求

* **Stability**: マルチスレッド環境下での並行アクセスによるクラッシュやデータ破損を完全に排除すること。
* **Reliability**: デバッグ困難な稀に発生する競合状態を未然に防ぎ、ライブラリの信頼性を高めること。
* **Performance**: ロックの範囲を最小限に留め、シリアライズ処理全体のスループットへの影響を最小化すること。

## Considered Options / 検討

* **Option 1**: 引き続きロックフリーなアプローチをとり、エラー発生時にリトライする。
* **Option 2**: `threading.Lock()` を導入し、キャッシュ操作を排他的に行う。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`MsgpackSerializer` の内部状態（キャッシュおよびレジストリ）に対するすべての読み書き操作を `threading.Lock()` で保護します。

1. **安定性の優先**: 確実な排他制御により、マルチスレッド下での信頼性を担保します。
2. **限定的なロック範囲**: ロックの範囲を「型の解決とキャッシュの更新」というメモリアクセス領域に限定し、重いシリアライズ処理（I/O や計算）はロック外で実行します。

## Consequences / 決定

* **Positive**:
    * `MsgpackSerializer` をシングルトンとして安全にマルチスレッド環境で使い回せるようになった。
    * 競合状態に起因する非決定的なクラッシュを排除できた。
* **Negative**:
    * キャッシュアクセスごとにロック取得のオーバーヘッドが追加されるが、実用上のパフォーマンスインパクトは極めて軽微である。
