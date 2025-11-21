---
title:  Semantic Content Type Support
status: Proposed
date: 2025-11-21
context: Issue and Bugfix
---

# Semantic Content Type Support

## Context
生成AIタスクの出力は、テキストだけでなく、画像、構造化データ、ダイアグラム（Mermaid, Graphviz/DOT, HTML）など多岐にわたる。
現状のデータベーススキーマ（`result_type` = `FILE` | `DIRECT`）は「データの保存形式」しか保持しておらず、「データの意味的種類（Semantic Type）」が不明であるため、ダッシュボードでの復元時に適切な可視化（レンダリング）ができない。

また、`beautyspot` はライブラリとしてユーザーの手元で動作するため、複雑なマイグレーション手順や重量級の依存関係（Alembicなど）を強制することはUXを損なう。

## Decision

### 1. Database Schema & Migration
* **Schema Change:** `tasks` テーブルに `content_type` (TEXT) カラムを追加する。
* **Migration Strategy:** **"Auto-Migration on Startup"** を採用する。
    * Alembic等は導入しない（依存関係の軽量化とUX維持のため）。
    * `Project` 初期化時（`_init_db`）に `PRAGMA table_info` でカラムの存在を確認し、不足していれば標準ライブラリのみで `ALTER TABLE` を自動実行する。

### 2. Type Definition
* `src/beautyspot/types.py` を新設し、`ContentType` クラスで定数を管理する。
* **Graphviz (DOT)** と **Mermaid** を明確に区別する。
    * `ContentType.GRAPHVIZ` (`text/vnd.graphviz`)
    * `ContentType.MERMAID` (`text/vnd.mermaid`)

### 3. Interface
* `@project.task` デコレータに `content_type` 引数を追加し、開発者が戻り値の型を宣言できるようにする。

### 4. Rendering Strategy (Dashboard)
* **Graphviz:** Pythonの `graphviz` ライブラリと `st.graphviz_chart` を使用する。
* **Mermaid:** Streamlit標準コンポーネントがないため、`st.components.v1.html` を使用して Mermaid.js (CDN) を注入し、ブラウザ側でレンダリングする。

### 5. Dependencies
* `pyproject.toml` に `graphviz>=0.20.1` を追加する。

## Consequences

### Positive
* ダッシュボードで、生成AIが出力したアーキテクチャ図やフローチャートを直感的に閲覧できるようになる。
* ユーザーはデータベースのアップグレード作業を意識する必要がない（自動化）。
* データの「中身」を解析して表示形式を推測する不安定なロジックを排除できる。

### Negative / Risks
* **OS依存:** Graphvizのレンダリングには、ユーザー環境に `dot` コマンド（OSレベルのパッケージ）がインストールされている必要がある。
* **Client-Side Rendering:** MermaidはCDN経由のJS実行となるため、オフライン環境では表示されない場合がある。

