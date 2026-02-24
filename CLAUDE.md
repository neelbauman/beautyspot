# CLAUDE.md — beautyspot

This file provides guidance for AI assistants working on the `beautyspot` codebase.

## How to Maintain This File

CLAUDE.md has two zones:

- **Manual zone** (above the `AUTO-GENERATED` marker): conventions, judgment criteria,
  and workflows. Edit directly when team conventions change.
- **Auto-generated zone** (below the marker): module list, class summaries, CLI commands,
  and public API — derived from source docstrings via `tools/generate_claude_ref.py`.
  **Never edit manually.** Run `make update-claude` to refresh.

### When to run `make update-claude`

| Change | Action |
|---|---|
| New `.py` module added to `src/beautyspot/` | `make update-claude` |
| New CLI command added (`@app.command`) | `make update-claude` |
| Class docstring updated | `make update-claude` |
| `__all__` in `__init__.py` changed | `make update-claude` |
| Convention or DI principle changed | Edit manual zone directly |

---

## Project Overview

`beautyspot` is a Python OSS library that transparently caches function execution results
and accelerates re-execution of complex data pipelines and ML experiments.

- **Python**: >=3.12 | **Package manager**: `uv` | **PyPI**: `beautyspot`
- Public entry point: `bs.Spot(...)` — a factory function that wires all components via DI.

---

## Development Commands

```bash
make install      # uv sync --all-groups
make test         # pytest + pyright typing tests
make lint         # ruff check (lint only)
make lint-fix     # ruff check --fix
make format       # ruff format
make build        # clean → test → uv build
make docs-serve   # MkDocs local preview
make audit        # radon cyclomatic complexity check
make update-claude  # Regenerate the auto-generated section below
```

---

## Architecture

```
bs.Spot() [__init__.py]      ← Factory function (DI wiring, the only public entry point)
    │
    ▼
core.Spot [core.py]          ← Main caching engine
    ├── db              TaskDBBase          (metadata + cache lookup)
    ├── serializer      SerializerProtocol
    ├── storage_backend BlobStorageBase
    ├── storage_policy  StoragePolicyProtocol
    ├── limiter         LimiterProtocol
    ├── lifecycle_policy LifecyclePolicy
    └── executor        ThreadPoolExecutor  (background IO)
```

For module details, read the source. The auto-generated section below lists key classes.

---

## Key Conventions

### DI Principles

All components are injected, never hardcoded. `__init__.py:Spot()` is the **only** place
that wires defaults. `core.Spot.__init__` requires all deps explicitly — never instantiate
it directly in user code, always use `bs.Spot(...)`.

### Non-blocking Persistence

- `default_wait=True` (default): saves on calling thread — safe, adds latency.
- `default_wait=False`: submits to `ThreadPoolExecutor` — zero latency, flush on `with spot:` exit.
- Per-call override: `@spot.mark(wait=False)`.
- Background save failures are logged at ERROR level and never raise.

### Context Manager

```python
with spot:
    result = my_func(args)
# Waits for pending background saves. Does NOT shut down the executor.
# The same spot instance is reusable in another `with` block.
```

### Cache Key Stability

- Changing a function's `__name__` or its `version=` string invalidates the cache.
- `kwargs` order is irrelevant (dicts are sorted before hashing).
- Use `keygen=KeyGen.ignore("verbose")` to exclude non-deterministic args.
- `input_key_fn` is deprecated → use `keygen`.

### Storage: DIRECT_BLOB vs FILE

The `save_blob` parameter precedence:
1. Explicit `save_blob=True/False` on `@spot.mark(...)`.
2. `storage_policy.should_save_as_blob(data)` when `save_blob=None` (default).

Default policy is `WarningOnlyPolicy` — never forces blob, only warns when large.

### Deprecations

| Old | New | Timing |
|---|---|---|
| `input_key_fn` | `keygen` | `DeprecationWarning` at decoration time |
| `@task` | `@mark` | — |
| `Project` | `Spot` | — |
| `run()` | `@mark` / `cached_run()` | Removed in v2.0 |

---

## Testing Guidelines

### Layer Selection

