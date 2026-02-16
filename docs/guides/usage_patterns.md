# Usage Patterns

`beautyspot` は、関数のキャッシュ化を「いつ」行いたいかに応じて、主に2つのアプローチを提供します。

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
# version="v1" などのオプションは、このブロック内での実行にのみ適用されます
with spot.cached_run(simulation, version="test-v1") as sim:
    
    # ここでは sim(arg) はキャッシュ機能付きで実行されます
    # IDEの型補完や静的解析も（元の関数のシグネチャに従い）機能しやすくなります
    results = [sim(x) for x in range(10)]

# ブロックを抜けると、sim の効力は消えますが、
# spot 自体（DB接続やExecutor）は生きたままで、再利用可能です

```

### 複数の関数をまとめてキャッシュ (Multiple Functions)

複数の関数を渡すと、タプルとして受け取れます。指定したオプション（`version` など）は、渡したすべての関数に一律で適用されます。

```python
def task_a(x): ...
def task_b(x): ...

with spot.cached_run(task_a, task_b, save_blob=True) as (run_a, run_b):
    run_a(data)
    run_b(data)

```

!!! note "Smart Return Policy"
`cached_run` の戻り値は、渡された関数の数によって変化します：

```
* **引数が1つの場合:** `Wrapper` オブジェクトを単体で返します。（アンパック不要）
* **引数が複数の場合:** `(Wrapper, Wrapper, ...)` のタプルを返します。

```

---

## コンテキストマネージャによる同期 (Flush)

`wait=False` を使用している場合、アプリケーションが急に終了すると、バックグラウンドで走っている保存処理が中断されるリスクがあります。`beautyspot` の `with` ブロックは、**「溜まっている保存タスクをすべて完了させる同期ポイント（Flush）」** として機能します。

### 推奨されるパターン：バッチ処理の区切り

`Spot` インスタンスはグローバルに定義し、同期が必要な区切りで `with` を使用します。

```python
spot = Spot("my_app", default_wait=False)

def run_experiment():
    with spot:
        # このブロック内で行われる保存はすべてバックグラウンドで行われる
        for i in range(100):
            process_data(i)
            
    # with ブロックを抜ける際、未完了の保存タスクがすべて終わるまで待機する
    # ここに来た時点で、100件すべてのキャッシュがストレージに書き込まれていることが保証される
    
    # Spot インスタンスは再利用可能なため、次の処理でも使用可能
    process_summary()

```

> **Note:** `with spot:` を抜けても Executor はシャットダウンされません。インスタンスは引き続き再利用可能です。完全に終了させる場合は `spot.shutdown()` を呼び出してください。


