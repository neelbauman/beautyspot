# 📊 Beautyspot Quality Report
**最終更新:** 2026-02-24 14:16:25

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
limiter         | 1   | 0   | 0.00
exceptions      | 4   | 0   | 0.00
_version        | 0   | 0   | 0.00
types           | 2   | 0   | 0.00
content_types   | 2   | 0   | 0.00
cachekey        | 1   | 0   | 0.00
hooks           | 1   | 1   | 0.50
lifecycle       | 1   | 1   | 0.50
db              | 2   | 0   | 0.00
cli             | 0   | 1   | 1.00
dashboard       | 0   | 2   | 1.00
maintenance     | 3   | 3   | 0.50
serializer      | 2   | 1   | 0.33
storage         | 2   | 1   | 0.33
core            | 0   | 11  | 1.00

Graph generated at: docs/statics/img/generated/architecture_metrics.png
```
</details>

## 2. コード品質メトリクス
### 2.1 循環的複雑度 (Cyclomatic Complexity)
#### ⚠️ 警告 (Rank C 以上)
複雑すぎてリファクタリングが推奨される箇所です。

```text
src/beautyspot/cli.py
    F 304:0 show_cmd - C
    F 556:0 gc_cmd - C
    F 671:0 prune_cmd - C
src/beautyspot/maintenance.py
    M 185:4 MaintenanceService.clean_garbage - C

4 blocks (classes, functions, methods) analyzed.
Average complexity: C (14.25)
```

<details>
<summary>📄 すべての CC メトリクス一覧を表示</summary>

```text
src/beautyspot/limiter.py
    M 44:4 TokenBucket._consume_reservation - A
    C 16:0 TokenBucket - A
    C 10:0 LimiterProtocol - A
    M 28:4 TokenBucket.__init__ - A
    M 74:4 TokenBucket.consume - A
    M 92:4 TokenBucket.consume_async - A
    M 11:4 LimiterProtocol.consume - A
    M 13:4 LimiterProtocol.consume_async - A
src/beautyspot/exceptions.py
    C 4:0 BeautySpotError - A
    C 12:0 CacheCorruptedError - A
    C 19:0 SerializationError - A
    C 25:0 ConfigurationError - A
    C 32:0 ValidationError - A
    C 39:0 IncompatibleProviderError - A
src/beautyspot/types.py
    C 9:0 SaveErrorContext - A
    C 43:0 HookContextBase - A
    C 54:0 PreExecuteContext - A
    C 61:0 CacheHitContext - A
    C 69:0 CacheMissContext - A
src/beautyspot/content_types.py
    C 6:0 ContentType - A
src/beautyspot/cachekey.py
    F 126:0 _canonicalize_type - B
    F 64:0 canonicalize - B
    F 41:0 _canonicalize_instance - A
    M 272:4 KeyGen.from_file_content - A
    M 290:4 KeyGen._default - A
    F 53:0 _is_ndarray_like - A
    C 251:0 KeyGen - A
    M 322:4 KeyGen.hash_items - A
    F 20:0 _safe_sort_key - A
    F 91:0 _canonicalize_dict - A
    F 101:0 _canonicalize_sequence - A
    F 108:0 _canonicalize_set - A
    C 194:0 KeyGenPolicy - A
    M 263:4 KeyGen.from_path_stat - A
    M 339:4 KeyGen.ignore - A
    M 354:4 KeyGen.file_content - A
    M 362:4 KeyGen.path_stat - A
    F 36:0 _canonicalize_ndarray - A
    F 115:0 _canonicalize_enum - A
    F 169:4 _canonicalize_np_ndarray - A
    C 181:0 Strategy - A
    M 200:4 KeyGenPolicy.__init__ - A
    M 208:4 KeyGenPolicy.bind - A
    M 347:4 KeyGen.map - A
src/beautyspot/hooks.py
    C 44:0 ThreadSafeHookBase - A
    M 68:4 ThreadSafeHookBase.__init_subclass__ - A
    C 12:0 HookBase - A
    F 33:0 _wrap_with_lock - A
    M 23:4 HookBase.pre_execute - A
    M 26:4 HookBase.on_cache_hit - A
    M 29:4 HookBase.on_cache_miss - A
    M 74:4 ThreadSafeHookBase.__init__ - A
