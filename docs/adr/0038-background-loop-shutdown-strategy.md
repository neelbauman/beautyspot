---
title: Background Loop Shutdown Strategy and Threading Model
status: Accepted
date: 2026-02-24
context: Ensuring Data Safety during Process Termination
---

# Background Loop Shutdown Strategy and Threading Model

## Context and Problem Statement / コンテキスト

バックグラウンドでの非同期 IO タスクを処理するイベントループにおいて、単純に `daemon=True` スレッドを使用すると、メインスレッド終了時にプロセスが即座に強制終了され、データ破損やキャッシュのロストが発生する危険がありました。一方で、`daemon=False` にして `atexit` で待機を試みるアプローチでは、タスクがハングした場合にプロセス全体が永遠に終了しなくなるデッドロックの罠が存在していました。

## Decision Drivers / 要求

* **Data Durability**: プロセス終了時に、インフライト（実行中）の IO タスクが確実に完了し、ディスクへ永続化されること。
* **Reliability**: タスクのスケジュールとシャットダウンの間の競合状態 (Race Condition) を排除すること。
* **Liveness**: ネットワーク障害等でタスクがスタックしても、一定時間後にプロセスが確実に終了し、ゾンビ化を防ぐこと。

## Considered Options / 検討

* **Option 1**: `daemon=False` スレッドを使用し、`atexit` で待機する。デッドロックやハングのリスクが高い。
* **Option 2**: `daemon=True` スレッドを維持しつつ、明示的なタスク追跡と猶予期間（Grace Period）付きの `atexit` ハンドラを実装する。

## Decision Outcome / 決定

Chosen option: **Option 2**.

真の耐障害性を持つ Graceful Shutdown を実現するため、以下のアーキテクチャを採用します。

1. **デーモンスレッドの維持**: スレッドは `daemon=True` で起動し、プロセス終了時の無限ハングを OS の力で防ぎます。
2. **明示的なタスク追跡とロック**: ロックとアクティブタスクカウンタを用いたステートマシンを導入し、`submit` 時と `atexit` 時の競合状態を完全に排除します。
3. **Grace Period（猶予期間）の導入**: `atexit` フック内でメインスレッドをブロックし、タイムアウト付き（デフォルト5秒）で `_thread.join()` を実行することで、IO タスクが完了するための猶予を与えます。

## Consequences / 決定

* **Positive**:
    * ユーザーが明示的な終了処理を意識せずとも、プロセス終了時に安全にデータが永続化される。
    * タスクが無限にスタックしても、タイムアウト後にプロセスが終了するため、アプリがハングアップしない。
* **Negative**:
    * プロセス終了時に、バックグラウンド処理が終わるまで最大 5 秒のブロックが発生する。
