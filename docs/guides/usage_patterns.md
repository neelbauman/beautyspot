# Usage Patterns

`beautyspot` は、関数のキャッシュ化を「いつ」行いたいか、また「どのように」実行したいかに応じて、柔軟な実行パターンを提供します。

## 1. Definition Time (`@spot.mark`)

**「この関数は常にキャッシュされるべきである」** という設計の場合に使用します。
主にアプリケーションのコアロジックや、データパイプラインの定義に適しています。

```python
import beautyspot as bs

# 1. Spot（実行コンテキスト）を定義
spot = bs.Spot("my_app")

# 2. 関数定義時にデコレータを付与
@spot.mark
def heavy_analysis(data):
    # ... 重い計算 ...
    return result

# 3. 呼び出すだけでキャッシュ機能が働く
result = heavy_analysis(input_data)

```

### 特徴

* **Persistent:** 関数が定義されている間、常にキャッシュ機構が有効になります。
* **Simple:** 呼び出し側のコードを変更する必要がありません。

---

## 2. Execution Time (`with spot.cached_run`)

既存の関数やサードパーティ製ライブラリの関数を、**特定のスコープ内でのみ**キャッシュ化して実行します。
v2.0 から推奨される、柔軟かつモダンな実行パターンです。

### 基本的な使い方 (Single Function)

`with` ブロック内でのみ、渡した関数が「キャッシュ機能付き」のラッパーに置き換わります。

```python
from external_lib import simulation
import beautyspot as bs

spot = bs.Spot("experiment")

# 単一の関数を渡すと、そのままラッパーが返ってきます
with spot.cached_run(simulation, version="test-v1") as sim:
    # IDEの型補完や静的解析も機能します
    results = [sim(x) for x in range(10)]

```

---

## 2.1 Function Identity (完全修飾名と衝突回避)

同名の関数が別モジュールや別クラスに存在する場合、**短い関数名 (`func_name`) だけでは衝突**します。  
`beautyspot` は内部で **完全修飾名 (`module.qualname`)** を保存し、保持期間や `--func` フィルタなどで優先的に使用します。

### 例: 同名関数が2つあるケース

```python
# package_a/tasks.py
def preprocess(x):
    return x * 2

# package_b/tasks.py
def preprocess(x):
    return x + 1
```

```python
import beautyspot as bs
from package_a.tasks import preprocess as preprocess_a
from package_b.tasks import preprocess as preprocess_b

spot = bs.Spot("my_app")

with spot.cached_run(preprocess_a) as run_a:
    run_a(10)

with spot.cached_run(preprocess_b) as run_b:
    run_b(10)
```

このとき、DBに保存される `func_identifier` は以下のようになります。

* `package_a.tasks.preprocess`
* `package_b.tasks.preprocess`

### CLIフィルタでの指定

```bash
# 完全修飾名で正確に対象を絞る
beautyspot prune .beautyspot/my_app.db --days 30 --func package_a.tasks.preprocess
```

短い関数名も後方互換として使えますが、**同名関数がある場合は完全修飾名を推奨**します。

---

## 3. Parallel Execution (並列実行と共有フック)

`beautyspot` は、`ThreadPoolExecutor` などを用いた並列タスク実行をネイティブにサポートしています。
複数のスレッドから同じフックインスタンスを共有してメトリクス（進捗、トークン数など）を収集する場合、**`ThreadSafeHookBase`** を使用することで、競合状態（Race Condition）を防ぎつつ安全に集計を行えます。

### Thread-Safe な集計パターン

以下の例では、5つのスレッドで並列にタスクを実行し、共通のカウンタを安全に更新しています。

```python
import concurrent.futures
from beautyspot.hooks import ThreadSafeHookBase

class ConcurrentCounterHook(ThreadSafeHookBase):
    def __init__(self):
        super().__init__()  # ⚠️ 必須：内部ロックの初期化
        self.count = 0

    def on_cache_hit(self, context):
        self.count += 1  # ロックは自動適用されます

    def on_cache_miss(self, context):
        self.count += 1

counter = ConcurrentCounterHook()

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    # 複数のタスクに同じ counter インスタンスを渡す
    futures = [
        executor.submit(spot.cached_run(heavy_task, hooks=[counter]), i) 
        for i in range(20)
    ]
    concurrent.futures.wait(futures)

print(f"Total processed: {counter.count}")

```

---

## 4. コンテキストマネージャによる同期 (Flush)

`wait=False`（非同期保存）を使用している場合、アプリケーションが終了する前にバックグラウンドの保存処理を完了させる必要があります。`with spot:` ブロックは、**「溜まっている保存タスクをすべて完了させる同期ポイント（Flush）」** として機能します。

### 推奨されるパターン：バッチ処理の区切り

大量の並列処理やループ処理の後に `with` ブロックを抜けることで、全データの永続化を保証します。

```python
spot = bs.Spot("my_app", default_wait=False)

def run_experiment():
    with spot:
        # このブロック内の保存はバックグラウンドで行われる
        for i in range(100):
            process_data(i)
            
    # ブロックを抜ける際、未完了の保存タスクがすべて終わるまで待機します
    # ここに来た時点で、100件すべてのキャッシュがストレージに書き込まれています

```
