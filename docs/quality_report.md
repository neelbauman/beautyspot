# 📊 Beautyspot Quality Report
**最終更新:** 2026-02-16 23:19:45

## 1. アーキテクチャ可視化
### 1.1 依存関係図 (Pydeps)
![Dependency Graph](statics/img/generated/dependency_graph.png)

### 1.2 安定度分析 (Instability Analysis)
青: 安定(Core系) / 赤: 不安定(高依存系)。矢印は依存の方向を示します。
![Stability Graph](statics/img/generated/architecture_metrics.png)

<details>
<summary>🔍 安定度メトリクスの詳細（Ca/Ce/I）を表示</summary>

```text
Module          | Ca  | Ce  | I (Instability)
---------------------------------------------
_version        | 0   | 0   | 0.00
limiter         | 1   | 0   | 0.00
serializer      | 2   | 0   | 0.00
cachekey        | 1   | 0   | 0.00
storage         | 2   | 0   | 0.00
db              | 2   | 0   | 0.00
core            | 1   | 5   | 0.83
content_types   | 1   | 0   | 0.00
dashboard       | 0   | 2   | 1.00
maintenance     | 2   | 3   | 0.60
cli             | 0   | 2   | 1.00

Graph generated at: docs/statics/img/generated/architecture_metrics.png
```
</details>

## 2. コード品質メトリクス
### 2.1 循環的複雑度 (Cyclomatic Complexity)
#### ⚠️ 警告 (Rank C 以上)
複雑すぎてリファクタリングが推奨される箇所です。

```text
src/beautyspot/cachekey.py
    F 27:0 canonicalize - C
src/beautyspot/cli.py
    F 303:0 show_cmd - C
    F 551:0 prune_cmd - C
    F 381:0 stats_cmd - C

4 blocks (classes, functions, methods) analyzed.
Average complexity: C (11.5)
```

<details>
<summary>📄 すべての CC メトリクス一覧を表示</summary>

