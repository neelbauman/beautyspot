# 📊 Beautyspot Quality Report
**最終更新:** 2026-02-25 18:00:44

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
exceptions      | 4   | 0   | 0.00
_version        | 0   | 0   | 0.00
content_types   | 2   | 0   | 0.00
cli             | 0   | 2   | 1.00
maintenance     | 3   | 3   | 0.50
types           | 2   | 0   | 0.00
cachekey        | 1   | 0   | 0.00
storage         | 2   | 1   | 0.33
hooks           | 1   | 1   | 0.50
limiter         | 1   | 0   | 0.00
dashboard       | 0   | 2   | 1.00
db              | 3   | 0   | 0.00
serializer      | 2   | 1   | 0.33
lifecycle       | 1   | 1   | 0.50
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
    F 581:0 gc_cmd - D
    F 326:0 _show_cmd_inner - C
    F 149:0 _list_tasks_inner - C
    F 419:0 _stats_cmd_inner - C
    F 766:0 _prune_cmd_inner - C
src/beautyspot/maintenance.py
    M 250:4 MaintenanceService.clean_garbage - C
    M 200:4 MaintenanceService.scan_garbage - C
src/beautyspot/cachekey.py
    F 234:0 _canonicalize_type - C
src/beautyspot/db.py
    M 319:4 SQLiteTaskDB._enqueue_write - C
    M 683:4 SQLiteTaskDB.flush - C
src/beautyspot/serializer.py
    M 140:4 MsgpackSerializer._default_packer - C
src/beautyspot/lifecycle.py
    F 49:0 parse_retention - C
src/beautyspot/core.py
    M 1082:4 Spot._execute_async - D
    M 942:4 Spot._execute_sync - C

14 blocks (classes, functions, methods) analyzed.
Average complexity: C (13.714285714285714)
```

<details>
<summary>📄 すべての CC メトリクス一覧を表示</summary>

```text
src/beautyspot/exceptions.py
    C 4:0 BeautySpotError - A
    C 12:0 CacheCorruptedError - A
    C 19:0 SerializationError - A
    C 25:0 ConfigurationError - A
    C 32:0 ValidationError - A
    C 39:0 IncompatibleProviderError - A
src/beautyspot/content_types.py
    C 6:0 ContentType - A
src/beautyspot/cli.py
    F 581:0 gc_cmd - D
    F 326:0 _show_cmd_inner - C
    F 149:0 _list_tasks_inner - C
    F 419:0 _stats_cmd_inner - C
    F 766:0 _prune_cmd_inner - C
    F 227:0 ui_cmd - B
    F 527:0 _clean_cmd_inner - B
    F 84:0 _list_databases - A
    F 474:0 clear_cmd - A
    F 50:0 _find_available_port - A
    F 60:0 _format_size - A
    F 33:0 get_service - A
    F 297:0 list_cmd - A
    F 731:0 prune_cmd - A
    F 842:0 version_cmd - A
    F 45:0 _is_port_in_use - A
    F 68:0 _format_timestamp - A
    F 75:0 _get_task_count - A
    F 144:0 _list_tasks - A
    F 315:0 show_cmd - A
    F 409:0 stats_cmd - A
    F 501:0 clean_cmd - A
    F 861:0 main - A
src/beautyspot/maintenance.py
    M 250:4 MaintenanceService.clean_garbage - C
    M 200:4 MaintenanceService.scan_garbage - C
    M 103:4 MaintenanceService.get_task_detail - B
    M 147:4 MaintenanceService.delete_task - B
    M 49:4 MaintenanceService.from_path - A
    M 357:4 MaintenanceService.scan_orphan_projects - A
    C 19:0 MaintenanceService - A
    M 329:4 MaintenanceService.resolve_key_prefix - A
    M 377:4 MaintenanceService.delete_project_storage - A
    M 33:4 MaintenanceService.close - A
    M 24:4 MaintenanceService.__init__ - A
    M 42:4 MaintenanceService.__enter__ - A
    M 45:4 MaintenanceService.__exit__ - A
    M 99:4 MaintenanceService.get_history - A
    M 142:4 MaintenanceService.delete_expired_tasks - A
    M 181:4 MaintenanceService.get_prunable_tasks - A
    M 187:4 MaintenanceService.prune - A
    M 194:4 MaintenanceService.clear - A
src/beautyspot/types.py
    C 40:0 HookContextBase - A
    M 54:4 HookContextBase.__post_init__ - A
    C 11:0 SaveErrorContext - A
    C 62:0 PreExecuteContext - A
    C 69:0 CacheHitContext - A
    C 77:0 CacheMissContext - A
