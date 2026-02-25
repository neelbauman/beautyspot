---
title: Thread-Safe SQLite Connection Closing and Lock Management
status: Accepted
date: 2026-02-24
context: Balancing Thread Safety and Main Thread Liveness
---

# Thread-Safe SQLite Connection Closing and Lock Management

## Context and Problem Statement / コンテキスト

`beautyspot` の `SQLiteTaskDB` は、並行読み取り性能を高めるため、各スレッドごとに専用のコネクションを保持する設計となっています。シャットダウン時には WAL のチェックポイントを妨げないよう、これらの接続を一括で閉じようとしていましたが、以下の深刻な問題がありました。
1. **`check_same_thread` の制約**: 別スレッドから `close()` を呼ぶとエラーが発生する。
2. **クラッシュの危険性**: クエリ実行中に強制クローズされるとセグメンテーションフォールトを引き起こす。
3. **リカバリ時のデッドロック**: エラー発生時の再接続処理で、再帰的なロック取得によりハングする。
4. **GC 時のブロック**: ロック解放を待機する設計では、GC 時にメインスレッドがフリーズし、ADR-0045 の「GC 時は絶対にメインスレッドをブロックさせない」という原則に違反する。

## Decision Drivers / 要求

* **Thread Safety**: クエリ実行と接続クローズの競合を防ぎ、プロセスクラッシュを回避すること。
* **Liveness**: シャットダウンや GC の際、他のスレッドの状態に関わらずメインスレッドをフリーズさせないこと。
* **Deadlock Freedom**: エラーリカバリなどの再入的な処理においても、ハングアップしないこと。

## Considered Options / 検討

* **Option 1**: 単純なロックによる同期的なクローズ。デッドロックや GC 時のフリーズのリスクが高い。
* **Option 2**: 再入可能ロック (`RLock`) とノンブロッキングクローズ (`blocking=False`) を組み合わせたフェイルファストなクリーンアップ。

## Decision Outcome / 決定

Chosen option: **Option 2**.

相反する要件を解決するため、以下の機構を導入します。

1. **リエントラントロック (`threading.RLock`) の導入**: 同一スレッド内でのリカバリ処理によるデッドロックを防ぎます。
2. **安全なクローズの許可**: `check_same_thread=False` を指定し、別スレッドからのクローズを許可します。
3. **ノンブロッキング・クローズ機構 (Fail-fast Close)**: 
   - シャットダウンや GC 時の `close()` 呼び出しは、ロック取得を **ノンブロッキング (`blocking=False`)** で試行します。
   - 他のスレッドがクエリを実行中でロックを取得できなかった場合、**安全を最優先してクローズを諦め**、Python の自然な GC 管理に委ねます。

## Consequences / 決定

* **Positive**:
    * シャットダウン時に可能な限り接続が閉じられ、WAL のクリーンアップが機能する。
    * プロセスクラッシュやリカバリ時のデッドロックのリスクが排除された。
    * GC 時にメインスレッドがブロックされず、システムの安定性が向上した。
* **Trade-off**:
    * 他のスレッドがクエリ実行中の場合、コネクションの切断が Python の GC タイミングまで遅延する可能性がある。
