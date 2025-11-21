---
title: Executor Lifecycle Management
status: Proposed
date: 2025-11-21
context: Issue3
---

# Manage Executor Lifecycle via Instance Ownership and Weak References

## Context and Problem Statement

`src/beautyspot/core.py` において、非同期タスクのIOオフロード用に `ThreadPoolExecutor` がグローバル変数 `_io_executor` として定義されている。

この実装には以下の課題がある：

1.  **リソース制御の欠如**: スレッド数（`max_workers=4`）がハードコードされており、ユーザーが実行環境（AWS Lambda、強力なサーバー等）に合わせて調整できない。
2.  **ゾンビプロセス**: プロセス終了時に明示的なシャットダウンが行われないため、環境によってはゾンビプロセス化するリスクがある。
3.  **テスト困難性**: グローバル変数はモック化が難しく、ユニットテストの分離を妨げる。

代替案として `with` 文（Context Manager）による管理も検討されたが、`beautyspot` の「デコレータを付与するだけで動作する」という簡易な利用体験（DX）を損なうため、採用には至らなかった。ユーザーコードを変更させずに、安全にリソースをクリーンアップする仕組みが必要である。

## Decision Drivers

  * **Developer Experience (DX)**: ユーザーに `shutdown()` の呼び出しや `with` 文を強制したくない。
  * **Configurability**: スレッド数や Executor の実装をユーザーが制御できるようにしたい。
  * **Safety**: プロセス終了時やインスタンス破棄時に、確実にスレッドプールを閉じたい。
  * **Memory Safety**: クリーンアップ処理の登録によって、メモリリーク（循環参照）を引き起こしてはならない。

## Considered Options

  * **Option 1**: 現状維持（グローバル変数のまま）。
  * **Option 2**: `Project` を Context Manager 化し、`__exit__` で `shutdown()` を呼ぶ。
  * **Option 3**: `atexit` モジュールを使い、終了時に `shutdown()` を呼ぶ。
  * **Option 4**: インスタンス管理に変更し、`weakref.finalize` で自動クリーンアップを行う。

## Decision Outcome

Chosen option: **Option 4**.

`Project` クラスの設計を以下のように変更する：

1.  **Executorのインスタンス化**:
    グローバル変数を廃止し、`Project` インスタンスごとに `ThreadPoolExecutor` を保持する。
2.  **Dependency Injection (DI)**:
    コンストラクタで外部 `Executor` の注入を許可する。
3.  **所有権と責任の分離**:
      * **外部注入 (`executor` 引数あり)**: `Project` はそれを借用するのみ。シャットダウンの責任はユーザー（呼び出し元）にあるため、自動クリーンアップは行わない。
      * **内部生成 (`executor` 引数なし)**: `Project` がライフサイクルを管理する責任を持つ。
4.  **自動クリーンアップ**:
    内部生成した場合に限り、`weakref.finalize` を使用してシャットダウンを自動化する。

### Technical Details: Why `weakref.finalize` instead of `atexit`?

単純な `atexit.register(self.shutdown)` を採用しなかった理由は、**メモリリーク（循環参照）のリスク** である。

  * **問題点**: `atexit` レジストリにインスタンスメソッド（`self.shutdown`）を登録すると、`atexit` が `self` への強参照（Strong Reference）を保持し続ける。これにより、アプリケーション実行中に `Project` インスタンスが不要になってもガベージコレクション（GC）されず、メモリリークを引き起こす。これを防ぐには `atexit.unregister` が必要になるが、管理が複雑になる。
  * **解決策**: `weakref.finalize(self, func, *args)` を採用する。
      * `self` がGCされた時点で、即座に `func`（クリーンアップ処理）が実行される。
      * プログラム終了時まで `self` が生存していた場合も、`atexit` 相当のタイミングで `func` が実行される。
      * **重要**: クリーンアップ関数 `_shutdown_executor` は `staticmethod` とし、引数には `self` ではなく `self.executor` のみを渡す。これにより、ファイナライザが `self` を参照し続けて寿命を延ばしてしまう事故を防ぐ。

```python
# Implementation Sketch
class Project:
    def __init__(self, ...):
        # ...
        self.executor = ThreadPoolExecutor(...)
        # self を参照しないよう、executor オブジェクトだけを渡す
        self._finalizer = weakref.finalize(self, self._shutdown_executor, self.executor)

    @staticmethod
    def _shutdown_executor(executor):
        executor.shutdown(wait=True)
```

## Consequences

  * **Positive**:
      * ユーザーはリソース管理を意識する必要がなくなり、APIもシンプルに保たれる。
      * `Project` インスタンスがGCされたタイミングでスレッドプールも回収されるため、リソース効率が良い。
      * DIにより、テスト時にモックExecutorを差し込むことが容易になる。
  * **Negative**:
      * `core.py` の実装において、GCの挙動と `weakref` の仕様を理解したコーディングが必要になり、内部的な複雑性が若干増す。
      * `Project` インスタンスを大量に生成・破棄するような特殊な使い方をした場合、スレッドプールの生成コストがオーバーヘッドになる可能性がある（ドキュメントでシングルトン的な利用を推奨することで緩和する）。

