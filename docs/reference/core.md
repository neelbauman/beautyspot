# Spot (Core)

`Spot` クラスは `beautyspot` のメインエントリポイントです。関数のマーキング（登録）、キャッシュのルックアップ、および実行結果の永続化をオーケストレートします。

::: beautyspot.core

## 主なコンセプト

### 1. タスクの登録と実行

`@spot.mark` デコレータを使用、または `spot.cached_run()` で関数を登録することで、その関数は自動的にキャッシュ対応となります。入力引数に基づいて一意のキャッシュキーが生成され、同じ引数での呼び出しはストレージから結果を復元します。

### 2. 非ブロッキング保存 (Non-blocking Persistence)

v2.0 では、`Spot` 初期化時に `default_wait=False` を設定するか、`@mark(wait=False)` を指定することで、保存処理をバックグラウンドスレッドで実行できます。これにより、計算終了直後に制御がユーザーに戻り、I/O 待ちによる遅延が解消されます。

### 3. 同期ポイントとしての Flush

`with spot:` ブロック（コンテキストマネージャ）を使用すると、そのブロックを抜ける際に、実行中のすべてのバックグラウンド保存タスクの完了を待機（Flush）します。
これは、プログラムの終了前やバッチ処理の区切りでデータの整合性を保証するために重要です。

### 4. ライフサイクルフック (Lifecycle Hooks)

v2.0から、関数の実行パイプラインに介入できるクラスベースのフックシステム (`HookBase`) が導入されました。`@spot.mark(hooks=[...])` を指定することで、関数の実行前 (`pre_execute`)、キャッシュヒット時 (`on_cache_hit`)、キャッシュミス時 (`on_cache_miss`) にカスタムロジックを差し込めます。これにより、レイテンシ計測やAPIコスト計算などを容易に実装できます。

## 使用例

### 基本的なデコレータの使用

```python
@spot.mark(version="1.0", save_blob=True)
def heavy_task(data):
    # 重い処理
    return result


```

### 局所的なキャッシュ実行 (cached_run)

デコレートせずに関数を一時的にキャッシュ化したい場合に使用します。`with` ブロックを使うと変数スコープを明確にできますが、返されたラッパーはブロック外でも有効です。

```python
with spot.cached_run(my_func, version="v1") as task:
    result = task(arg)

# task はブロック外でも @spot.mark(version="v1") 相当のラッパーとして有効

```

### バックグラウンド保存の制御

```python
# 保存を待たずに即座に値を返す
@spot.mark(wait=False)
def async_save_task(x):
    return x * 10

with spot:
    async_save_task(1)
    async_save_task(2)
# ここを抜ける時に 1 と 2 の保存完了が保証される


```

### メトリクス収集フックの使用

```python
from beautyspot.hooks import HookBase

class MetricsHook(HookBase):
    def on_cache_miss(self, context):
        print(f"[{context.func_name}] 実関数が実行されました。")
    
    def on_cache_hit(self, context):
        print(f"[{context.func_name}] キャッシュが利用されました！")

@spot.mark(hooks=[MetricsHook()])
def fetch_data(query: str):
    return "Result"

```

## 関連コンポーネント

* **[CacheManager](cache.md)**: キャッシュのキー生成、読み書き、Thundering Herd対策などの内部ロジックを担当するコンポーネントです。

## 注意事項

* **シャットダウン**: `spot.shutdown()` を呼ぶと Executor が停止し、それ以降バックグラウンド保存は利用できなくなります。
* **スレッドセーフ**: 内部で `ThreadPoolExecutor` を使用しているため、注入される DB や Storage はスレッドセーフである必要があります。

## 動作フローチャート

### キャッシュヒットした場合（同期パス）

キャッシュにデータが存在する場合、バックグラウンドスレッドは関与せず、メインスレッド内で直接データの復元が行われます。

```mermaid
sequenceDiagram
    box rgb(255, 40, 40, 0.1) メインスレッド
        participant User as ユーザーコード
        participant UserFunc as markされた関数
        participant Spot as Spotインスタンス
        participant Cache as CacheManager
        participant Storage as DB / Storage
    end

    User->>UserFunc: 関数呼び出し (引数: args, kwargs)
    UserFunc->>Spot: キャッシュルックアップ要求
    
    Spot->>Cache: make_cache_key() (引数からハッシュキーを生成)
    Cache-->>Spot: cache_key, input_id

    Spot->>Spot: pre_execute フック発火

    Spot->>Cache: get(cache_key) (キャッシュの取得要求)
    Cache->>Storage: データの読み込み
    Storage-->>Cache: シリアライズされたデータ
    Cache->>Cache: デシリアライズ (復元)
    Cache-->>Spot: 復元されたオブジェクト

    Spot->>Spot: on_cache_hit フック発火
    
    Spot-->>UserFunc: キャッシュされた結果
    Note right of UserFunc: 実関数は実行されない
    UserFunc-->>User: 関数の実行結果
```

### キャッシュヒットしなかった場合（バックグラウンド保存）

