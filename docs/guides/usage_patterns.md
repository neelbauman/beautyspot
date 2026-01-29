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

## 3. Imperative Execution (Deprecated)

!!! warning "Deprecated: `spot.run`"
v1.x および v2.0初期にあった `spot.run(func, *args)` は、型安全性の問題により **非推奨 (Deprecated)** となりました。
将来のバージョンで削除される予定です。今後は `cached_run` を使用してください。

### Migration Guide

**Before (`spot.run`):**
引数の型チェックが効かず、オプション指定のために `_` プレフィックス付きの特殊なキーワード引数が必要でした。

```python
# 非推奨
result = spot.run(my_func, arg1, _version="v1")

```

**After (`cached_run`):**
標準的な関数呼び出しが可能になり、コードの意図も明確になります。

```python
# 推奨
with spot.cached_run(my_func, version="v1") as task:
    result = task(arg1)

```
