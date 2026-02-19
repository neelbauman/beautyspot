# CLAUDE.md — beautyspot

This file provides guidance for AI assistants working on the `beautyspot` codebase.

---

## Project Overview

`beautyspot` is a Python OSS library that transparently caches function execution results and accelerates re-execution of complex data pipelines and ML experiments. The public API entry point is `bs.Spot(...)`, a factory function that wires together all internal components via Dependency Injection (DI).

- **Current version**: 2.5.2 (determined by git tags via `hatch-vcs`)
- **Python requirement**: >=3.12
- **Package manager**: `uv`
- **PyPI**: `beautyspot`
- **Docs**: MkDocs (mkdocs-material)

---

## Repository Layout

```
beautyspot/
├── src/beautyspot/          # Library source
│   ├── __init__.py          # Public API: Spot() factory + re-exports
│   ├── core.py              # Spot class (main engine), ScopedMark
│   ├── cachekey.py          # KeyGen, KeyGenPolicy, Strategy, canonicalize()
│   ├── cli.py               # CLI entry point (Typer)
│   ├── content_types.py     # ContentType constants (semantic MIME types)
│   ├── dashboard.py         # Streamlit dashboard
│   ├── db.py                # TaskDBBase (ABC), SQLiteTaskDB
│   ├── lifecycle.py         # LifecyclePolicy, Rule, Retention, parse_retention
│   ├── limiter.py           # LimiterProtocol, TokenBucket (GCRA)
│   ├── maintenance.py       # MaintenanceService (admin + GC)
│   ├── serializer.py        # SerializerProtocol, MsgpackSerializer
│   └── storage.py           # BlobStorageBase, LocalStorage, S3Storage, policies
├── tests/
│   ├── conftest.py          # Shared fixtures (inspect_db factory)
│   ├── unit/                # Pure logic tests (no disk/DB)
│   ├── integration/         # Component tests with real SQLite + filesystem
│   │   ├── core/            # mark, cached_run, context manager, DI, etc.
│   │   ├── storage/         # SQLite CRUD, blob ops
│   │   └── cli/             # CLI command tests
│   ├── senarios/            # (intentional typo) E2E / security / edge-case tests
│   ├── migration/           # Backward-compat tests for deprecated params
│   └── typing/              # Pyright type inference tests
├── docs/
│   ├── guides/              # Usage guides (lifecycle, CLI, caching, etc.)
│   ├── cookbooks/           # Task-specific examples
│   ├── reference/           # API reference
│   └── adr/                 # Architecture Decision Records (ADR-0000..ADR-0030)
├── tools/                   # Analysis scripts (report generation, structure analysis)
├── Makefile                 # Developer workflow targets
├── pyproject.toml           # Package metadata + tool configuration
├── mkdocs.yml               # Documentation site config
└── .pre-commit-config.yaml  # Pre-commit hooks
```

---

## Development Commands

All commands use `uv`. Run from the repository root.

```bash
# Install all dependencies (including dev group)
make install        # uv sync --all-groups

# Run full test suite (pytest + pyright type tests)
make test

# Lint (ruff)
make lint           # check only
make lint-fix       # auto-fix

# Format (ruff)
make format

# Build wheel (runs tests first, version from git tag)
make build

# Serve docs locally
make docs-serve

# Code quality audit (radon cyclomatic complexity + maintainability)
make audit

# Generate dependency graphs and class diagrams
make visualize
```

### Running Tests Directly

```bash
# All tests
uv run pytest

# Specific layer
uv run pytest tests/unit
uv run pytest tests/integration
uv run pytest tests/senarios
uv run pytest tests/migration

# Pyright typing tests only
uv run pyright tests/typing

# With coverage
uv run pytest --cov=src/beautyspot
```

---

## Architecture

### Component Diagram

```
User code
    |
    v
bs.Spot() [__init__.py]           <- Factory function (DI wiring)
    |
    v
core.Spot [core.py]               <- Main caching engine
    |-- db:           TaskDBBase       (metadata + cache lookup)
    |-- serializer:   SerializerProtocol
    |-- storage_backend: BlobStorageBase
    |-- storage_policy: StoragePolicyProtocol
    |-- limiter:      LimiterProtocol
    |-- lifecycle_policy: LifecyclePolicy
    `-- executor:     ThreadPoolExecutor  (background IO)