src/beautyspot/cachekey.py
    F 234:0 _canonicalize_type - C
    F 42:0 _canonicalize_instance - B
    F 95:0 canonicalize - B
    M 380:4 KeyGen.from_file_content - A
    M 398:4 KeyGen._default - A
    F 84:0 _is_ndarray_like - A
    F 128:0 _canonicalize_dict - A
    C 359:0 KeyGen - A
    M 430:4 KeyGen.hash_items - A
    F 21:0 _safe_sort_key - A
    F 137:0 _canonicalize_list - A
    F 148:0 _canonicalize_tuple - A
    F 158:0 _canonicalize_set - A
    F 173:0 _canonicalize_frozenset - A
    F 187:0 _canonicalize_deque - A
    F 208:0 _canonicalize_ordereddict - A
    C 302:0 KeyGenPolicy - A
    M 371:4 KeyGen.from_path_stat - A
    M 447:4 KeyGen.ignore - A
    M 462:4 KeyGen.file_content - A
    M 470:4 KeyGen.path_stat - A
    F 37:0 _canonicalize_ndarray - A
    F 197:0 _canonicalize_defaultdict - A
    F 223:0 _canonicalize_enum - A
    F 277:4 _canonicalize_np_ndarray - A
    C 289:0 Strategy - A
    M 308:4 KeyGenPolicy.__init__ - A
    M 316:4 KeyGenPolicy.bind - A
    M 455:4 KeyGen.map - A
src/beautyspot/storage.py
    M 304:4 LocalStorage.prune_empty_dirs - B
    M 280:4 LocalStorage.clean_temp_files - B
    C 151:0 LocalStorage - A
    M 352:4 S3Storage.__init__ - A
    M 369:4 S3Storage._parse_s3_uri - A
    M 171:4 LocalStorage._validate_key - A
    M 212:4 LocalStorage.load - A
    M 233:4 LocalStorage.delete - A
    M 257:4 LocalStorage.list_keys - A
    C 351:0 S3Storage - A
    C 51:0 WarningOnlyPolicy - A
    M 158:4 LocalStorage._ensure_cache_dir - A
    M 186:4 LocalStorage.save - A
    M 271:4 LocalStorage.get_mtime - A
    M 425:4 S3Storage.list_keys - A
    F 433:0 create_storage - A
    C 28:0 StoragePolicyProtocol - A
    C 38:0 ThresholdStoragePolicy - A
    M 66:4 WarningOnlyPolicy.should_save_as_blob - A
    C 76:0 AlwaysBlobPolicy - A
    C 89:0 BlobStorageBase - A
    M 389:4 S3Storage.load - A
    M 401:4 S3Storage.delete - A
    M 414:4 S3Storage.get_mtime - A
    M 34:4 StoragePolicyProtocol.should_save_as_blob - A
    M 46:4 ThresholdStoragePolicy.should_save_as_blob - A
    M 82:4 AlwaysBlobPolicy.should_save_as_blob - A
    M 95:4 BlobStorageBase.save - A
    M 103:4 BlobStorageBase.load - A
    M 110:4 BlobStorageBase.delete - A
    M 118:4 BlobStorageBase.list_keys - A
    M 127:4 BlobStorageBase.get_mtime - A
    M 134:4 BlobStorageBase.prune_empty_dirs - A
    M 142:4 BlobStorageBase.clean_temp_files - A
    M 152:4 LocalStorage.__init__ - A
    M 381:4 S3Storage.save - A
src/beautyspot/hooks.py
    C 51:0 ThreadSafeHookBase - A
    M 80:4 ThreadSafeHookBase.__init_subclass__ - A
    C 12:0 HookBase - A
    M 93:4 ThreadSafeHookBase.__getattr__ - A
    F 40:0 _wrap_with_lock - A
    M 23:4 HookBase.pre_execute - A
    M 26:4 HookBase.on_cache_hit - A
    M 29:4 HookBase.on_cache_miss - A
    M 86:4 ThreadSafeHookBase.__init__ - A
src/beautyspot/limiter.py
    M 44:4 TokenBucket._consume_reservation - A
    C 16:0 TokenBucket - A
    C 10:0 LimiterProtocol - A
    M 28:4 TokenBucket.__init__ - A
    M 74:4 TokenBucket.consume - A
    M 92:4 TokenBucket.consume_async - A
    M 11:4 LimiterProtocol.consume - A
    M 13:4 LimiterProtocol.consume_async - A
src/beautyspot/dashboard.py
    F 44:0 load_data - A
    F 15:0 get_args - A
