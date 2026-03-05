---
title: Background Loop and Executor Shutdown Sequence
status: accepted
date: 2026-03-05
context: Addressing Race Conditions during Spot.shutdown()
---

# Background Loop and Executor Shutdown Sequence

## Context and Problem Statement / コンテキスト

`beautyspot` では、バックグラウンドでのI/Oタスク処理に専用のスレッド（`_BackgroundLoop`）と、ブロッキング操作を委譲する `ThreadPoolExecutor` の2つを組み合わせて使用しています。
`Spot.shutdown(save_sync=False)` またはプロセスのシャットダウン時に、これら2つのリソースを破棄する順序やタイミングの不整合が問題となりました。

具体的には、バックグラウンドループ内の非同期タスクが `run_in_executor` に依存している状態（I/O待ち）で、先に `Executor` が `cancel_futures=True` で強制終了されると、タスク側で予期せぬ `CancelledError` や `RuntimeError` が発生し、クラッシュやログのノイズ、正常な後処理（一時ファイルの削除やDB切断など）の阻害を引き起こすリスクがありました。

## Decision Drivers / 要求

* **Graceful Degradation**: 強制終了時（`save_sync=False`）であっても、システムがクラッシュせず、残存タスクが安全に破棄されること。
* **Correct Sequencing**: リソースの依存関係（Loop -> Executor）に基づいた適切なシャットダウン手順の確立。
* **Observability**: 意図的なキャンセルによるタスクのドロップが、ユーザーに適切に通知されること（エラーの握りつぶしを防ぐ）。

## Considered Options / 検討

* **Option 1**: Executorのシャットダウンを常にLoopの完全な終了（タイムアウトなし）まで遅延させる。 -> シャットダウンがブロックし続けるリスクがあり、フェイルファストの要件を満たせない。
* **Option 2**: LoopとExecutorのシャットダウン順序は維持しつつ、`run_in_executor` を呼び出すバックグラウンドタスク内で `CancelledError` および `RuntimeError` を明示的に捕捉・ハンドリングする。

## Decision Outcome / 決定

Chosen option: **Option 2**.

シャットダウン手順の順序自体（Loopの停止 -> Executorの停止）は論理的に正しいものの、強制停止（`save_sync=False` または Loop のドレインタイムアウト）時には、Executor内のタスクがキャンセルされることを前提とした防御的プログラミングを採用します。

具体的には、`_save_result_async` 内で `run_in_executor` を呼び出す際に `try...except (asyncio.CancelledError, RuntimeError)` ブロックを設け、シャットダウンによる強制キャンセルを安全に捕捉します。捕捉した場合は、`on_background_error` コールバックを呼び出すか、適切に警告を記録することで、クラッシュを防ぎつつ通知を行います。

## Consequences / 決定

* **Positive**:
  * 強制シャットダウン時にエラーによるクラッシュや未処理例外のログ洪水が発生しなくなる。
  * バックグラウンドタスクが安全に中断され、リソースリークを防ぐことができる。
* **Negative**:
  * 強制キャンセルされた保存タスクは破棄されるため、データロストの事実がログ（Warning）にのみ残る。これは `save_sync=False` による明示的な要求動作として許容される。