```text
src/beautyspot/limiter.py
    M 36:4 TokenBucket._consume_reservation - A
    C 8:0 TokenBucket - A
    M 20:4 TokenBucket.__init__ - A
    M 66:4 TokenBucket.consume - A
    M 84:4 TokenBucket.consume_async - A
src/beautyspot/serializer.py
    M 69:4 MsgpackSerializer._default_packer - B
    C 25:0 MsgpackSerializer - A
    M 146:4 MsgpackSerializer.dumps - A
    M 123:4 MsgpackSerializer._ext_hook - A
    M 167:4 MsgpackSerializer.loads - A
    C 7:0 SerializerProtocol - A
    M 39:4 MsgpackSerializer.register - A
    M 12:4 SerializerProtocol.dumps - A
    M 15:4 SerializerProtocol.loads - A
    C 19:0 SerializationError - A
    M 33:4 MsgpackSerializer.__init__ - A
src/beautyspot/cachekey.py
    F 27:0 canonicalize - C
    F 92:0 _ - B
    M 210:4 KeyGen.from_file_content - A
    C 189:0 KeyGen - A
    M 228:4 KeyGen._default - A
    F 15:0 _safe_sort_key - A
    F 68:0 _ - A
    F 78:0 _ - A
    F 85:0 _ - A
    C 139:0 KeyGenPolicy - A
    M 201:4 KeyGen.from_path_stat - A
    M 251:4 KeyGen.hash_items - A
    M 261:4 KeyGen.ignore - A
    M 276:4 KeyGen.file_content - A
    M 284:4 KeyGen.path_stat - A
    C 126:0 Strategy - A
    M 145:4 KeyGenPolicy.__init__ - A
    M 153:4 KeyGenPolicy.bind - A
    M 269:4 KeyGen.map - A
src/beautyspot/storage.py
    M 69:4 LocalStorage._validate_key - A
    M 120:4 S3Storage.__init__ - A
    C 64:0 LocalStorage - A
    M 88:4 LocalStorage.load - A
    M 110:4 LocalStorage.list_keys - A
    C 119:0 S3Storage - A
    M 156:4 S3Storage.list_keys - A
    F 164:0 create_storage - A
    C 26:0 BlobStorageBase - A
    M 104:4 LocalStorage.delete - A
    M 141:4 S3Storage.load - A
    M 149:4 S3Storage.delete - A
    C 20:0 CacheCorruptedError - A
    M 32:4 BlobStorageBase.save - A
    M 40:4 BlobStorageBase.load - A
    M 47:4 BlobStorageBase.delete - A
    M 55:4 BlobStorageBase.list_keys - A
    M 65:4 LocalStorage.__init__ - A
    M 76:4 LocalStorage.save - A
    M 135:4 S3Storage.save - A
src/beautyspot/db.py
    M 91:4 SQLiteTaskDB.init_schema - A
    M 201:4 SQLiteTaskDB.get_outdated_tasks - A
    M 219:4 SQLiteTaskDB.get_blob_refs - A
    C 80:0 SQLiteTaskDB - A
    M 162:4 SQLiteTaskDB.get_history - A
    C 24:0 TaskDB - A
    M 118:4 SQLiteTaskDB.get - A
    M 186:4 SQLiteTaskDB.prune - A
    C 18:0 TaskRecord - A
    M 30:4 TaskDB.init_schema - A
    M 34:4 TaskDB.get - A
    M 38:4 TaskDB.save - A
    M 52:4 TaskDB.get_history - A
    M 56:4 TaskDB.delete - A
    M 61:4 TaskDB.prune - A
    M 68:4 TaskDB.get_outdated_tasks - A
    M 75:4 TaskDB.get_blob_refs - A
    M 85:4 SQLiteTaskDB.__init__ - A
    M 88:4 SQLiteTaskDB._connect - A
    M 132:4 SQLiteTaskDB.save - A
    M 181:4 SQLiteTaskDB.delete - A
src/beautyspot/core.py
    M 372:4 Spot._check_cache_sync - B
    M 489:4 Spot.mark - B
    M 200:4 Spot._resolve_key_fn - A
    M 407:4 Spot._save_result_sync - A
    M 649:4 Spot.delete - A
    M 267:4 Spot._resolve_settings - A
    M 592:4 Spot.cached_run - A
    C 47:0 ScopedMark - A
    M 59:4 ScopedMark.__enter__ - A
    C 119:0 Spot - A
    M 176:4 Spot._setup_workspace - A
    M 190:4 Spot.shutdown - A
    M 227:4 Spot.register - A
    M 277:4 Spot._make_cache_key - A
    M 124:4 Spot.__init__ - A
    M 250:4 Spot.register_type - A
    M 298:4 Spot._execute_sync - A
    M 329:4 Spot._execute_async - A
    M 622:4 Spot.run - A
    M 53:4 ScopedMark.__init__ - A
    M 101:4 ScopedMark.__exit__ - A
    C 106:0 SpotOptions - A
    M 187:4 Spot._shutdown_executor - A
    M 194:4 Spot.__enter__ - A
    M 197:4 Spot.__exit__ - A
    M 454:4 Spot.limiter - A
    M 475:4 Spot.mark - A
    M 478:4 Spot.mark - A
    M 567:4 Spot.cached_run - A
    M 581:4 Spot.cached_run - A
src/beautyspot/content_types.py
    C 3:0 ContentType - A
src/beautyspot/dashboard.py
    F 53:0 load_data - A
    F 14:0 get_args - A
    F 34:0 render_mermaid - A
src/beautyspot/__init__.py
    F 24:0 Spot - A
src/beautyspot/maintenance.py
    M 67:4 MaintenanceService.get_task_detail - B
    M 101:4 MaintenanceService.delete_task - A
    M 153:4 MaintenanceService.clean_garbage - A
    C 16:0 MaintenanceService - A
    M 141:4 MaintenanceService.scan_garbage - A
    M 27:4 MaintenanceService.from_path - A
    M 21:4 MaintenanceService.__init__ - A
    M 63:4 MaintenanceService.get_history - A
    M 123:4 MaintenanceService.get_prunable_tasks - A
    M 127:4 MaintenanceService.prune - A
    M 134:4 MaintenanceService.clear - A
src/beautyspot/cli.py
    F 303:0 show_cmd - C
    F 551:0 prune_cmd - C
    F 381:0 stats_cmd - C
    F 162:0 _list_tasks - B
    F 215:0 ui_cmd - B
    F 478:0 clean_cmd - B
    F 102:0 _list_databases - A
    F 447:0 clear_cmd - A
    F 49:0 _find_available_port - A
    F 59:0 _format_size - A
    F 33:0 get_service - A
    F 72:0 _get_task_count - A
    F 285:0 list_cmd - A
    F 646:0 version_cmd - A
    F 44:0 _is_port_in_use - A
    F 67:0 _format_timestamp - A
    F 665:0 main - A

139 blocks (classes, functions, methods) analyzed.
Average complexity: A (2.7553956834532376)
```
</details>

