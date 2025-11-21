---
title: Dashboard Interaction Model
status: Proposed
date: 2025-11-22
context: Issue
---

# ADR-002: Dashboard Interaction Model

## Context
現状のダッシュボード (`dashboard.py`) では、タスク一覧の表示と詳細データの復元操作が分離している。
ユーザーは一覧テーブルで対象を確認した後、別途ドロップダウンメニューから対応する `cache_key` (ハッシュ値) を手動で探し出す必要があり、認知負荷が高い。
プロジェクトの依存関係として `streamlit>=1.51.0` が確保されており、インタラクティブなデータフレーム機能が利用可能である。

## Decision
`st.dataframe` の `on_select` 機能を使用し、テーブル行のクリックによって詳細ビュー（Restore Data）のコンテキストを切り替える方式を採用する。

## Consequences
* **Positive:** ユーザーは直感的にレコードを選択・復元できる。
* **Positive:** フィルタリングされた結果に対しても、正しい行インデックスで詳細へアクセスできる。
* **Negative:** Streamlit の古いバージョン（<1.35）との互換性が失われる（ただし `pyproject.toml` でバージョン指定済みのため許容）。

## Status
Proposed