src/beautyspot/lifecycle.py
    F 14:0 parse_retention - B
    C 65:0 LifecyclePolicy - A
    M 73:4 LifecyclePolicy.resolve - A
    C 49:0 Retention - A
    C 56:0 Rule - A
    M 70:4 LifecyclePolicy.__init__ - A
    M 85:4 LifecyclePolicy.default - A
src/beautyspot/__init__.py
    F 45:0 Spot - B
src/beautyspot/db.py
    M 180:4 SQLiteTaskDB.get - B
    M 146:4 SQLiteTaskDB.init_schema - B
    M 297:4 SQLiteTaskDB.get_outdated_tasks - A
    M 328:4 SQLiteTaskDB.get_blob_refs - A
    F 20:0 _ensure_utc_isoformat - A
    C 107:0 SQLiteTaskDB - A
    M 248:4 SQLiteTaskDB.get_history - A
    M 339:4 SQLiteTaskDB.get_keys_start_with - A
    C 36:0 TaskDBBase - A
    M 117:4 SQLiteTaskDB._connect - A
    M 272:4 SQLiteTaskDB.delete_all - A
    M 282:4 SQLiteTaskDB.prune - A
    M 317:4 SQLiteTaskDB.delete_expired - A
    C 29:0 TaskRecord - A
    M 42:4 TaskDBBase.init_schema - A
    M 46:4 TaskDBBase.get - A
    M 52:4 TaskDBBase.save - A
    M 67:4 TaskDBBase.get_history - A
    M 71:4 TaskDBBase.delete - A
    M 75:4 TaskDBBase.delete_expired - A
    M 79:4 TaskDBBase.prune - A
    M 86:4 TaskDBBase.get_outdated_tasks - A
    M 94:4 TaskDBBase.get_blob_refs - A
    M 98:4 TaskDBBase.delete_all - A
    M 102:4 TaskDBBase.get_keys_start_with - A
    M 112:4 SQLiteTaskDB.__init__ - A
    M 135:4 SQLiteTaskDB._read_connect - A
    M 216:4 SQLiteTaskDB.save - A
    M 267:4 SQLiteTaskDB.delete - A
src/beautyspot/cli.py
    F 304:0 show_cmd - C
    F 556:0 gc_cmd - C
    F 671:0 prune_cmd - C
    F 395:0 stats_cmd - B
    F 150:0 _list_tasks - B
    F 216:0 ui_cmd - B
    F 480:0 clean_cmd - B
    F 90:0 _list_databases - A
    F 453:0 clear_cmd - A
    F 50:0 _find_available_port - A
    F 60:0 _format_size - A
    F 75:0 _get_task_count - A
    F 33:0 get_service - A
    F 286:0 list_cmd - A
    F 771:0 version_cmd - A
    F 45:0 _is_port_in_use - A
    F 68:0 _format_timestamp - A
    F 790:0 main - A
src/beautyspot/dashboard.py
    F 54:0 load_data - A
    F 14:0 get_args - A
    F 35:0 render_mermaid - A
src/beautyspot/maintenance.py
    M 185:4 MaintenanceService.clean_garbage - C
    M 84:4 MaintenanceService.get_task_detail - B
    M 32:4 MaintenanceService.from_path - A
    M 128:4 MaintenanceService.delete_task - A
    M 279:4 MaintenanceService.scan_orphan_projects - A
    C 18:0 MaintenanceService - A
    M 169:4 MaintenanceService.scan_garbage - A
    M 251:4 MaintenanceService.resolve_key_prefix - A
    M 299:4 MaintenanceService.delete_project_storage - A
    M 23:4 MaintenanceService.__init__ - A
    M 80:4 MaintenanceService.get_history - A
    M 123:4 MaintenanceService.delete_expired_tasks - A
    M 150:4 MaintenanceService.get_prunable_tasks - A
    M 156:4 MaintenanceService.prune - A
    M 163:4 MaintenanceService.clear - A