| Scenario | Layer |
|---|---|
| New function / class logic, no I/O | `tests/unit/` |
| New `Spot` option, DB operation, or storage backend | `tests/integration/` |
| Bug regression, user workflow, security | `tests/scenarios/` |
| Deprecated param still emits warning and works | `tests/migration/` |
| Type inference correctness | `tests/typing/` (pyright) |

### Key Fixture: `inspect_db`

Defined in `tests/conftest.py`. Returns all rows from a SQLite DB as `list[dict]`.
Use it to assert DB state after cache operations.

```python
def test_something(inspect_db, tmp_path):
    db_path = tmp_path / "test.db"
    # ... run spot operations ...
    rows = inspect_db(db_path)
    assert rows[0]["func_name"] == "my_func"
```

### Integration Test Pattern

```python
import beautyspot as bs

def test_basic_cache(tmp_path):
    spot = bs.Spot(
        name="test",
        db=bs.SQLiteTaskDB(tmp_path / "t.db"),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
    )

    @spot.mark()
    def fn(x): return x * 2

    assert fn(3) == 6
    assert fn(3) == 6  # cache hit
```

---

## Common Tasks

### Adding a new `@mark` option

1. Add the parameter to `Spot.mark()` in `core.py`.
2. Thread it through `_execute_sync` and `_execute_async`.
3. Update `_resolve_settings` if it needs a Spot-level default.
4. Update `Spot.cached_run()` if it applies there too.
5. Update the factory in `__init__.py` if it needs a constructor-level default.
6. Tests: `tests/unit/` for logic, `tests/integration/core/` for end-to-end.

### Adding a new storage backend

1. Subclass `BlobStorageBase` in `storage.py` (implement `save`, `load`, `delete`, `list_keys`).
2. Update `create_storage()` factory if it should be auto-detected by URI scheme.
3. Guard the optional import (see `S3Storage` / `boto3` pattern).
4. Tests: `tests/integration/storage/`.

### Adding a new CLI command

1. Add `@app.command("name")` in `cli.py`.
2. Use `get_service(db_path)` to get a `MaintenanceService`.
3. Use `rich` `Console`, `Table`, `Panel` for output.
4. Tests: `tests/integration/cli/`.

### Registering a custom serializable type

```python
@spot.register(
    code=1,  # unique int 0–127 per MsgpackSerializer instance
    encoder=lambda obj: {"data": obj.to_dict()},
    decoder=lambda d: MyClass.from_dict(d),
)
class MyClass: ...

# Or imperatively:
spot.register_type(MyClass, code=1, encoder=..., decoder=...)
```

---

<!-- AUTO-GENERATED BELOW — run `make update-claude` to refresh -->

## Reference (Auto-generated — do not edit manually)

### Modules

| Module | Key classes |
|---|---|
| `cachekey.py` | `Strategy`, `KeyGenPolicy`, `KeyGen` |
| `cli.py` | — |
| `content_types.py` | `ContentType` |
| `core.py` | `_BackgroundLoop`, `Spot` |
| `db.py` | `TaskDBBase`, `SQLiteTaskDB` |
| `exceptions.py` | `BeautySpotError`, `CacheCorruptedError`, `SerializationError`, `ConfigurationError`, `ValidationError` |
| `hooks.py` | `HookBase`, `ThreadSafeHookBase` |
| `lifecycle.py` | `Retention`, `Rule`, `LifecyclePolicy` |
| `limiter.py` | `TokenBucket` |
| `maintenance.py` | `MaintenanceService` |
| `serializer.py` | `SerializerProtocol`, `TypeRegistryProtocol`, `MsgpackSerializer` |
| `storage.py` | `StoragePolicyProtocol`, `ThresholdStoragePolicy`, `WarningOnlyPolicy`, `AlwaysBlobPolicy`, `BlobStorageBase` |
| `types.py` | `SaveErrorContext`, `HookContextBase`, `PreExecuteContext`, `CacheHitContext`, `CacheMissContext` |

### Class Summaries

**`cachekey.py`**

- `Strategy`: Defines the strategy for hashing a specific argument
- `KeyGenPolicy`: A policy object that binds to a function signature to generate cache keys
- `KeyGen`: Generates stable cache keys (SHA-256) for function inputs (Identity Layer)

**`content_types.py`**

- `ContentType`: Supported semantic content types for beautyspot tasks

**`core.py`**