```mermaid
sequenceDiagram
    participant OS as OS / atexit
    
    box rgb(255, 40, 40, 0.1) メインスレッド
        participant User as ユーザーコード<br/>(User Code)
        participant UserFunc as markされた関数<br/>(User Function)
        participant Spot as Spotインスタンス
    end
    
    participant BGLoop as BGLoopスレッド<br/>(_BackgroundLoop)
    participant Executor as ワーカースレッド<br/>(ThreadPoolExecutor)

    User->>Spot: Spot.__init__() (インスタンス初期化、リソースは未作成)
    Note right of User: バックグラウンドリソースは遅延初期化される

    User->>UserFunc: 関数呼び出し (デコレートされたラッパー経由)
    UserFunc->>Spot: Spot._execute_sync() (キャッシュルックアップ＆実行要求)
    
    Note right of Spot: キャッシュミス発生と仮定

    Spot->>Spot: Spot._persist_result_sync(save_sync=False) (結果の非同期保存処理を開始)
    Spot->>Spot: Spot._ensure_bg_resources() (バックグラウンド用スレッドの確保/生成)

    opt リソース未作成の場合（初回のみ）
        Spot->>BGLoop: _BackgroundLoop.__init__() (非同期IOを管理するイベントループスレッドを生成)
        activate BGLoop
        Note right of BGLoop: 内部で新しくイベントループを作成し<br/>asyncio.run_forever()を実行
        Spot->>Executor: ThreadPoolExecutor.__init__() (実際のIO処理を行うスレッドプールを生成)
        activate Executor
        Spot->>Spot: weakref.finalize(Spot._shutdown_resources) (プロセス強制終了時のリソース解放フックを登録)
    end

    Spot->>BGLoop: _BackgroundLoop.submit() (保存用コルーチンをイベントループに投入)
    Note right of Spot: _active_tasksカウンタを加算しインフライトタスクとして追跡
    BGLoop-->>Spot: asyncio.Future (イベントループ内でスケジュールされたタスクの参照)
    Spot->>Spot: Spot._track_future() (タスク完了をFlush等で待機できるようリストに追加)
    
    Spot-->>UserFunc: 戻り値 (保存完了を待たずに即座に返す)
    UserFunc-->>User: 関数の実行結果

    Note over BGLoop, Executor: --- バックグラウンド保存処理 ---

    BGLoop->>BGLoop: _BackgroundLoop._task_wrapper() (コルーチン実行開始・終了をフックしタスク状態を管理)
    BGLoop->>Executor: loop.run_in_executor() (同期的なDB/ストレージ保存関数をワーカースレッドに委譲)

    activate Executor
    Executor->>Executor: Spot._save_result_safe() (ファイルシステムやDBに対する実際のIO書き込みを実行)

    alt 保存成功
        Executor-->>BGLoop: 結果を返す (IO処理の正常完了を通知)
    else 例外発生
        Executor->>Spot: Spot._handle_save_error() (エラーのロギングとユーザーフックの実行)
        Note right of Executor: 例外は握り潰さずロギング＆<br/>on_background_errorフックを実行
        Executor-->>BGLoop: 処理完了を通知 (ワーカースレッド内の例外は上位イベントループに伝搬させない)
    end
    deactivate Executor

    BGLoop->>BGLoop: _BackgroundLoop._active_tasks を減算 (追跡カウンタを減らし、0になればシャットダウン可能か判定)

    Note over User, Executor: --- シャットダウン / 終了処理 ---

    alt ユーザーコードが明示的に終了する場合
        User->>Spot: Spot.shutdown(save_sync=True) (Spotの明示的な終了要求、未完了タスクを待機)
        Spot->>Spot: Spot._drain_futures() (登録済みFutureの完了をタイムアウト付きで同期待機)
        Spot->>BGLoop: _BackgroundLoop.stop(save_sync=True) (新規タスク受付を停止し、ループの終了を要求)
        
        BGLoop->>BGLoop: _BackgroundLoop._is_shutting_down = True (内部フラグを立てて新規タスクを拒否)
        Note right of User: Mainスレッドは最大 drain_timeout 秒間、<br/>BGLoopスレッドの完了を thread.join() で待機する

        alt 実行中のタスクが残っている場合
            BGLoop->>BGLoop: _BackgroundLoop._task_wrapper() のfinally内で<br/>loop.stop() を発行 (最後のタスク完了時にループを停止)
        else アクティブなタスクが0の場合
            BGLoop->>BGLoop: 即座に loop.stop() を発行 (待つタスクがないため即座にループを停止)
        end

        BGLoop-->>Spot: イベントループ停止 ＆ スレッド終了 (BGLoopスレッドの完全な停止)
        deactivate BGLoop

        Spot->>Executor: ThreadPoolExecutor.shutdown(wait=True) (ワーカースレッドプールへ完了待機と停止を指示)
        Executor-->>Spot: スレッドプール終了 (全ワーカーの停止)
        deactivate Executor

        Spot-->>User: シャットダウン完了 (全てのリソースが安全に解放された状態)

    else プロセス終了時 (atexit / weakref.finalize による自動終了)
        OS->>Spot: Spot._shutdown_resources() (終了フックからの強制クリーンアップ呼び出し)
        Note right of Spot: atexitまたはガベージコレクションによって発火
        Spot->>BGLoop: _BackgroundLoop.stop(save_sync=False) (同期待機せずに即座の停止を要求)
        
        BGLoop->>BGLoop: _BackgroundLoop._is_shutting_down = True (内部フラグを立てて新規タスクを拒否)
        BGLoop->>BGLoop: 即座に loop.stop() を発行 (実行中のタスクがあっても強制停止をスケジュール)
        
        Spot->>Executor: ThreadPoolExecutor.shutdown(wait=False, cancel_futures=True) (スレッドプールの即時停止と未実行タスクのキャンセル)
        
        Note right of OS: タイムアウトを待たずに即座にプロセスを終了し、OSがリソースを回収する
    end
```
