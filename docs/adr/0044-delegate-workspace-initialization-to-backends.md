---
title: Delegate Workspace Initialization to Storage Backends
status: Proposed
date: 2026-02-24
context: Improving Separation of Concerns and Resource Isolation
---

# Delegate Workspace Initialization to Storage Backends

## Context and Problem Statement / コンテキスト

これまで `beautyspot` では、 Factory 関数 `Spot()` の初期化時において、デフォルトのキャッシュディレクトリ（`.beautyspot/`）の作成と `.gitignore` の配置を一律で行っていました。しかし、ユーザーがカスタムのパスを指定した場合でも、意図せずカレントディレクトリに `.beautyspot/` が作成されてしまうという課題がありました。また、コンポーネント（DB、ストレージ）が自身の永続化先の詳細を自己管理できておらず、関心の分離の観点で不完全な設計となっていました。

## Decision Drivers / 要求

* **Separation of Concerns**: コアロジックや Factory 関数を物理的なディレクトリ構造の詳細から解放し、純粋な依存性注入（DI）に専念させること。
* **Zero Side Effects**: ユーザーが指定していないパス（デフォルトパスなど）に対して、不要なディレクトリやファイルを生成しないこと。
* **Extensibility**: クラウドストレージなど、ローカルディレクトリを必要としないバックエンドの実装を容易にすること。

## Considered Options / 検討

* **Option 1**: Factory 関数 `Spot()` 内で、全てのコンポーネントの設定を読み取り、一括でディレクトリを作成する。
* **Option 2**: ワークスペースの初期化ロジックをコアから削除し、各バックエンドコンポーネントにその責務を委譲する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

`__init__.py` および `core.py` からワークスペース初期化ロジック（`_setup_workspace`）を完全に削除します。代わりに、ローカルファイルシステムに依存する各バックエンドコンポーネント（`LocalStorage` および `SQLiteTaskDB`）の初期化処理内で、自身が使用するディレクトリの作成と `.gitignore` の配置を行うように責務を委譲します。

## Consequences / 決定

* **Positive**:
    * ユーザーがカスタムパスを指定した際の挙動が直感的になり、クリーンなファイルシステムが保たれる。
    * 各コンポーネントが独立して動作可能になり、テストや単体利用が容易になる。
* **Negative**:
    * カスタムのローカルバックエンドを実装するユーザーは、必要に応じて自身でディレクトリ作成や `.gitignore` 配置のロジックを書く必要がある。
* **Mitigation**:
    * 抽象基底クラスの Docstring および実装ガイドにおいて、インフラ管理の責務について明記する。