### 2.2 保守性指数 (Maintainability Index)
#### ⚠️ 警告 (Rank B 以下)
コードの読みやすさ・保守しやすさに改善の余地があるモジュールです。

```text
なし（すべて Rank A です ✨）
```

<details>
<summary>📄 すべての MI メトリクス一覧を表示</summary>

```text
src/beautyspot/_version.py - A
src/beautyspot/limiter.py - A
src/beautyspot/serializer.py - A
src/beautyspot/cachekey.py - A
src/beautyspot/storage.py - A
src/beautyspot/db.py - A
src/beautyspot/core.py - A
src/beautyspot/content_types.py - A
src/beautyspot/dashboard.py - A
src/beautyspot/__init__.py - A
src/beautyspot/maintenance.py - A
src/beautyspot/cli.py - A
```
</details>

## 4. デザイン・インテント分析 (Design Intent Map)
クラス図には現れない、生成関係、静的利用、および Protocol への暗黙的な準拠を可視化します。

```mermaid
graph LR
    classDef protocol fill:#f9f,stroke:#333,stroke-width:2px;
    class SerializerProtocol protocol;
    KeyGen -- "creates" --> KeyGenPolicy
    KeyGen -- "creates" --> ValueError
    KeyGenPolicy -. "uses" .-> KeyGen.from_file_content
    KeyGenPolicy -. "uses" .-> KeyGen.from_path_stat
    KeyGenPolicy -. "uses" .-> KeyGen.hash_items
    LocalStorage -- "creates" --> FileNotFoundError
    LocalStorage -- "creates" --> Path
    LocalStorage -- "creates" --> ValueError
    MaintenanceService -- "creates" --> MsgpackSerializer
    MaintenanceService -- "creates" --> Path
    MaintenanceService -- "creates" --> SQLiteTaskDB
    MsgpackSerializer -- "creates" --> SerializationError
    MsgpackSerializer -. "implements" .-> SerializerProtocol
    MsgpackSerializer -- "creates" --> ValueError
    S3Storage -- "creates" --> FileNotFoundError
    S3Storage -- "creates" --> ImportError
    SQLiteTaskDB -- "creates" --> ImportError
    SQLiteTaskDB -- "creates" --> Path
    ScopedMark -- "creates" --> RuntimeError
    Spot -. "uses" .-> KeyGen._default
    Spot -- "creates" --> NotImplementedError
    Spot -- "creates" --> Path
    Spot -- "creates" --> ScopedMark
    Spot -- "creates" --> ThreadPoolExecutor
    Spot -- "creates" --> TokenBucket
    Spot -- "creates" --> TypeError
    Spot -- "creates" --> ValueError
    TokenBucket -- "creates" --> ValueError
```
