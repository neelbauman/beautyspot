## 🔧 . Ad-hoc Type Registration (Per-Task Serializer)

特定のタスクでしか使わない特殊な型がある場合、グローバルな `spot` インスタンスに登録するのではなく、**そのタスク専用のシリアライザ** を作成して渡すことができます。
これにより、他のタスクへの副作用（汚染）を防ぎながら、柔軟な型登録が可能になります。

**Scenario:**
ある関数の中だけで、特殊なバイナリ形式を持つサードパーティ製オブジェクトを扱いたい。

```python
import beautyspot as bs
from beautyspot.serializer import MsgpackSerializer

spot = bs.Spot("my_workspace")

# 1. このタスク専用のシリアライザを作成
# (グローバルの spot.serializer とは独立しています)
local_serializer = MsgpackSerializer()

class MySpecialObject:
    def __init__(self, data):
        self.data = data

# 2. ローカルなシリアライザに型を登録
local_serializer.register(
    type_=MySpecialObject,
    code=100,  # このコード値はこのシリアライザ内でのみ有効です
    encoder=lambda obj: {"data": obj.data},
    decoder=lambda d: MySpecialObject(d["data"])
)

# 3. serializer 引数を使ってタスクに注入
@spot.mark(serializer=local_serializer)
def produce_special_object():
    return MySpecialObject(data="secret_payload")

# cached_run でも同様に使用可能です
with spot.cached_run(produce_special_object, serializer=local_serializer) as task:
    result = task()
```
