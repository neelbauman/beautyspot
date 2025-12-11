---
title: Msgpack Everywhere and Size Guardrails
status: Accepted
date: 2025-12-11
context: v1.0.0 Refinement
---

# Msgpack Everywhere and Size Guardrails

## Context and Problem Statement

ADR-0007 で `MsgpackSerializer` を導入したが、`save_blob=False`（SQLiteへの直接保存）を選択した場合、依然として `json.dumps` が使用されていた。
これにより以下の問題が発生していた：

1.  **一貫性の欠如:** `register_type` で登録したカスタム型（例: Numpy配列）が、`save_blob=False` の時だけ文字列化されてしまい、正しく復元できない。
2.  **DB肥大化のリスク:** ユーザーが誤って巨大なデータ（画像や動画など）を `save_blob=True` なしで返した場合、警告なしにSQLiteに保存され、データベースファイルが肥大化してしまう。

## Decision Drivers

* **Consistency:** 保存先に関わらず、カスタム型のシリアライズ/デシリアライズが一貫して動作すること。
* **Safety:** 意図しないDB肥大化を防ぐためのフィードバック（ガードレール）をユーザーに提供すること。
* **Explicit over Implicit:** サイズによる「自動振り分け」のようなマジックを行わず、ユーザーの明示的な設定を尊重すること。

## Decision Outcome

### 1. Msgpack Everywhere Strategy
データの保存先（SQLite or Blob）に関わらず、**常に `MsgpackSerializer` を通過させる。**

* **`save_blob=True` (Blob Mode):**
    * Msgpackバイナリをそのまま外部ファイル（`.bin`）として保存。
* **`save_blob=False` (Direct Mode):**
    * Msgpackバイナリを **Base64エンコード** し、SQLiteの `TEXT` カラムに保存する。
    * 保存時の `result_type` として新たに `DIRECT_B64` を定義する。

### 2. Size-based Warning Guardrails
`save_blob=False` が指定されているにもかかわらず、シリアライズ後のデータサイズが閾値（デフォルト: 1MB）を超えた場合、**警告ログ (`WARNING`) を出力する。**

* **閾値の設定:** `Project` 初期化時に `blob_warning_threshold` 引数で設定可能にする。
* **挙動:** エラーにはせず保存は行うが、ログで `save_blob=True` の利用を促す。

### 3. No Auto-Dispatch
データサイズや型に基づいて、ライブラリが勝手に保存先（SQLite vs File）を切り替える機能は**実装しない**。
予測可能性とパフォーマンス（二重シリアライズ回避）を優先する。

## Consequences

* **Positive:**
    * Numpy配列などのカスタム型が、SQLite保存であっても安全に復元可能になる。
    * 巨大なデータを誤ってDBに入れるミスを、実行時のログで早期発見できる。
    * SQLite公式の推奨（100KB未満はDB内の方が高速）に従った使い分けを、ユーザーに自然に促すことができる。
* **Negative:**
    * SQLite内のデータがBase64文字列となるため、`SELECT` 文で直接中身を読むことが難しくなる（可読性の低下）。
    * Base64化により、データサイズが約33%増加する（ただし100KB以下のデータであれば許容範囲とする）。

