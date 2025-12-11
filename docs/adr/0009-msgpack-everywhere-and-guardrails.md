---
title: Msgpack Everywhere with Native BLOB Support
status: Accepted
date: 2025-12-11
context: v1.0.0 Refinement
---

# Msgpack Everywhere with Native BLOB Support

## Context and Problem Statement

ADR-0007 で `MsgpackSerializer` を導入したが、SQLiteへの保存方式について以下の課題が残っていた。

1.  **JSONの限界:** 従来の `TEXT` カラム（JSON）ではバイナリデータを扱えず、Numpy配列などが保存できない。
2.  **Base64の非効率性:** `TEXT` カラムに保存するために Msgpack を Base64 エンコードする案（旧ADR-0009）があったが、データサイズが約33%増加し、CPUコストもかかる。
3.  **一貫性:** 画像や動画などのバイナリデータも、可能な限り変換なしで「そのまま」扱いたい。

## Decision Drivers

* **Performance:** シリアライズ/デシリアライズのオーバーヘッド（Base64等）を最小化したい。
* **Efficiency:** ストレージ容量を無駄に消費したくない。
* **Consistency:** 小さいデータ（DB内）も大きいデータ（外部ファイル）も、同じ Msgpack フォーマットで統一したい。

## Decision Outcome

### 1. Schema Change: Add BLOB Column
`tasks` テーブルに、バイナリデータをそのまま格納するための **`result_data` (BLOB)** カラムを追加する。

* 既存の `result_value` (TEXT) カラムは、ファイルパスやレガシーなJSONデータの保持用に継続利用する。
* マイグレーションは `Project` 初期化時に `ALTER TABLE` で自動的に行われる。

### 2. Msgpack Everywhere Strategy
データの保存先に関わらず、常に `MsgpackSerializer` を通過させる。

* **`save_blob=False` (Direct Mode):**
    * Msgpackバイナリを **`result_data` (BLOB) カラム** にそのまま保存する。
    * `result_type` は **`DIRECT_BLOB`** とする。
* **`save_blob=True` (Blob Mode):**
    * Msgpackバイナリを外部ファイル（`.bin`）として保存。
    * ファイルパスを **`result_value` (TEXT) カラム** に保存する。
    * `result_type` は `FILE` とする。

### 3. Size Guardrails (Unchanged)
`save_blob=False` であっても、閾値（デフォルト: 1MB）を超えるデータが渡された場合は、警告ログ (`WARNING`) を出力して `save_blob=True` の利用を促す。

## Consequences

* **Positive:**
    * **最高効率:** Base64エンコードが不要になり、データサイズとCPU負荷が最小化される。
    * **互換性:** 既存の `result_value` カラムを維持するため、旧バージョンのキャッシュデータも読み込み可能。
* **Negative:**
    * データベースのスキーマ変更（マイグレーション処理）が必要になる。
    * `sqlite3` コマンドラインツール等で `SELECT` した際、中身がバイナリのため視認できない（ダッシュボード等のツールが必要）。

