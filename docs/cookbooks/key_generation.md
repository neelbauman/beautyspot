## 🗝️ . Advanced Key Generation

引数のすべてが「計算結果」に影響するわけではありません。`KeyGen` を使って、「どの引数をキャッシュキーに含めるか」を精密に制御します。

**Case:**

* `verbose` フラグは結果に関係ないので無視したい (`IGNORE`)
* `config_path` はファイルの中身が変わったら再計算したい (`FILE_CONTENT`)

```python
from beautyspot.cachekey import KeyGen

# ポリシーの定義
key_policy = KeyGen.map(
    # 引数名 'verbose' と 'logger' はハッシュ計算から除外
    verbose=KeyGen.IGNORE,
    logger=KeyGen.IGNORE,
    
    # 引数名 'config_path' はファイルの中身を読んでハッシュ化
    config_path=KeyGen.FILE_CONTENT
)

@spot.mark(input_key_fn=key_policy)
def train_model(data, config_path, verbose=False, logger=None):
    if verbose:
        print("Training started...")
    # ...
    return model

```

