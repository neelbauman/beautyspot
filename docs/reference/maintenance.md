# Maintenance Service

`MaintenanceService` は、`beautyspot` システムの管理・運用に特化したサービスレイヤーです。実行時のコアロジックを担う `Spot` クラスから分離されており、キャッシュデータのクリーンアップ、履歴の参照、不要な Blob ファイルの削除などの管理タスクを提供します。

::: beautyspot.maintenance

## 主な役割

- **履歴と詳細の取得**: 実行されたタスクの履歴一覧や、デコードされた実行結果の詳細を取得します。
- **キャッシュの管理**: 特定のキャッシュキーに基づくデータの削除（`delete_task`）や、特定の関数・期間に基づく一括削除（`prune`, `clear`）を行います。
- **ガベージコレクション**: データベースから参照されていない孤立した Blob ファイルをスキャンし、物理ストレージをクリーンアップします。

## 使用例

```python
from beautyspot.maintenance import MaintenanceService

# 既存の Spot インスタンスからコンポーネントを引き継いで初期化
service = MaintenanceService(spot.db, spot.storage, spot.serializer)

# 30日以上前の古いキャッシュを削除
service.prune(days=30)

# 参照されていない不要なファイルを削除
orphans = service.scan_garbage()
service.clean_garbage(orphans)
```
