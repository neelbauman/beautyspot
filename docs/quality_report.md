# 📊 Beautyspot Quality Report
**最終更新:** 2026-02-24 21:07:03

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
hooks           | 1   | 1   | 0.50
dashboard       | 0   | 2   | 1.00
serializer      | 2   | 1   | 0.33
storage         | 2   | 1   | 0.33
lifecycle       | 1   | 1   | 0.50
maintenance     | 3   | 3   | 0.50
cachekey        | 1   | 0   | 0.00
db              | 2   | 0   | 0.00
cli             | 0   | 1   | 1.00
core            | 0   | 11  | 1.00

Graph generated at: docs/statics/img/generated/architecture_metrics.png
```
</details>

## 2. コード品質メトリクス
### 2.1 循環的複雑度 (Cyclomatic Complexity)
#### ⚠️ 警告 (Rank C 以上)
複雑すぎてリファクタリングが推奨される箇所です。

```text
src/beautyspot/maintenance.py
    M 215:4 MaintenanceService.clean_garbage - C
src/beautyspot/cachekey.py
    F 176:0 _canonicalize_type - C
src/beautyspot/cli.py
    F 587:0 gc_cmd - D
    F 332:0 _show_cmd_inner - C
    F 155:0 _list_tasks_inner - C
    F 425:0 _stats_cmd_inner - C
    F 775:0 _prune_cmd_inner - C

7 blocks (classes, functions, methods) analyzed.
Average complexity: C (14.428571428571429)
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
src/beautyspot/hooks.py
    C 44:0 ThreadSafeHookBase - A
    M 68:4 ThreadSafeHookBase.__init_subclass__ - A
    C 12:0 HookBase - A
    F 33:0 _wrap_with_lock - A
    M 23:4 HookBase.pre_execute - A
    M 26:4 HookBase.on_cache_hit - A
    M 29:4 HookBase.on_cache_miss - A
    M 74:4 ThreadSafeHookBase.__init__ - A
src/beautyspot/dashboard.py
    F 54:0 load_data - A
    F 14:0 get_args - A
    F 35:0 render_mermaid - A
src/beautyspot/serializer.py
    M 94:4 MsgpackSerializer._default_packer - B
    C 38:0 MsgpackSerializer - A
    M 159:4 MsgpackSerializer.dumps - A
    M 67:4 MsgpackSerializer.register - A
    M 146:4 MsgpackSerializer._ext_hook - A
    M 170:4 MsgpackSerializer.loads - A
    C 22:0 SerializerProtocol - A
    C 28:0 TypeRegistryProtocol - A
    M 84:4 MsgpackSerializer._enforce_cache_size - A
    M 23:4 SerializerProtocol.dumps - A
    M 24:4 SerializerProtocol.loads - A
    M 29:4 TypeRegistryProtocol.register - A
    M 56:4 MsgpackSerializer.__init__ - A
src/beautyspot/__init__.py
    F 44:0 Spot - B
src/beautyspot/storage.py
    M 273:4 LocalStorage.prune_empty_dirs - B
    M 249:4 LocalStorage.clean_temp_files - B
    C 137:0 LocalStorage - A
    M 337:4 S3Storage._parse_s3_uri - A
    M 157:4 LocalStorage._validate_key - A
    M 190:4 LocalStorage.load - A
    M 211:4 LocalStorage.delete - A
    M 235:4 LocalStorage.list_keys - A
    C 320:0 S3Storage - A
    M 321:4 S3Storage.__init__ - A
    C 51:0 WarningOnlyPolicy - A
    M 144:4 LocalStorage._ensure_cache_dir - A
    M 164:4 LocalStorage.save - A
    M 372:4 S3Storage.list_keys - A
    F 380:0 create_storage - A
    C 28:0 StoragePolicyProtocol - A
    C 38:0 ThresholdStoragePolicy - A
    M 60:4 WarningOnlyPolicy.should_save_as_blob - A
    C 70:0 AlwaysBlobPolicy - A
    C 83:0 BlobStorageBase - A
    M 357:4 S3Storage.load - A
    M 365:4 S3Storage.delete - A
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
    M 349:4 S3Storage.save - A
src/beautyspot/lifecycle.py
    F 43:0 parse_retention - B
    M 127:4 LifecyclePolicy.resolve_with_fallback - A
    C 108:0 LifecyclePolicy - A
    M 116:4 LifecyclePolicy.resolve - A
    C 14:0 _ForeverSentinel - A
    M 24:4 _ForeverSentinel.__new__ - A
    M 29:4 _ForeverSentinel.__repr__ - A
    M 32:4 _ForeverSentinel.__bool__ - A
    C 82:0 Retention - A
    C 99:0 Rule - A
    M 113:4 LifecyclePolicy.__init__ - A
    M 145:4 LifecyclePolicy.default - A
