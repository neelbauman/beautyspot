# docs/adr/0016-nested-msgpack-protocol.md

---
title: Nested Msgpack Protocol via Serializer Wrapping
status: Accepted
date: 2026-02-02
context: Improving DX for Custom Types
---

# Nested Msgpack Protocol via Serializer Wrapping

## Context and Problem Statement / コンテキスト

これまでは、カスタム型のエンコーダは `ExtType` の仕様に合わせて「生のバイト列」を返す必要がありました。
これにより、ユーザーは `msgpack` ライブラリを直接操作する必要があり、Pydantic モデルなどの扱いが煩雑になっていました。

## Decision Drivers / 要求

* **Simplicity:** ユーザー関数は、ただの型変換（Obj <-> Dict）のみに集中すべきである。
* **Encapsulation:** バイナリ化（Pack/Unpack）の責務はライブラリ側が負うべきである。

## Considered Options / 検討

* **Option 1**: エンコーダが生のバイト列（`bytes`）を返し、デコーダがそれを受け取る（旧仕様）。
* **Option 2**: シリアライザラッピングを採用。エンコーダは Python オブジェクト（Dict 等）を返し、ライブラリが内部で Msgpack 化して保持する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

**Serializer Wrapping (Nested Protocol)** を採用します。

1.  `MsgpackSerializer` は、ユーザー定義のエンコーダ/デコーダに対する**ラッパー（Wrapper）**として機能する。
2.  **Encode時:** エンコーダが返したオブジェクト（中間表現）を、ライブラリが自動的に `packb` して `ExtType` に格納する。
3.  **Decode時:** `ExtType` のデータを、ライブラリが自動的に `unpackb` してからデコーダに渡す。
4.  これにより、ユーザーは `import msgpack` をする必要がなくなり、直感的な実装が可能になる。

## Consequences / 決定

* **Positive**:
    * Pydantic v2 や Dataclasses のサポートが極めて容易になる。
    * 内部的に再帰呼び出しを行うため、カスタム型のネストも自動的に解決される。
* **Negative**:
    * 内部での再帰的な Pack/Unpack による、わずかなパフォーマンス上のオーバーヘッドが発生する可能性がある。