src/beautyspot/serializer.py
    M 95:4 MsgpackSerializer._default_packer - B
    C 38:0 MsgpackSerializer - A
    M 160:4 MsgpackSerializer.dumps - A
    M 67:4 MsgpackSerializer.register - A
    M 147:4 MsgpackSerializer._ext_hook - A
    M 171:4 MsgpackSerializer.loads - A
    C 22:0 SerializerProtocol - A
    C 28:0 TypeRegistryProtocol - A
    M 85:4 MsgpackSerializer._enforce_cache_size - A
    M 23:4 SerializerProtocol.dumps - A
    M 24:4 SerializerProtocol.loads - A
    M 29:4 TypeRegistryProtocol.register - A
    M 56:4 MsgpackSerializer.__init__ - A
src/beautyspot/storage.py
    M 259:4 LocalStorage.prune_empty_dirs - B
    M 235:4 LocalStorage.clean_temp_files - B
    C 137:0 LocalStorage - A
    M 315:4 S3Storage._parse_s3_uri - A
    M 143:4 LocalStorage._validate_key - A
    M 176:4 LocalStorage.load - A
    M 197:4 LocalStorage.delete - A
    M 221:4 LocalStorage.list_keys - A
    C 298:0 S3Storage - A
    M 299:4 S3Storage.__init__ - A
    C 51:0 WarningOnlyPolicy - A
    M 150:4 LocalStorage.save - A
    M 348:4 S3Storage.list_keys - A
    F 356:0 create_storage - A
    C 28:0 StoragePolicyProtocol - A
    C 38:0 ThresholdStoragePolicy - A
    M 60:4 WarningOnlyPolicy.should_save_as_blob - A
    C 70:0 AlwaysBlobPolicy - A
    C 83:0 BlobStorageBase - A
    M 333:4 S3Storage.load - A
    M 341:4 S3Storage.delete - A
    M 34:4 StoragePolicyProtocol.should_save_as_blob - A
    M 46:4 ThresholdStoragePolicy.should_save_as_blob - A
    M 76:4 AlwaysBlobPolicy.should_save_as_blob - A
    M 89:4 BlobStorageBase.save - A
    M 97:4 BlobStorageBase.load - A
    M 104:4 BlobStorageBase.delete - A
    M 112:4 BlobStorageBase.list_keys - A
    M 120:4 BlobStorageBase.prune_empty_dirs - A
    M 128:4 BlobStorageBase.clean_temp_files - A
    M 138:4 LocalStorage.__init__ - A
    M 327:4 S3Storage.save - A
src/beautyspot/core.py
    M 795:4 Spot._check_cache_sync - B
    M 366:4 Spot.shutdown - B
    M 403:4 Spot._trigger_auto_eviction - B
    M 324:4 Spot._ensure_bg_resources - B
    M 1085:4 Spot.cached_run - B
    M 126:4 _BackgroundLoop.stop - A
    M 385:4 Spot._drain_futures - A
    M 444:4 Spot._resolve_key_fn - A
    M 843:4 Spot._submit_background_save - A
    C 160:0 Spot - A
    M 206:4 Spot.__init__ - A
    M 308:4 Spot.maintenance - A
    M 530:4 Spot._dispatch_hooks - A
    M 548:4 Spot._resolve_settings - A
    M 588:4 Spot._execute_sync - A
    M 687:4 Spot._execute_async - A
    M 868:4 Spot._save_result_safe - A
    M 902:4 Spot._save_result_sync - A
    C 64:0 _BackgroundLoop - A
    M 95:4 _BackgroundLoop._task_wrapper - A
    M 106:4 _BackgroundLoop.submit - A
    M 471:4 Spot.register - A
    M 512:4 Spot._calculate_expires_at - A
    M 567:4 Spot._make_cache_key - A
    M 986:4 Spot.mark - A
    M 294:4 Spot._track_future - A
    M 352:4 Spot._setup_workspace - A
    M 496:4 Spot.register_type - A
    M 70:4 _BackgroundLoop.__init__ - A
    M 87:4 _BackgroundLoop._run_event_loop - A
    M 152:4 _BackgroundLoop._shutdown - A
    M 283:4 Spot.__enter__ - A
    M 286:4 Spot.__exit__ - A
    M 361:4 Spot._shutdown_resources - A
    M 860:4 Spot._save_result_async - A
    M 948:4 Spot.consume - A
    M 969:4 Spot.mark - A
    M 972:4 Spot.mark - A
    M 1053:4 Spot.cached_run - A
    M 1070:4 Spot.cached_run - A

