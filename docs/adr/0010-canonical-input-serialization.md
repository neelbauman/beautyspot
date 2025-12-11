---
title: Canonical Input Serialization with Msgpack and SHA-256
status: Accepted
date: 2025-12-11
context: v2.0.0 Architecture Refinement
---

# Canonical Input Serialization with Msgpack and SHA-256

## Context and Problem Statement

`beautyspot` はこれまで、キャッシュキーの生成に `json.dumps(sort_keys=True)` と `MD5` を使用していた。
しかし、以下の課題が顕在化していた：

1.  **バイナリデータの非効率性:** Numpy配列や画像データなどをJSON化する際、テキスト変換（`tolist()` や `str()`）による巨大なオーバーヘッドとメモリ消費が発生する。
2.  **ハッシュの衝突リスク:** `str()` に依存したフォールバックでは、巨大なNumpy配列が省略表示（`...`）された際にハッシュが衝突し、誤ったキャッシュヒットを引き起こす危険性がある。
3.  **アルゴリズムの老朽化:** `MD5` は現代のセキュリティ基準では非推奨とされており、コンプライアンス上の懸念がある。

## Decision Drivers

* **Accuracy:** 入力データが少しでも異なれば、確実に異なるキーを生成したい（特にNumpy配列）。
* **Performance:** バイナリデータを効率的に扱いたい。
* **Consistency:** 入力（キー生成）も出力（データ保存）も `msgpack` エコシステムで統一したい。

## Decision Outcome

キャッシュキー生成ロジックを以下のように刷新する：

1.  **Canonicalization (正規化):**
    * 独自の正規化関数 `canonicalize(obj)` を実装する。
    * **Dict:** キーでソートされた「タプルのリスト `[[k, v], ...]`」に変換し、順序を固定する。
    * **Set:** ソートされたリストに変換する。
    * **Numpy:** `numpy` をインポートせず、Duck Typing（`shape`, `dtype`, `tobytes` 属性の確認）により検知し、生のバイト列を含むタプルに変換する。これにより完全な一意性を保証する。
2.  **Serialization:**
    * 正規化されたオブジェクトを `msgpack` でシリアライズする。
3.  **Hashing:**
    * ハッシュアルゴリズムを `SHA-256` に変更する。

## Consequences

* **Positive:**
    * Numpy配列などのバイナリデータに対するハッシュ生成が劇的に高速化・省メモリ化される。
    * 省略表示によるハッシュ衝突バグが解消される。
    * `pickle` を使用しないため、安全性（RCEフリー）が維持される。
* **Negative:**
    * **破壊的変更:** 既存のキャッシュ（v1.x）とはキーが一致しなくなるため、v2.0.0 でのリリースが必要。
    * 巨大で深くネストした辞書データの場合、Python側での正規化処理により若干のオーバーヘッド増が発生する可能性がある。
