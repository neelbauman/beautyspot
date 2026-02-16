# Cache Key Generation

`beautyspot.cachekey` モジュールは、関数の引数（入力）から一意で安定した SHA-256 ハッシュ値を生成する役割を担います。

::: beautyspot.cachekey

## 設計思想

キャッシュキーの生成において、`beautyspot` は以下の 3 つを重視しています。

1. **安定性 (Stability)**: Python のデフォルトの `__repr__` に含まれるメモリアドレス（例: `<Object at 0x...>`）に依存せず、オブジェクトの内容に基づいたハッシュを生成します。
2. **正規化 (Canonicalization)**: 辞書のキー順序や集合（Set）の順序を固定し、論理的に同じ入力からは必ず同じハッシュが生成されるようにします。
3. **効率性**: バイナリデータ（Numpy 配列等）を扱う際、テキスト変換のオーバーヘッドを避けるため `msgpack` を利用したバイナリシリアライズを採用しています。

## 正規化の戦略 (`canonicalize`)

`canonicalize` 関数は、あらゆる Python オブジェクトをシリアライズ可能な安定した形式に再帰的に変換します。

* **プリミティブ型**: `int`, `float`, `str`, `bytes`, `bool`, `None` はそのまま保持されます。
* **コレクション**: `dict` はキーでソートされたリストに、`set` はソートされたリストに変換されます。
* **Numpy 配列**: `numpy` への依存を避けつつ、Duck Typing（`shape`, `dtype`, `tobytes` の確認）によって検知し、バイナリ情報を保持したままハッシュ化されます。これにより、巨大な配列の省略表示によるハッシュ衝突を防ぎます。
* **カスタムオブジェクト**: `__dict__` または `__slots__` をスキャンし、オブジェクトの構造を反映します。 Pydantic (v1/v2) モデルのスキーマ抽出もサポートしています。

## キー生成ポリシー (`KeyGenPolicy`)

特定の引数に対して、ハッシュ計算の方法をカスタマイズできます。

| 戦略 | 内容 |
| --- | --- |
| `DEFAULT` | オブジェクトを正規化してハッシュ化します。 |
| `IGNORE` | その引数をハッシュ計算から除外します（例: `verbose` フラグや `logger`）。 |
| `FILE_CONTENT` | 引数をファイルパスとみなし、**ファイルの中身**のハッシュを使用します。 |
| `PATH_STAT` | 引数をファイルパスとみなし、メタデータ（パス、サイズ、更新時刻）のハッシュを使用します（高速）。 |

### 使用例: ポリシーの適用

```python
from beautyspot.cachekey import KeyGen

# 'verbose' 引数を無視し、'input_path' はファイルの中身でハッシュ化する
policy = KeyGen.map(
    input_path=KeyGen.FILE_CONTENT,
    verbose=KeyGen.IGNORE,
)

@spot.mark(keygen=policy)
def process_file(input_path, verbose=False):
    ...

```

## 技術的な詳細

* **シリアライズ**: 正規化されたデータは `msgpack` を用いてバイト列に変換されます。
* **ハッシュアルゴリズム**: セキュリティ基準と衝突耐性を考慮し、`SHA-256` を採用しています（v1.x の MD5 から刷新されました）。

