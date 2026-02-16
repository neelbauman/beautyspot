## ⚡ . Imperative Caching: `with cached_run`

ライブラリの関数や、ソースコードを変更できない関数を「その場限り」でキャッシュしたい場合に最適です。

**Scenario:**
シミュレーションライブラリ `simpy` の関数を実行したいが、パラメータが同じなら計算をスキップしたい。

```python
import beautyspot as bs
from external_lib import run_simulation  # 変更できない外部関数

spot = bs.Spot("simulation_env")

# コンテキスト内でのみ、run_simulation はキャッシュ機能を持つラッパーになります
# version="v1" を指定することで、将来ロジックが変わった時にキャッシュを無効化できます
with spot.cached_run(run_simulation, version="exp-v1") as cached_sim:
    
    # 1回目: 実行される (3秒)
    result1 = cached_sim(param_a=10, param_b=20)
    
    # 2回目: キャッシュから即座に返る (0秒)
    result2 = cached_sim(param_a=10, param_b=20)

print("Done!")

```
