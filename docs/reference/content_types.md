# content_types

`beautyspot.content_types` モジュールは、キャッシュされたデータの種類を分類・識別するための定義と、自動推論ロジックを提供します。これにより、ダッシュボード等での適切なレンダリングが可能になります。

::: beautyspot.content_types

## 設計思想：データの「意味」の保持

`beautyspot` では、すべてのデータは `MsgpackSerializer` によってバイナリとして保存されますが、それと同時に「それが何であるか」という `ContentType` を記録します。

* **ストレージ層**: 効率的なバイナリ保存。
* **プレゼンテーション層**: `ContentType` に基づいた最適な表示（テキスト、表、画像など）。

## ContentType クラス (Enum)

利用可能なコンテンツタイプは以下の通りです。

| 定数 | 説明 | 判定条件の例 |
| --- | --- | --- |
| `TEXT` | プレーンテキスト | `str` 型 |
| `JSON` | 構造化データ | `dict`, `list` 型 |
| `IMAGE` | 画像データ | `PIL.Image` オブジェクト、または特定のバイナリシグネチャ |
| `DATAFRAME` | 表形式データ | `pandas.DataFrame`, `polars.DataFrame` |
| `NUMERIC` | 数値データ | `int`, `float`, `numpy.number` |
| `BINARY` | 汎用バイナリ | 上記以外、または `bytes` 型 |

## 自動推論と明示的指定

### 自動推論 (`infer_content_type`)

`core.py` において、関数の実行結果が返された際、`beautyspot` はそのオブジェクトの型やプロパティをスキャンして `ContentType` を自動的に決定します。

### 明示的なヒント

自動推論が困難な場合や、特定の表示を強制したい場合は、`@spot.mark()` の引数でヒントを与えることができます。

```python
@spot.mark(content_type="image/png")
def generate_plot():
    ...

```

## ダッシュボードでの利用 (`dashboard.py`)

`dashboard.py` は、保存された `ContentType` を参照してレンダリング戦略を選択します。

* **`JSON` の場合**: ツリー形式で展開可能なビューを表示。
* **`DATAFRAME` の場合**: インタラクティブなテーブルを表示。
* **`IMAGE` の場合**: バイナリをデコードし、プレビュー画像をインライン表示。