```

### Key Modules

#### `core.py` — `Spot` class

- `mark(func, ...)`: Decorator. Wraps a sync or async function with cache-check → execute → save logic.
- `cached_run(func, ...)`: Returns a `ScopedMark` context manager. The wrapped function is only callable inside the `with` block (enforced via `ContextVar`).
- `limiter(cost)`: Decorator for rate-limiting function calls using `TokenBucket`.
- `register(code, encoder, decoder)` / `register_type(...)`: Register custom types with `MsgpackSerializer`.
- `__enter__` / `__exit__`: Context manager. On exit, waits for all pending background save futures.
- `_execute_sync` / `_execute_async`: Core execution paths. Both perform: cache check → function call → expiration calculation → save (sync or background).
- `_save_result_sync`: Serializes result, applies storage policy (DIRECT_BLOB vs FILE), writes to DB.
- `_save_result_safe`: Background wrapper for `_save_result_sync`; swallows exceptions and logs them.

#### `__init__.py` — Public API Factory

`Spot()` in `__init__.py` is a **factory function** (not the class itself). It resolves defaults for all components using DI:
- `db` defaults to `SQLiteTaskDB(".beautyspot/{name}.db")`
- `storage_backend` defaults to `LocalStorage(".beautyspot/blobs/{name}/")`
- `serializer` defaults to `MsgpackSerializer()`
- `limiter` defaults to `TokenBucket(tpm=10000)`
- `storage_policy` defaults to `WarningOnlyPolicy` (warns on large data, does not force blob storage)

#### `db.py` — Task Database

- `TaskDBBase`: Abstract interface (`init_schema`, `get`, `save`, `delete`, `get_history`, `prune`, `delete_expired`, `get_blob_refs`, `get_keys_start_with`).
- `SQLiteTaskDB`: Default SQLite implementation. Uses WAL journal mode. Auto-migrates schema for new columns (`content_type`, `version`, `result_data`, `expires_at`). Lazy expiration: expired records are treated as cache misses on `get()`, physical deletion deferred to `beautyspot gc`.

SQLite schema (`tasks` table):

| Column | Type | Notes |
|---|---|---|
| `cache_key` | TEXT PK | MD5 of `func_name:iid[:version]` |
| `func_name` | TEXT | Decorated function name |
| `input_id` | TEXT | SHA-256 of canonicalized args |
| `result_type` | TEXT | `DIRECT_BLOB` or `FILE` |
| `result_value` | TEXT | Blob filename (if `FILE`) |
| `result_data` | BLOB | Inline data (if `DIRECT_BLOB`) |
| `content_type` | TEXT | Semantic MIME type (optional) |
| `version` | TEXT | User-specified version tag |
| `updated_at` | TIMESTAMP | Auto-set by SQLite default |
| `expires_at` | TIMESTAMP | NULL = indefinite |

#### `storage.py` — Blob Storage

- `BlobStorageBase`: ABC with `save(key, data) -> location`, `load(location) -> bytes`, `delete(location)`, `list_keys()`.
- `LocalStorage`: Writes `{key}.bin` under `base_dir`. Uses atomic writes (temp file + rename). Returns relative filename as location (portable). Validates keys to prevent path traversal. `prune_empty_dirs()` cleans up empty subdirectories.
- `S3Storage`: S3-backed storage. Requires `beautyspot[s3]` extra (`boto3`). Stores as `{prefix}/{key}.bin`.
- `create_storage(path)`: Factory that dispatches to `S3Storage` (if `s3://` prefix) or `LocalStorage`.

Storage policies (determine whether to inline in SQLite or use blob storage):

| Policy | Behavior |
|---|---|
| `WarningOnlyPolicy` | Never forces blob; logs warning if size > threshold. **Default.** |
| `ThresholdStoragePolicy` | Uses blob if `len(data) > threshold` |
| `AlwaysBlobPolicy` | Always saves to blob storage |

#### `serializer.py` — Serialization

- `MsgpackSerializer`: Uses `msgpack` with a nested `ExtType` protocol for custom types. Registers custom encoders/decoders via `register(type_class, code, encoder, decoder)`. ExtType codes must be 0–127 and unique per `MsgpackSerializer` instance.
- `SerializerProtocol` / `TypeRegistryProtocol`: Runtime-checkable Protocols for DI.
- `SerializationError`: Raised for unsupported types or corrupted data.

#### `cachekey.py` — Cache Key Generation

Cache key computation (two layers):

1. **Input ID (iid)**: SHA-256 of canonicalized `(args, kwargs)`. Deterministic via `msgpack.packb` of the canonical form.
2. **Cache key (ck)**: MD5 of `"{func_name}:{iid}[:{version}]"`.

`canonicalize(obj)` handles: primitives, dicts (sorted by key), lists/tuples, sets/frozensets (sorted), Enums, numpy arrays (shape + dtype + raw bytes), Pydantic models (JSON schema), and arbitrary objects (`__dict__` / `__slots__`).

`KeyGen` class methods for custom key strategies:
- `KeyGen.ignore(*arg_names)`: Exclude specific args from hash.
- `KeyGen.map(**arg_strategies)`: Per-argument `Strategy` (DEFAULT, IGNORE, FILE_CONTENT, PATH_STAT).
- `KeyGen.file_content(*arg_names)`: Hash file content (SHA-256).
- `KeyGen.path_stat(*arg_names)`: Hash file path + size + mtime (fast).