src/beautyspot/maintenance.py
    M 215:4 MaintenanceService.clean_garbage - C
    M 187:4 MaintenanceService.scan_garbage - B
    M 102:4 MaintenanceService.get_task_detail - B
    M 48:4 MaintenanceService.from_path - A
    M 146:4 MaintenanceService.delete_task - A
    M 318:4 MaintenanceService.scan_orphan_projects - A
    C 18:0 MaintenanceService - A
    M 290:4 MaintenanceService.resolve_key_prefix - A
    M 338:4 MaintenanceService.delete_project_storage - A
    M 32:4 MaintenanceService.close - A
    M 23:4 MaintenanceService.__init__ - A
    M 41:4 MaintenanceService.__enter__ - A
    M 44:4 MaintenanceService.__exit__ - A
    M 98:4 MaintenanceService.get_history - A
    M 141:4 MaintenanceService.delete_expired_tasks - A
    M 168:4 MaintenanceService.get_prunable_tasks - A
    M 174:4 MaintenanceService.prune - A
    M 181:4 MaintenanceService.clear - A
src/beautyspot/cachekey.py
    F 176:0 _canonicalize_type - C
    F 42:0 _canonicalize_instance - B
    F 96:0 canonicalize - B
    M 322:4 KeyGen.from_file_content - A
    M 340:4 KeyGen._default - A
    F 85:0 _is_ndarray_like - A
    C 301:0 KeyGen - A
    M 372:4 KeyGen.hash_items - A
    F 21:0 _safe_sort_key - A
    F 123:0 _canonicalize_dict - A
    F 133:0 _canonicalize_sequence - A
    F 140:0 _canonicalize_set - A
    F 147:0 _canonicalize_deque - A
    C 244:0 KeyGenPolicy - A
    M 313:4 KeyGen.from_path_stat - A
    M 389:4 KeyGen.ignore - A
    M 404:4 KeyGen.file_content - A
    M 412:4 KeyGen.path_stat - A
    F 37:0 _canonicalize_ndarray - A
    F 153:0 _canonicalize_defaultdict - A
    F 159:0 _canonicalize_ordereddict - A
    F 165:0 _canonicalize_enum - A
    F 219:4 _canonicalize_np_ndarray - A
    C 231:0 Strategy - A
    M 250:4 KeyGenPolicy.__init__ - A
    M 258:4 KeyGenPolicy.bind - A
    M 397:4 KeyGen.map - A
src/beautyspot/db.py
    M 235:4 SQLiteTaskDB._enqueue_write - B
    M 282:4 SQLiteTaskDB.init_schema - B
    M 204:4 SQLiteTaskDB._writer_loop - B
    M 332:4 SQLiteTaskDB.get - B
    M 264:4 SQLiteTaskDB.shutdown - A
    C 140:0 SQLiteTaskDB - A
    M 468:4 SQLiteTaskDB.get_outdated_tasks - A
    M 505:4 SQLiteTaskDB.get_blob_refs - A
    F 24:0 _ensure_utc_isoformat - A
    M 163:4 SQLiteTaskDB._ensure_cache_dir - A
    M 411:4 SQLiteTaskDB.get_history - A
    M 516:4 SQLiteTaskDB.get_keys_start_with - A
    M 531:4 SQLiteTaskDB.flush - A
    F 35:0 _ensure_utc_isoformat_naive - A
    C 60:0 TaskDBBase - A
    M 145:4 SQLiteTaskDB.__init__ - A
    M 176:4 SQLiteTaskDB._connect - A
    M 489:4 SQLiteTaskDB.delete_expired - A
    C 42:0 TaskRecord - A
    C 50:0 _WriteTask - A
    M 66:4 TaskDBBase.init_schema - A
    M 70:4 TaskDBBase.get - A
    M 76:4 TaskDBBase.save - A
    M 92:4 TaskDBBase.get_history - A
    M 96:4 TaskDBBase.delete - A
    M 100:4 TaskDBBase.delete_expired - A
    M 104:4 TaskDBBase.prune - A
    M 111:4 TaskDBBase.get_outdated_tasks - A
    M 119:4 TaskDBBase.get_blob_refs - A
    M 123:4 TaskDBBase.delete_all - A
    M 127:4 TaskDBBase.get_keys_start_with - A
    M 131:4 TaskDBBase.flush - A
    M 135:4 TaskDBBase.shutdown - A
    M 193:4 SQLiteTaskDB._read_connect - A
    M 368:4 SQLiteTaskDB.save - A
    M 430:4 SQLiteTaskDB.delete - A
    M 437:4 SQLiteTaskDB.delete_all - A
    M 450:4 SQLiteTaskDB.prune - A
