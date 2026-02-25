---
title: Dashboard Interaction Model
status: Proposed
date: 2025-11-22
context: Issue
---

# Dashboard Interaction Model

## Context and Problem Statement / コンテキスト

現状のダッシュボード (`dashboard.py`) では、タスク一覧の表示と詳細データの復元操作が分離しています。
ユーザーは一覧テーブルで対象を確認した後、別途ドロップダウンメニューから対応する `cache_key` (ハッシュ値) を手動で探し出す必要があり、認知負荷が高い状態です。
プロジェクトの依存関係として `streamlit>=1.51.0` が確保されており、インタラクティブなデータフレーム機能が利用可能となっています。

## Decision Drivers / 要求

* **Lower Cognitive Load**: ユーザーがハッシュ値を意識することなく、直感的にデータを操作できること。
* **Seamless Navigation**: 一覧での選択が即座に詳細ビューに反映されること。
* **Modern UI Experience**: Streamlit の最新機能を活用し、洗練された操作感を提供すること。

## Considered Options / 検討

* **Option 1**: 現状維持（テーブルと選択用ドロップダウンの分離）。
* **Option 2**: `st.dataframe` の `on_select` 機能を使用し、テーブル行のクリックによって詳細ビュー（Restore Data）のコンテキストを切り替える方式。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`st.dataframe` の `on_select` 機能を使用し、テーブル行のクリックによって詳細ビューのコンテキストを切り替える方式を採用します。これにより、ユーザーはテーブル上のレコードを直接クリックするだけで、そのタスクの詳細や保存されたデータを復元できるようになります。

## Consequences / 決定

* **Positive**:
    * ユーザーは直感的にレコードを選択・復元できる。
    * フィルタリングされた結果に対しても、正しい行インデックスで詳細へアクセスできる。
* **Negative**:
    * Streamlit の古いバージョン（<1.35）との互換性が失われる（ただし `pyproject.toml` でバージョン指定済みのため許容）。