#### `lifecycle.py` — Retention Policies

- `LifecyclePolicy`: A list of `Rule` objects. First matching rule wins.
- `Rule(pattern, retention)`: `pattern` is a `fnmatch`-style glob on function names. `retention` is a `timedelta`, a string (`"7d"`, `"12h"`, `"30m"`), int (seconds), or `None` (indefinite).
- `parse_retention(value)`: Normalizes retention specification to `timedelta | None`.

#### `limiter.py` — Rate Limiting

- `TokenBucket`: GCRA-based rate limiter. Strict pacing (no burst after idle). Thread-safe and async-compatible. `consume(cost)` blocks; `consume_async(cost)` awaits.

#### `maintenance.py` — MaintenanceService

Admin operations separated from execution:
- `from_path(db_path, blob_dir)`: Factory from DB file path (auto-detects blob dir).
- `get_history(limit)`, `get_task_detail(cache_key)`: Dashboard data retrieval.
- `delete_task(cache_key)`: Deletes DB record + associated blob.
- `delete_expired_tasks()`: Physical deletion of expired records.
- `prune(days, func_name)`: Delete tasks older than N days.
- `clear(func_name)`: Delete all (or all for a function).
- `scan_garbage()` / `clean_garbage()`: Orphaned blob file detection and cleanup.
- `scan_orphan_projects(workspace_dir)`: Find blob dirs without a corresponding `.db` file (zombie projects).

#### `cli.py` — CLI

Entrypoint: `beautyspot` (mapped via `[project.scripts]` in `pyproject.toml`).

| Command | Description |
|---|---|
| `beautyspot list` | List databases or tasks |
| `beautyspot show <db> <key>` | Inspect a cached task (supports key prefix) |
| `beautyspot stats <db>` | Show cache statistics |
| `beautyspot clear <db>` | Delete all (or specific function) cached tasks |
| `beautyspot clean <db>` | Garbage-collect orphaned blob files |
| `beautyspot prune <db> --days N` | Delete tasks older than N days |
| `beautyspot gc` | Full GC: expired tasks + zombie project cleanup |
| `beautyspot ui <db>` | Launch Streamlit dashboard |
| `beautyspot version` | Show version |

#### `content_types.py` — ContentType

String constants for semantic content types used in `@spot.mark(content_type=...)`. The dashboard uses these to select the appropriate rendering widget.

```python
ContentType.TEXT       # "text/plain"
ContentType.JSON       # "application/json"
ContentType.MARKDOWN   # "text/markdown"
ContentType.PNG        # "image/png"
ContentType.MERMAID    # "text/vnd.mermaid"
# etc.
```

---

## Key Conventions

### DI Principles

All internal components are injected, not hardcoded. The `Spot()` factory in `__init__.py` is the only place that wires defaults. The `core.Spot` class constructor requires all dependencies explicitly. Never instantiate `core.Spot` directly in user code — always use `bs.Spot(...)`.

### Non-blocking Persistence

- `default_wait=True` (default): `_save_result_sync` is called on the calling thread — safe but adds latency.
- `default_wait=False`: `_save_result_safe` is submitted to `ThreadPoolExecutor` — zero latency, but data is not flushed until `with spot:` exits or `shutdown()` is called.
- Individual calls can override with `@spot.mark(wait=False)`.

### Context Manager Usage

```python
with spot:
    result = my_func(args)
# On exit: waits for all pending background saves (does NOT shut down executor)
# The same `spot` instance can be reused in another `with` block.
```

### Cache Key Stability

- Changing a function's name or its `version` string invalidates the cache.
- Argument order in `kwargs` does not affect the key (dicts are sorted).
- Use `keygen=KeyGen.ignore("verbose")` to exclude non-deterministic args.
- `input_key_fn` is deprecated; use `keygen` instead.

### Storage Policy Decision

The storage policy (`save_blob` parameter) precedence:
1. Explicit `save_blob=True/False` on `@spot.mark(...)` or `cached_run(...)`.
2. `storage_policy.should_save_as_blob(data)` if `save_blob=None` (default).

### Deprecations

- `input_key_fn` → use `keygen` (triggers `DeprecationWarning` at decoration time, not call time).
- `run()` method → removed in v2.0; use `@mark` or `cached_run()`.
- `@task` decorator → renamed to `@mark`.
- `Project` class → renamed to `Spot`.

### Error Handling

- Background save failures are logged at ERROR level and do not raise.
- `SerializationError` propagates from synchronous saves.
- `CacheCorruptedError` (in `storage.py`) is raised when blob data cannot be deserialized.

---

## Workspace Directory

`beautyspot` writes all runtime data to `.beautyspot/` in the current working directory:

