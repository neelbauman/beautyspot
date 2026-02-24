# serializer

`beautyspot.serializer` モジュールは、計算結果やオブジェクトツリーを永続化可能なバイナリ形式に変換するための、安全で拡張可能なシリアライゼーション機構を提供します。

::: beautyspot.serializer

## プロトコル定義

`beautyspot` では、特定のクラスに依存しない疎結合な設計を維持するため、2つのプロトコルを定義しています。

### 1. SerializerProtocol

シリアライザーが実装すべき最小限のインターフェースです。

* `dumps(obj: Any) -> bytes`: オブジェクトをバイナリに変換します。
* `loads(data: bytes) -> Any`: バイナリをオブジェクトに復元します。

### 2. TypeRegistryProtocol

カスタム型の登録を受け入れるためのインターフェースです。

* `register(type_class, code, encoder, decoder)`: 特定の型に対して、一意の識別コード（0-127）と変換ロジックを紐付けます。

## MsgpackSerializer クラス

MessagePack をバックエンドに使用した、本ライブラリの標準シリアライザーです。

### 技術的特徴

* **スレッドセーフ設計**:
内部的な `threading.Lock` により、レジストリの更新、LRU キャッシュの操作、サブクラス解決が保護されています。これにより、バックグラウンドでの非同期保存中であっても安全に共有・利用が可能です。
* **知的なサブクラス解決**:
登録されていない型が渡された場合、そのクラスの MRO (Method Resolution Order) をスキャンして、登録済みの基底クラスが存在するかを確認します。
* **LRU キャッシュによる最適化**:
サブクラス解決の結果は内部でキャッシュされます。動的な型生成（namedtuples や Pydantic モデルなど）によるメモリ肥大化を防ぐため、最大サイズ（デフォルト 1024）を超えると古いエントリから自動的に破棄されます。

### カスタム型の登録手順

```python
from beautyspot.serializer import MsgpackSerializer

serializer = MsgpackSerializer()

# numpy.ndarray などを登録する例
serializer.register(
    type_class=MyCustomClass,
    code=10,  # 0-127 の一意な数値
    encoder=lambda obj: obj.to_dict(),
    decoder=lambda data: MyCustomClass.from_dict(data)
)

```

## 例外ハンドリング

シリアライズ過程で発生する問題は、すべて `beautyspot.exceptions.SerializationError` として集約されます。

* **エンコード失敗**: カスタムエンコーダ内で例外が発生した場合、原因となった型名と共に報告されます。
* **非シリアライズ型**: 登録されていない型をシリアライズしようとした場合、修正のヒント（`spot.register` の使用推奨）を含む詳細なメッセージが表示されます。
* **データ破損**: デコード時にデータが不整合な場合、キャッシュの破損（Corrupted）として扱われます。