src/beautyspot/db.py
    M 319:4 SQLiteTaskDB._enqueue_write - C
    M 683:4 SQLiteTaskDB.flush - C
    M 231:4 SQLiteTaskDB._read_connect - B
    M 281:4 SQLiteTaskDB._writer_loop - B
    M 363:4 SQLiteTaskDB.shutdown - B
    M 463:4 SQLiteTaskDB.get - B
    C 190:0 SQLiteTaskDB - A
    M 25:4 _ReadConnWrapper.close - A
    M 599:4 SQLiteTaskDB.get_outdated_tasks - A
    M 636:4 SQLiteTaskDB.get_blob_refs - A
    F 57:0 _ensure_utc_isoformat - A
    C 19:0 _ReadConnWrapper - A
    C 76:0 _WriteTask - A
    M 195:4 SQLiteTaskDB.__init__ - A
    M 218:4 SQLiteTaskDB._ensure_cache_dir - A
    M 542:4 SQLiteTaskDB.get_history - A
    M 647:4 SQLiteTaskDB.get_keys_start_with - A
    M 663:4 SQLiteTaskDB.count_tasks - A
    M 84:4 _WriteTask.try_cancel - A
    M 92:4 _WriteTask.try_start - A
    M 100:4 _WriteTask.mark_done - A
    C 110:0 TaskDBBase - A
    M 620:4 SQLiteTaskDB.delete_expired - A
    M 20:4 _ReadConnWrapper.__init__ - A
    M 47:4 _ReadConnWrapper.__del__ - A
    C 68:0 TaskRecord - A
    M 116:4 TaskDBBase.init_schema - A
    M 120:4 TaskDBBase.get - A
    M 126:4 TaskDBBase.save - A
    M 142:4 TaskDBBase.get_history - A
    M 146:4 TaskDBBase.delete - A
    M 150:4 TaskDBBase.delete_expired - A
    M 154:4 TaskDBBase.prune - A
    M 161:4 TaskDBBase.get_outdated_tasks - A
    M 169:4 TaskDBBase.get_blob_refs - A
    M 173:4 TaskDBBase.delete_all - A
    M 177:4 TaskDBBase.get_keys_start_with - A
    M 181:4 TaskDBBase.flush - A
    M 185:4 TaskDBBase.shutdown - A
    M 391:4 SQLiteTaskDB.init_schema - A
    M 499:4 SQLiteTaskDB.save - A
    M 561:4 SQLiteTaskDB.delete - A
    M 568:4 SQLiteTaskDB.delete_all - A
    M 581:4 SQLiteTaskDB.prune - A
src/beautyspot/serializer.py
    M 140:4 MsgpackSerializer._default_packer - C
    C 38:0 MsgpackSerializer - A
    M 96:4 MsgpackSerializer.register - A
    M 199:4 MsgpackSerializer._ext_hook - A
    M 222:4 MsgpackSerializer.dumps - A
    M 78:4 MsgpackSerializer._get_local_cache - A
    M 233:4 MsgpackSerializer.loads - A
    C 22:0 SerializerProtocol - A
    C 28:0 TypeRegistryProtocol - A
    M 91:4 MsgpackSerializer._enforce_cache_size - A
    M 23:4 SerializerProtocol.dumps - A
    M 24:4 SerializerProtocol.loads - A
    M 29:4 TypeRegistryProtocol.register - A
    M 61:4 MsgpackSerializer.__init__ - A
src/beautyspot/lifecycle.py
    F 49:0 parse_retention - C
    M 143:4 LifecyclePolicy.resolve_with_fallback - A
    C 15:0 _ForeverSentinel - A
    M 26:4 _ForeverSentinel.__new__ - A
    C 124:0 LifecyclePolicy - A
    M 132:4 LifecyclePolicy.resolve - A
    M 35:4 _ForeverSentinel.__repr__ - A
    M 38:4 _ForeverSentinel.__bool__ - A
    C 98:0 Retention - A
    C 115:0 Rule - A
    M 129:4 LifecyclePolicy.__init__ - A
    M 161:4 LifecyclePolicy.default - A
src/beautyspot/__init__.py
    F 46:0 Spot - B
