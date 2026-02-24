# exceptions

`beautyspot` が送出するすべての例外クラスを定義します。ユーザーは `BeautySpotError` を捕捉することで、ライブラリ起因のエラーを一括でハンドリングできます。

::: beautyspot.exceptions

## 例外の階層構造

`beautyspot` の例外は、発生の文脈に応じて以下のように階層化されています。

* **BeautySpotError**: すべての例外の基底クラス。
* **CacheCorruptedError**: キャッシュデータ（DBレコードまたはBlobファイル）の消失、読み取り不能、または論理的な破損が発生した際に送出されます。
* **SerializationError**: シリアライザーによるエンコードまたはデコードが失敗した際に送出されます。
* **ConfigurationError**: ユーザーの設定（無効な保持ポリシー、互換性のないストレージオプションなど）に論理的なエラーがある際に送出されます。
* **ValidationError**: メソッド呼び出し時の引数チェックやバリデーションエラー。
* **IncompatibleProviderError**: 注入された依存オブジェクト（Serializer, Storage, DBなど）が要求された機能を提供していない場合のエラー。


## 設計の意図

### 標準例外との親和性

`ValidationError` および `IncompatibleProviderError` は、Python標準の `ValueError` を継承しています。これにより、既存のコードで `except ValueError:` を使用してバリデーションエラーを捕捉している場合でも、コードを修正することなく `beautyspot` のエラーを適切に処理できます。

### 粒度の高いエラーハンドリング

設定ミス（`ConfigurationError`）とデータの破損（`CacheCorruptedError`）を明確に区別することで、アプリケーション側で「設定を修正して再起動すべきか」あるいは「キャッシュをクリアして再試行すべきか」といった回復戦略を立てやすくしています。

