---
title: Resilient Deserialization and Explicit Versioning
status: Proposed
date: 2025-11-21
context: Issue3
---

# Resilient Deserialization and Explicit Versioning

## Context and Problem Statement / コンテキスト

Pythonの `pickle` は、保存されたオブジェクトのクラス定義と現在のコードが一致していることを前提とします。
開発中はクラス定義が頻繁に変更されるため、過去のキャッシュを読み込む際に `AttributeError` 等が発生し、アプリケーションがクラッシュする問題がありました。

## Decision Drivers / 要求

* **Fault Tolerance**: キャッシュデータがコードの変更と不整合を起こしても、アプリケーションをクラッシュさせないこと。
* **Developer Experience (DX)**: 開発中の頻繁なリファクタリングを妨げないこと。
* **Explicit Control**: ユーザーが意図したタイミングでキャッシュを無効化できる手段を提供すること。
* **Safe Deployment**: 本番環境において、安全にキャッシュを刷新できること。

## Considered Options / 検討

* **Option 1**: デシリアライズエラー時に例外を送出し、実行を停止する（既存挙動）。
* **Option 2**: エラーを捕捉して「キャッシュミス」として扱い、再計算を行う。あわせて明示的な `version` 指定による無効化を可能にする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

1.  **Fail Safe (Auto Recalc):** `Storage.load()` でデシリアライズエラー（クラス不整合や破損）が発生した場合、これを `CacheCorruptedError` として捕捉し、`core.py` 側で **「キャッシュミス」** として扱う。これによりアプリをクラッシュさせず、自動的に再計算を行う。
2.  **Explicit Versioning:** ユーザーが意図的にキャッシュを無効化できるよう、`@task` デコレータに `version` 引数を追加する。これを変更するとキャッシュキーが変わり、古い（互換性のない）キャッシュを参照しなくなる。
3.  **User Guidance:** 自動再計算が発生した際、ログに「コード変更時は `version` の更新を検討してね」というヒントを出力し、ベストプラクティスへ誘導する。

## Consequences / 決定

* **Positive**:
    * 開発中のクラッシュを防ぎ、スムーズなDXを提供する。
    * 本番運用時でも、`version` を使うことで安全なデプロイ（キャッシュ切り替え）が可能になる。
* **Negative**:
    * 再計算コストが発生する（が、クラッシュよりはマシである）。