- `_BackgroundLoop`: バックグラウンドで asyncio イベントループを実行するヘルパー。
- `Spot`: Spot class that handles task management, serialization, and

**`db.py`**

- `TaskDBBase`: Abstract interface for task metadata storage
- `SQLiteTaskDB`: Default implementation using SQLite

**`exceptions.py`**

- `BeautySpotError`: Base exception for all beautyspot errors
- `CacheCorruptedError`: Raised when cache data (DB record or Blob file) is lost,
- `SerializationError`: Raised when the serializer fails to encode or decode data
- `ConfigurationError`: Raised when there is a logical error in the user's configuration
- `ValidationError`: メソッド呼び出し時の引数やバリデーションエラー。
- `IncompatibleProviderError`: 注入された依存オブジェクト（Serializer, Storage, DB）が

**`hooks.py`**

- `HookBase`: beautyspotのタスク実行ライフサイクルに介入するためのベースクラス。
- `ThreadSafeHookBase`: スレッドセーフなフックベースクラス。

**`lifecycle.py`**

- `Retention`: Constants for retention policies
- `Rule`: A rule defining retention policy based on function name pattern
- `LifecyclePolicy`: Manages data retention policies based on function names

**`limiter.py`**

- `TokenBucket`: A smooth rate limiter based on the GCRA (Generic Cell Rate Algorithm)

**`maintenance.py`**

- `MaintenanceService`: Service layer for administrative tasks, dashboard support, and system assembly

**`serializer.py`**

- `SerializerProtocol`: Protocol for custom serializers
- `TypeRegistryProtocol`: Protocol for serializers that support custom type registration
- `MsgpackSerializer`: A secure and extensible serializer based on MessagePack

**`storage.py`**

- `StoragePolicyProtocol`: Protocol to determine if data should be saved as a blob (file/object storage)
- `ThresholdStoragePolicy`: Policy that saves data as a blob if its size exceeds a configured threshold
- `WarningOnlyPolicy`: Policy for backward compatibility (v2.0 behavior)
- `AlwaysBlobPolicy`: Policy that always saves data as a blob
- `BlobStorageBase`: Abstract base class for large object storage (BLOBs)

**`types.py`**

- `SaveErrorContext`: バックグラウンドでのキャッシュ保存処理 (wait=False) が失敗した際に、
- `HookContextBase`: すべてのフックに共通する基本コンテキスト情報。
- `PreExecuteContext`: 関数実行前、またはキャッシュ確認前に渡されるコンテキスト。
- `CacheHitContext`: キャッシュから正常に結果が取得された際に渡されるコンテキスト。
- `CacheMissContext`: キャッシュミスとなり、元の関数が実行された後に渡されるコンテキスト。

### CLI Commands

| Command | Description |
|---|---|
| `beautyspot ui` | 🚀 Launch the interactive dashboard |
| `beautyspot list` | 📋 List cached tasks or available databases |
| `beautyspot show` | 🔍 Show details of a specific cached task |
| `beautyspot stats` | 📊 Show cache statistics |
| `beautyspot clear` | 🗑️  Clear cached tasks |
| `beautyspot clean` | 🧹 Clean orphaned blob files (garbage collection) |
| `beautyspot gc` | 🗑️  Garbage Collect: Clean up expired tasks and orphan storage |
| `beautyspot prune` | 🗓️  Prune old cached tasks (time-based expiration) |
| `beautyspot version` | ℹ️  Show version information |

### Public API (`import beautyspot as bs`)

`Spot`, `SpotType`, `KeyGen`, `ContentType`, `SaveErrorContext`, `BeautySpotError`, `CacheCorruptedError`, `SerializationError`, `ConfigurationError`, `TaskDBBase`, `BlobStorageBase`, `SerializerProtocol`, `StoragePolicyProtocol`, `LimiterProtocol`, `SQLiteTaskDB`, `LocalStorage`, `MsgpackSerializer`, `TokenBucket`, `ThresholdStoragePolicy`, `WarningOnlyPolicy`, `AlwaysBlobPolicy`, `LifecyclePolicy`, `Rule`, `Retention`, `HookBase`, `ThreadSafeHookBase`, `PreExecuteContext`, `CacheHitContext`, `CacheMissContext`