210 blocks (classes, functions, methods) analyzed.
Average complexity: A (2.9095238095238094)
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
src/beautyspot/limiter.py - A
src/beautyspot/exceptions.py - A
src/beautyspot/_version.py - A
src/beautyspot/types.py - A
src/beautyspot/content_types.py - A
src/beautyspot/cachekey.py - A
src/beautyspot/hooks.py - A
src/beautyspot/lifecycle.py - A
src/beautyspot/__init__.py - A
src/beautyspot/db.py - A
src/beautyspot/cli.py - A
src/beautyspot/dashboard.py - A
src/beautyspot/maintenance.py - A
src/beautyspot/serializer.py - A
src/beautyspot/storage.py - A
src/beautyspot/core.py - A
```
</details>

## 4. デザイン・インテント分析 (Design Intent Map)
クラス図には現れない、生成関係、静的利用、および Protocol への暗黙的な準拠を可視化します。

```mermaid
graph LR
    classDef protocol fill:#f9f,stroke:#333,stroke-width:2px;
    class LimiterProtocol protocol;
    class SerializerProtocol protocol;
    class TypeRegistryProtocol protocol;
    class StoragePolicyProtocol protocol;
    AlwaysBlobPolicy -. "implements" .-> StoragePolicyProtocol
    KeyGen -- "creates" --> KeyGenPolicy
    KeyGen -- "creates" --> ValueError
    KeyGenPolicy -. "uses" .-> KeyGen.from_file_content
    KeyGenPolicy -. "uses" .-> KeyGen.from_path_stat
    KeyGenPolicy -. "uses" .-> KeyGen.hash_items
    LocalStorage -- "creates" --> CacheCorruptedError
    LocalStorage -- "creates" --> Path
    LocalStorage -- "creates" --> ValidationError
    LocalStorage -- "creates" --> ValueError
    MaintenanceService -- "creates" --> MsgpackSerializer
    MaintenanceService -- "creates" --> Path
    MaintenanceService -- "creates" --> SQLiteTaskDB
    MsgpackSerializer -- "creates" --> OrderedDict
    MsgpackSerializer -- "creates" --> SerializationError
    MsgpackSerializer -. "implements" .-> SerializerProtocol
    MsgpackSerializer -. "implements" .-> TypeRegistryProtocol
    MsgpackSerializer -- "creates" --> ValueError
    S3Storage -- "creates" --> CacheCorruptedError
    S3Storage -- "creates" --> ImportError
    S3Storage -- "creates" --> ValidationError
    SQLiteTaskDB -- "creates" --> ImportError
    SQLiteTaskDB -- "creates" --> Path
    SQLiteTaskDB -- "creates" --> TaskRecord
    Spot -- "creates" --> CacheHitContext
    Spot -- "creates" --> CacheMissContext
    Spot -- "creates" --> IncompatibleProviderError
    Spot -. "uses" .-> KeyGen._default
    Spot -. "uses" .-> LifecyclePolicy.default
    Spot -. "implements" .-> LimiterProtocol
    Spot -- "creates" --> MaintenanceService
    Spot -- "creates" --> NotImplementedError
    Spot -- "creates" --> PreExecuteContext
    Spot -- "creates" --> RuntimeError
    Spot -- "creates" --> SaveErrorContext
    Spot -- "creates" --> ThreadPoolExecutor
    Spot -. "implements" .-> TypeRegistryProtocol
    Spot -- "creates" --> ValidationError
    Spot -- "creates" --> ValueError
    ThresholdStoragePolicy -. "implements" .-> StoragePolicyProtocol
    TokenBucket -. "implements" .-> LimiterProtocol
    TokenBucket -- "creates" --> ValueError
    WarningOnlyPolicy -. "implements" .-> StoragePolicyProtocol
```
