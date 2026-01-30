## Rate Limiting (GCRA)
`beautyspot` は、APIのレート制限（Rate Limit）を遵守するための高性能なリミッターを内蔵しています。

単純な time.sleep とは異なり、GCRA (Generic Cell Rate Algorithm) を採用しているため、バースト（一時的な集中アクセス）を許容しつつ、長期的には指定されたレートを守るという、滑らかな制御が可能です。

### 基本的な使い方

#### 1. Spot でレートを定義する

Spot の初期化時に tpm (Tokens Per Minute) を設定します。
これが「1分間に許可される最大コスト」になります。

```
# 1分間に 60 トークンまで許可（≒ 1秒に1回）
spot = bs.Spot("api_client", tpm=60)
```

#### 2. 関数にコストを設定する
`@spot.limiter`  デコレータを使用して、その関数を実行するのに必要な「コスト（トークン消費量）」を定義します。

```
@spot.mark
@spot.limiter(cost=1)  # 1回の実行で1トークン消費
def call_api_endpoint_a():
    ...

@spot.mark
@spot.limiter(cost=5)  # 重いエンドポイントは5トークン消費
def call_heavy_endpoint():
    ...
```

上記の例では、 `call_api_endpoint_a ` なら毎分60回実行できますが、 `call_heavy_endpoint ` は毎分12回しか実行できません。

制限を超えた場合、関数は自動的にスリープ（ブロック）して、トークンが補充されるのを待ちます。


### 動的なコスト設定

引数に応じて消費コストを変えたい場合、cost 引数に関数を渡すことができます。

```
def calculate_cost(text_list):
    # テキスト1つにつき1コスト消費
    return len(text_list)

@spot.mark
@spot.limiter(cost=calculate_cost)
def batch_process(text_list):
    ...
```

### 非同期処理 (Async)

`async ` 関数に対しても、同様に動作します。

この場合、スレッドをブロックするのではなく、非同期に `await asyncio.sleep(...)` します。

```
@spot.mark
@spot.limiter(cost=1)
async def fetch_data():
    # レート制限にかかった場合、ここで非同期に待機します
    await client.get(...)
```

### 理論的背景: GCRA

`beautyspot` のリミッターは「リーキーバケツ（Leaky Bucket）」の一種である GCRA アルゴリズムを使用しています。

- **メモリ効率**: カウンタを保持する必要がなく、到着予定時刻（TAT）という単一のタイムスタンプのみで管理するため非常に軽量です。
- **公平性**: 全てのリクエストに対して公平に遅延を分配します。

