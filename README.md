![beautyspot_logo](docs/statics/img/beautyspot_logo_with_typo_1.jpeg)

# beautyspot

* [公式ドキュメント](https://neelbauman.github.io/beautyspot/)
* [PyPI](https://pypi.org/project/beautyspot/)
* [ライセンス](https://opensource.org/licenses/MIT)

---

`beautyspot` は、Python 関数の実行結果を透過的にキャッシュし、複雑なデータパイプラインや実験の再実行を高速化するための OSS ライブラリです。

生成AIの呼び出しや重い計算処理を行う際、API制限の管理、データの永続化、エラーからのリカバリなどを自前で実装するのは大変です。`beautyspot` は、あなたの関数の「黒子（くろこ）」として振る舞い、これらのインフラ制御をすべて引き受けます。あなたは「純粋なロジック」を書くことだけに集中できます。

## 📦 Installation

```bash
uv add beautyspot
# or
pip install beautyspot
```

## ✨ Key Features

* **Non-blocking Caching**: キャッシュの保存処理をバックグラウンドスレッドにオフロードし、メインの関数の応答速度（レイテンシ）を劇的に向上させます。
* **Dependency Injection (DI)**: DB（SQLite/Redis等）、ストレージ（Local/S3等）、シリアライザを自由に入れ替え可能な柔軟なアーキテクチャ。
* **Smart Lifecycle Management**: `with` ブロック（コンテキストマネージャ）を使用することで、バックグラウンドの保存タスクの完了を確実に同期し、データロストを防ぎます。
* **Rate Limiting (GCRA)**: APIコールなどの実行頻度を、厳密なトークンバケットアルゴリズムで制御します。
* **Extensible Hooks**: 実行前、キャッシュヒットやミス時に介入できるクラスベースのフックシステム。関数のロジックを汚すことなく、LLMのトークン消費量や実行時間の計測メトリクスを収集できます。
* **Automated Garbage Collection**: 確率的エビクション（Probabilistic Auto-Eviction）により、メインスレッドのレイテンシを一切犠牲にすることなく、ストレージの肥大化を自動的に防ぎます。

## 🚀 Quick Start

v2.0 からは `Spot` インスタンスに依存コンポーネントを注入して使用する設計になりました。

```python
import beautyspot as bs

# 1. Spot の初期化
# default_wait=False を指定すると、保存を待たずに即座に結果を返します
spot = bs.Spot(
    name="my_app",
    default_wait=False
)

# 2. タスクの登録（Marking）
@spot.mark(version="v1")
def heavy_computation(x: int):
    # 重い処理やAPIコール...
    return x * 10

# 3. 実行と同期
with spot:
    # 1回目の呼び出し（実際に実行され、裏でキャッシュが保存される）
    result1 = heavy_computation(5) 
    
    # 2回目の呼び出し（キャッシュから即座に返却される）
    result2 = heavy_computation(5)
    
    # ブロックを抜ける際、未完了のバックグラウンド保存タスクが完了するのを待機（Flush）します


```

## 🔌 Advanced: Tracking LLM Tokens with Hooks

LLMアプリにおいて、キャッシュでどれだけのトークンを節約できたかを知ることは重要です。フックシステムを使えば、簡単に計測できます。

```python
from beautyspot.hooks import HookBase

class TokenTracker(HookBase):
    def __init__(self):
        self.saved_tokens = 0

    def on_cache_hit(self, context):
        # キャッシュヒット時に節約できたトークン（文字数）をカウント
        self.saved_tokens += len(context.result)
        print(f"Total saved: {self.saved_tokens} tokens")

@spot.mark(hooks=[TokenTracker()])
def call_llm(prompt: str):
    return "AI response..."


```

## 🛠 Maintenance Service & Auto Eviction

キャッシュの削除やクリーンアップは、手動で行うことも、バックグラウンドで自動化することも可能です。

```python
import beautyspot as bs
from beautyspot.maintenance import MaintenanceService

# 1. 自動エビクション (Spot初期化時に 1% の確率で自動掃除を設定)
spot = bs.Spot("my_app", eviction_rate=0.01)

# 2. 手動メンテナンス (バッチスクリプト等で明示的に実行する場合)
admin = MaintenanceService(spot.db, spot.storage, spot.serializer)
# 期限切れデータや孤立したファイルを一括削除
deleted_db, deleted_blob = admin.clean_garbage()

# 古いキャッシュや特定のキーを個別に削除
admin.delete_task(cache_key="...")

```

## ⚠️ Migration Guide (v1.x -> v2.0)

v2.0 は破壊的変更を含むメジャーアップデートです。

* **`Project` -> `Spot**`: クラス名が変更されました。
* **`@task` -> `@mark**`: デコレータ名が変更されました。
* **`run()` メソッドの廃止**: 今後は `@mark` または `cached_run()` を使用してください。

## 🗺️ What's Next? (Roadmap)

現在、`beautyspot` の開発チームは以下の課題と機能拡張に取り組んでいます。コントリビューションも大歓迎です！

1. **Declarative Configuration**:
`Spot.from_profile("local-dev")` のように、`beautyspot.yml` 等を用いたインフラ設定の宣言的な注入。
2. **Smart Content Negotiation**:
`@spot.mark(content_type="dataframe")` のように宣言するだけで、Pandas/Polars等の最適なシリアライザ（Parquet等）を自動選択する仕組み。
3. **Cache Tagging**:
タグベースでのキャッシュのグルーピングと一括無効化 (`spot.invalidate(tags=["experiment_A"])`)。
4. **Soft Dependency Strategy**:
PandasやNumPyなどのデータサイエンスライブラリのサポートを、コアの依存関係を増やさない「オプショナルな拡張機能 (`pip install beautyspot[data]`)」として提供するアーキテクチャの導入。

## 📖 Documentation

詳細なガイド、アーキテクチャの哲学、APIリファレンスについては、[公式ドキュメント](https://neelbauman.github.io/beautyspot/) を参照してください。

## 📄 License

This project is licensed under the MIT License。