```
.beautyspot/
├── .gitignore      # Contains "*" — entire directory is gitignored
├── {name}.db       # SQLite database for a Spot named "name"
└── blobs/
    └── {name}/     # Blob files for a Spot named "name"
        └── {cache_key}.bin
```

This directory is auto-created and should never be committed to git.

---

## Testing Guidelines

### Test Layer Selection

| Scenario | Layer |
|---|---|
| New function/class logic only | `tests/unit/` |
| New `Spot` option, DB operation, or storage | `tests/integration/` |
| Bug fix (regression), user workflow, security | `tests/senarios/` |
| Deprecated parameter still emits warning and works | `tests/migration/` |
| Type inference correctness | `tests/typing/` |

### Fixture: `inspect_db`

Defined in `tests/conftest.py`. A factory fixture that returns all rows from a test SQLite DB as a list of dicts. Use it to assert DB state directly after cache operations.

```python
def test_something(inspect_db, tmp_path):
    db_path = tmp_path / "test.db"
    # ... run spot operations ...
    rows = inspect_db(db_path)
    assert rows[0]["func_name"] == "my_func"
```

### Integration Test Pattern

Integration tests typically use `tmp_path` to isolate the workspace:

```python
import beautyspot as bs

def test_basic_cache(tmp_path):
    spot = bs.Spot(name="test", db=bs.SQLiteTaskDB(tmp_path / "t.db"),
                   storage_backend=bs.LocalStorage(tmp_path / "blobs"))
    @spot.mark()
    def fn(x): return x * 2

    assert fn(3) == 6
    assert fn(3) == 6  # cache hit
```

---

## Optional Dependencies

| Extra | Packages | Use case |
|---|---|---|
| `beautyspot[s3]` | `boto3` | S3Storage backend |
| `beautyspot[dashboard]` | `pandas`, `streamlit`, `watchdog`, `graphviz` | Streamlit UI |
| `beautyspot[all]` | All of the above | Everything |

---

## Versioning & Release

- Version is derived from git tags (`hatch-vcs`): tag `v2.5.2` → version `2.5.2`.
- Version is written to `src/beautyspot/_version.py` at build time.
- Release workflow: `make release` (runs `pypi-publish` then pushes the git tag).
- Requires `.env` file with `PYPI_TOKEN` (or `TEST_PYPI_TOKEN` for test releases).

---

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

1. **`ruff-check`**: Linting (astral-sh/ruff).
2. **`detect-secrets`**: Prevents committing secrets (baseline in `.secrets.baseline`).
3. **`check-added-large-files`**: Rejects files > 500 KB.

Run all hooks manually: `pre-commit run --all-files`

---

## ADR Index (Architecture Decision Records)

Key decisions in `docs/adr/`:

| ADR | Topic |
|---|---|
| 0001 | Stable argument hashing |
| 0003 | Resilient deserialization and versioning |
| 0007 | Customizable serialization with msgpack |
| 0008 | Database dependency injection |
| 0009 | Msgpack everywhere and guardrails |
| 0013 | Decorator-based type registration |
| 0023 | Non-blocking persistence and task tracking |
| 0025 | Factory function for default DI |
| 0028 | Recursive cleanup and zombie collection |
| 0029 | Declarative storage policy |
| 0030 | Declarative lifecycle policy |

---

## Common Tasks for AI Assistants

### Adding a new `@mark` option

1. Add the parameter to `Spot.mark()` in `core.py:594`.
2. Thread it through `_execute_sync` and `_execute_async`.
3. Update `Spot.cached_run()` and `ScopedMark.__init__` if it applies to `cached_run`.
4. Update the factory in `__init__.py` if it needs a Spot-level default.
5. Add unit tests in `tests/unit/` and integration tests in `tests/integration/core/`.

### Adding a new storage backend

1. Subclass `BlobStorageBase` in `storage.py` (implement `save`, `load`, `delete`, `list_keys`).
2. Update `create_storage()` factory in `storage.py` if it should be auto-detected by URI scheme.
3. Add optional import guard (like `S3Storage` does with `boto3`).
4. Add integration tests in `tests/integration/storage/`.

### Adding a new CLI command

1. Add `@app.command("name")` in `cli.py`.
2. Use `get_service(db_path)` to obtain a `MaintenanceService`.
3. Use `rich` `Console`, `Table`, `Panel` for output formatting.
4. Add tests in `tests/integration/cli/`.

### Custom type serialization

```python
@spot.register(
    code=1,  # unique 0-127 int
    encoder=lambda df: {"data": df.to_dict(orient="list"), "columns": list(df.columns)},
    decoder=lambda d: pd.DataFrame(d["data"], columns=d["columns"]),
)
class MyDataFrame(pd.DataFrame):
    pass
```

Or use `spot.register_type(MyClass, code, encoder, decoder)` imperatively.