src/beautyspot/cli.py
    F 587:0 gc_cmd - D
    F 332:0 _show_cmd_inner - C
    F 155:0 _list_tasks_inner - C
    F 425:0 _stats_cmd_inner - C
    F 775:0 _prune_cmd_inner - C
    F 233:0 ui_cmd - B
    F 533:0 _clean_cmd_inner - B
    F 90:0 _list_databases - A
    F 480:0 clear_cmd - A
    F 50:0 _find_available_port - A
    F 60:0 _format_size - A
    F 75:0 _get_task_count - A
    F 33:0 get_service - A
    F 303:0 list_cmd - A
    F 740:0 prune_cmd - A
    F 851:0 version_cmd - A
    F 45:0 _is_port_in_use - A
    F 68:0 _format_timestamp - A
    F 150:0 _list_tasks - A
    F 321:0 show_cmd - A
    F 415:0 stats_cmd - A
    F 507:0 clean_cmd - A
    F 870:0 main - A
src/beautyspot/core.py
    M 935:4 Spot._check_cache_sync - B
    M 337:4 Spot._ensure_bg_resources - B
    M 411:4 Spot.flush - B
    M 469:4 Spot._trigger_auto_eviction - B
    M 702:4 Spot._execute_sync - B
    M 814:4 Spot._execute_async - B
    M 112:4 _BackgroundLoop.submit - B
    M 385:4 Spot.shutdown - B
    M 1262:4 Spot.cached_run - B
    M 143:4 _BackgroundLoop.stop - A
    M 232:4 Spot.__init__ - A
    M 549:4 Spot._resolve_key_fn - A
    M 617:4 Spot._calculate_expires_at - A
    C 70:0 _BackgroundLoop - A
    C 180:0 Spot - A
    M 321:4 Spot.maintenance - A
    M 646:4 Spot._dispatch_hooks - A
    M 1077:4 Spot._save_result_sync - A
    M 101:4 _BackgroundLoop._task_wrapper - A
    M 463:4 Spot._get_func_identifier - A
    M 576:4 Spot.register - A
    M 681:4 Spot._make_cache_key - A
    M 983:4 Spot._submit_background_save - A
    M 1014:4 Spot._invoke_error_callback - A
    M 1163:4 Spot.mark - A
    M 307:4 Spot._track_future - A
    M 373:4 Spot._shutdown_resources - A
    M 601:4 Spot.register_type - A
    M 664:4 Spot._resolve_settings - A
    M 1064:4 Spot._save_result_safe - A
    M 76:4 _BackgroundLoop.__init__ - A
    M 93:4 _BackgroundLoop._run_event_loop - A
    M 172:4 _BackgroundLoop._shutdown - A
    M 296:4 Spot.__enter__ - A
    M 299:4 Spot.__exit__ - A
    M 459:4 Spot._drain_futures - A
    M 1001:4 Spot._build_save_error_context - A
    M 1026:4 Spot._notify_save_discarded - A
    M 1042:4 Spot._handle_save_error - A
    M 1050:4 Spot._save_result_async - A
    M 1125:4 Spot.consume - A
    M 1146:4 Spot.mark - A
    M 1149:4 Spot.mark - A
    M 1230:4 Spot.cached_run - A
    M 1247:4 Spot.cached_run - A

241 blocks (classes, functions, methods) analyzed.
Average complexity: A (2.995850622406639)
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
src/beautyspot/hooks.py - A
src/beautyspot/dashboard.py - A
src/beautyspot/serializer.py - A
src/beautyspot/__init__.py - A
src/beautyspot/storage.py - A
src/beautyspot/lifecycle.py - A
src/beautyspot/maintenance.py - A
src/beautyspot/cachekey.py - A
src/beautyspot/db.py - A
src/beautyspot/cli.py - A
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
    SQLiteTaskDB -- "creates" --> RuntimeError
    SQLiteTaskDB -- "creates" --> TaskRecord
    SQLiteTaskDB -- "creates" --> TimeoutError
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
