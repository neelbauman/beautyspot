---
title: Database Dependency Injection and Abstraction
status: Accepted
date: 2025-12-03
context: v1.0.0 Release Preparation
---

# Database Dependency Injection and Abstraction

## Context and Problem Statement / コンテキスト

これまでの `beautyspot` (`v0.x`) は、`Project` クラス内部で `TaskDB` (SQLite実装) をハードコードしてインスタンス化していた。

```python
# v0.x implementation
self.db = TaskDB(self.db_path)
```

この設計には以下の課題がある：

1.  **拡張性の欠如:** SQLite 以外のデータベース（PostgreSQL, DuckDB, In-Memory DB等）を使いたくても、ライブラリのコードを書き換えない限り不可能である。
2.  **テストの制約:** ユニットテスト時に、ファイルシステムに依存しないモックDBやオンメモリDBへの差し替えが困難である。

v1.0.0 では、ユーザー体験（DX）としての「手軽さ（パスを指定するだけ）」を維持しつつ、アーキテクチャレベルでの柔軟性を確保する必要がある。

## Decision Drivers / 要求

  * **Extensibility:** ユーザーが独自の `TaskDB` 実装を注入 (Inject) できるようにする。
  * **Backward Compatibility / DX:** 従来通りファイルパス（文字列）を渡すだけの初期化もサポートし、ライトユーザーの負担を増やさない。
  * **Testability:** データベース層のモック化を容易にする。

## Decision Outcome / 決定

Chosen option: **Dependency Injection with Abstract Base Class**.

1.  **抽象化:** `src/beautyspot/db.py` に抽象基底クラス `TaskDB` を定義し、インターフェース（`save`, `get`, `init_schema` 等）を強制する。
2.  **具象化:** 従来のSQLite実装を `SQLiteTaskDB` として再定義する。
3.  **注入 (DI):** `Project` クラスのコンストラクタ引数を `db_path: str` から `db: Union[str, TaskDB]` に変更する。
      * `str` が渡された場合: 内部で `SQLiteTaskDB(path)` を生成する（Convenience）。
      * `TaskDB` が渡された場合: そのインスタンスをそのまま使用する（Injection）。

## Consequences / 結果

  * **Positive:**
      * PostgreSQL や MySQL などのアダプタをユーザー側で実装し、`Project(..., db=PostgresDB(...))` のように利用可能になる。
      * テスト時に `MemoryTaskDB` などを差し込むことで、高速かつクリーンなテストが可能になる。
  * **Negative:**
      * `db_path` 引数が廃止（または `db` に統合）されるため、既存コードの引数名変更が必要になる（v1.0.0 での破壊的変更）。


