# 🔌 Hooks 

`beautyspot` は「あなたのビジネスロジックを汚さない」という強い哲学（The Kuroko Pattern）を持っています。

キャッシュヒット率の計測、LLMのトークン消費量の計算、あるいは関数の実行時間（レイテンシ）のロギングなどを行いたい場合、関数の内側にそれらのコードを書くべきではありません。

v2.0 で導入された **Hooks（フック）システム** を使用すると、実行パイプラインの特定のタイミングに独自のクラスベース・プラグインを差し込み、関数の外側からエレガントにメトリクスを収集できます。

---

## 🏗 基本的な使い方

フックを作成するには、`beautyspot.hooks.HookBase` を継承したクラスを定義し、必要なメソッド（タイミング）だけをオーバーライドします。

作成したインスタンスは、`@spot.mark` または `spot.cached_run` の `hooks` 引数にリストとして渡します。

```python
import time
import beautyspot as bs
from beautyspot.hooks import HookBase

# 1. カスタムフックの定義
class ExecutionTimerHook(HookBase):
    def pre_execute(self, context):
        # 実行前のタイミングで開始時間を記録
        self.start_time = time.time()

    def on_cache_miss(self, context):
        # キャッシュミス＝実際に元関数が実行された直後のタイミング
        elapsed = time.time() - self.start_time
        print(f"[{context.func_name}] 実関数の実行に {elapsed:.4f} 秒かかりました。")

    def on_cache_hit(self, context):
        # キャッシュがヒットしたタイミング
        print(f"[{context.func_name}] キャッシュから即座に復元しました！")

spot = bs.Spot("my_app")
timer_hook = ExecutionTimerHook()

# 2. フックの登録
@spot.mark(hooks=[timer_hook])
def heavy_task(data):
    time.sleep(2)
    return data * 2

```

---

## 🎯 フックのタイミングとコンテキスト

フックには3つのタイミングがあり、それぞれ利用できる情報（Context）が型安全に定義されています。

### 1. `pre_execute(self, context: PreExecuteContext)`

* **発火タイミング**: キャッシュの有無を確認する前、および関数が実行される直前。
* **主な用途**: 開始時間の記録、入力引数（`context.args`, `context.kwargs`）の長さやトークン数の事前計算、アクセスログの記録。
* **利用できるデータ**: `func_name`, `input_id`, `cache_key`, `args`, `kwargs`

### 2. `on_cache_hit(self, context: CacheHitContext)`

* **発火タイミング**: ストレージ（またはDB）からキャッシュが正常に取得され、元の関数実行がスキップされた直後。
* **主な用途**: 節約できたコスト（API料金やトークン数）の計算、キャッシュヒット率の計測。
* **利用できるデータ**: 上記に加え、復元された `result` と `version`。

### 3. `on_cache_miss(self, context: CacheMissContext)`

* **発火タイミング**: キャッシュが存在せず（または期限切れで）、実際に元の関数が実行され、結果が得られた直後。
* **主な用途**: 実際に消費したコストの計算、実行時間の計測、外部の監視基盤（Datadog等）へのメトリクス送信。
* **利用できるデータ**: 上記に加え、新たに生成された `result` と `version`。

---

## 💡 実践レシピ：LLMのトークン節約トラッカー

クラスベースのフックの最大の強みは、**「状態（State）を保持できること」**です。
複数のタスクを横断して、累計の消費トークンや節約トークンをトラッキングする実践的な例です。

```python
from beautyspot.hooks import HookBase

class LLMTokenTracker(HookBase):
    def __init__(self):
        self.total_consumed = 0
        self.total_saved = 0

    def on_cache_miss(self, context):
        # 実際には tiktoken 等で厳密に計算します
        tokens = len(str(context.result)) // 4 
        self.total_consumed += tokens

    def on_cache_hit(self, context):
        tokens = len(str(context.result)) // 4
        self.total_saved += tokens

    def print_report(self):
        print(f"📊 トークンレポート:")
        print(f"  - 累計消費: {self.total_consumed}")
        print(f"  - 累計節約: {self.total_saved} (キャッシュ効果)")

# グローバルなトラッカーインスタンスを作成
tracker = LLMTokenTracker()

@spot.mark(hooks=[tracker])
def call_openai_api(prompt):
    ...

@spot.mark(hooks=[tracker])
def call_anthropic_api(prompt):
    ...

# アプリケーションの終了時にレポートを出力
tracker.print_report()

```

---

## 🔒 スレッドセーフなフック

`HookBase` はスレッドセーフではありません。**同一フックインスタンスを複数のスレッドが同時に呼び出す可能性がある場合**（例：`ThreadPoolExecutor` で並列タスクを実行し、共有のカウンタを持つフックを使う場合）は、`ThreadSafeHookBase` を使用してください。

```python
from beautyspot.hooks import ThreadSafeHookBase

class SharedMetricsHook(ThreadSafeHookBase):
    def __init__(self):
        super().__init__()   # ← threading.Lock を初期化するために必須
        self.hit_count = 0
        self.miss_count = 0

    def on_cache_hit(self, context):
        self.hit_count += 1   # ロックは自動適用される

    def on_cache_miss(self, context):
        self.miss_count += 1  # ロックは自動適用される
```

`HookBase` と **完全に同じメソッド名** をオーバーライドするだけです。
ロックは `__init_subclass__` の仕組みにより、サブクラス定義時に自動で適用されます。

!!! warning "super().__init__() を忘れずに"
    `ThreadSafeHookBase` を継承したクラスで `__init__` を定義する場合は、必ず `super().__init__()` を呼び出してください。呼び忘れると `threading.Lock` が初期化されず、`AttributeError` が発生します。

---

## ⚠️ 重要な設計と安全機構（Fail-Safe）

OSSツールとして、ユーザーのアプリケーションを落とさないための安全機構が備わっています。

* **No-Op by Default**: フックを指定しない場合、コンテキストオブジェクトの生成すら行われず、パフォーマンスへの影響（オーバーヘッド）はゼロです。
* **Fail-Safe Execution**: フック関数（`on_cache_hit` など）の内部でエラーや例外（例: ログ送信のネットワークエラー）が発生した場合、`beautyspot` はその例外をキャッチして内部ロガー（`logging.error`）に記録するだけで、**メインの関数の戻り値や実行自体はブロックしません。** これにより、些細なメトリクス収集のバグで本番環境のパイプラインが停止するのを防ぎます。

---

## 📚 API Reference

自動抽出されたクラスおよびメソッドの詳細仕様です。

::: beautyspot.hooks