src/beautyspot/core.py
    M 1082:4 Spot._execute_async - D
    M 942:4 Spot._execute_sync - C
    M 904:4 Spot._notify_and_cleanup_inflight - B
    M 1279:4 Spot._check_cache_sync - B
    M 370:4 Spot._ensure_bg_resources - B
    M 448:4 Spot.flush - B
    M 505:4 Spot._trigger_auto_eviction - B
    M 873:4 Spot._persist_result_async - B
    M 127:4 _BackgroundLoop.submit - B
    M 429:4 Spot.shutdown - B
    M 854:4 Spot._persist_result_sync - B
    M 1439:4 Spot._save_result_sync - B
    M 1654:4 Spot.cached_run - B
    M 158:4 _BackgroundLoop.stop - A
    C 195:0 Spot - A
    M 249:4 Spot.__init__ - A
    M 609:4 Spot._resolve_key_fn - A
    M 677:4 Spot._calculate_expires_at - A
    C 85:0 _BackgroundLoop - A
    M 352:4 Spot.maintenance - A
    M 711:4 Spot._dispatch_hooks - A
    M 116:4 _BackgroundLoop._task_wrapper - A
    M 499:4 Spot._get_func_identifier - A
    M 636:4 Spot.register - A
    M 746:4 Spot._make_cache_key - A
    M 1333:4 Spot._submit_background_save - A
    M 1373:4 Spot._invoke_error_callback - A
    M 1549:4 Spot.mark - A
    M 338:4 Spot._track_future - A
    M 414:4 Spot._shutdown_resources - A
    M 661:4 Spot.register_type - A
    M 729:4 Spot._resolve_settings - A
    M 771:4 Spot._prepare_execution - A
    M 1351:4 Spot._build_save_error_context - A
    M 1409:4 Spot._save_result_async - A
    M 1426:4 Spot._save_result_safe - A
    C 72:0 _ExecutionContext - A
    M 91:4 _BackgroundLoop.__init__ - A
    M 108:4 _BackgroundLoop._run_event_loop - A
    M 187:4 _BackgroundLoop._shutdown - A
    M 327:4 Spot.__enter__ - A
    M 330:4 Spot.__exit__ - A
    M 496:4 Spot._drain_futures - A
    M 803:4 Spot._build_cache_hit_context - A
    M 824:4 Spot._build_save_kwargs - A
    M 1385:4 Spot._notify_save_discarded - A
    M 1401:4 Spot._handle_save_error - A
    M 1503:4 Spot.consume - A
    M 1532:4 Spot.mark - A
    M 1535:4 Spot.mark - A
    M 1622:4 Spot.cached_run - A
    M 1639:4 Spot.cached_run - A

261 blocks (classes, functions, methods) analyzed.
Average complexity: A (3.218390804597701)
```
</details>

### 2.2 保守性指数 (Maintainability Index)
#### ⚠️ 警告 (Rank B 以下)
コードの読みやすさ・保守しやすさに改善の余地があるモジュールです。

```text
src/beautyspot/core.py - B
```

<details>
<summary>📄 すべての MI メトリクス一覧を表示</summary>

```text
src/beautyspot/exceptions.py - A
src/beautyspot/_version.py - A
src/beautyspot/content_types.py - A
src/beautyspot/cli.py - A
src/beautyspot/maintenance.py - A
src/beautyspot/types.py - A
src/beautyspot/cachekey.py - A
src/beautyspot/storage.py - A
src/beautyspot/hooks.py - A
src/beautyspot/limiter.py - A
src/beautyspot/dashboard.py - A
src/beautyspot/db.py - A
src/beautyspot/serializer.py - A
src/beautyspot/lifecycle.py - A
src/beautyspot/__init__.py - A
src/beautyspot/core.py - B
```
</details>

## 4. デザイン・インテント分析 (Design Intent Map)
クラス図には現れない、生成関係、静的利用、および Protocol への暗黙的な準拠を可視化します。

```mermaid
graph LR
    classDef protocol fill:#f9f,stroke:#333,stroke-width:2px;
    class StoragePolicyProtocol protocol;
    class LimiterProtocol protocol;
    class SerializerProtocol protocol;
    class TypeRegistryProtocol protocol;
    AlwaysBlobPolicy -. "implements" .-> StoragePolicyProtocol
    HookContextBase -- "creates" --> MappingProxyType
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
    Spot -- "creates" --> ConfigurationError
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
    Spot -- "creates" --> TypeError
    Spot -. "implements" .-> TypeRegistryProtocol
    Spot -- "creates" --> ValidationError
    Spot -- "creates" --> ValueError
    ThreadSafeHookBase -- "creates" --> AttributeError
    ThresholdStoragePolicy -. "implements" .-> StoragePolicyProtocol
    TokenBucket -. "implements" .-> LimiterProtocol
    TokenBucket -- "creates" --> ValueError
    WarningOnlyPolicy -. "implements" .-> StoragePolicyProtocol
```
