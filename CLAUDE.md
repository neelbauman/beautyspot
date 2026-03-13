# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`beautyspot` is a Python OSS library that transparently caches function execution results and accelerates re-execution of complex data pipelines and ML experiments. Published on PyPI as `beautyspot`.

- **Python**: >=3.12 | **Package manager**: `uv` | **Build**: `hatchling` + `hatch-vcs`
- **Public entry point**: `bs.Spot(...)` — factory function that wires all components via DI

## Development Commands

```bash
# Always use uv, never bare python3
make install        # uv sync --all-groups
make test           # pytest + pyright typing tests
make test-unit      # pytest only
make test-typing    # pyright tests/typing
make lint           # ruff check .
make lint-fix       # ruff check . --fix
make format         # ruff format .
make audit          # radon cyclomatic complexity + maintainability
make build          # clean → test → uv build
make docs-serve     # MkDocs local preview
```

Single test: `uv run pytest tests/unit/test_foo.py::test_bar -x -q`

## Architecture

```
bs.Spot() [__init__.py]      ← Factory function (DI wiring, the ONLY public entry point)
    │
    ▼
core.Spot [core.py]          ← Main caching engine
    ├── cache           CacheManager        (CRUD + Thundering Herd protection)
    ├── db              TaskDBBase          (metadata + cache lookup; default: SQLiteTaskDB)
    ├── serializer      SerializerProtocol  (default: MsgpackSerializer)
    ├── storage_backend BlobStorageBase     (default: LocalStorage; also S3Storage)
    ├── storage_policy  StoragePolicyProtocol
    ├── limiter         LimiterProtocol     (default: TokenBucket, GCRA algorithm)
    ├── lifecycle_policy LifecyclePolicy
    └── executor        ThreadPoolExecutor  (background IO)
```

### Key Design Principles

- **DI Everywhere**: All components are protocols/interfaces. `__init__.py:Spot()` is the **only** place that wires defaults. Never instantiate `core.Spot` directly.
- **Non-blocking Persistence**: `wait=True` (default) saves on calling thread. `wait=False` submits to `ThreadPoolExecutor`, flushed on `with spot:` exit. Background failures log at ERROR, never raise.
- **Cache Key Stability**: Function `__name__` + `version=` string define cache identity. `kwargs` order is irrelevant (sorted before hashing). Use `keygen=KeyGen.ignore("verbose")` to exclude args.
- **Context Manager**: `with spot:` waits for pending background saves but does NOT shut down the executor — the instance is reusable.

## Testing

### Layer Selection

| Scenario | Directory |
|---|---|
| Pure logic, no I/O | `tests/unit/` |
| Spot options, DB/storage operations | `tests/integration/` |
| User workflows, security, edge cases | `tests/scenarios/` |
| Deprecated param backward compat | `tests/migration/` |
| Type inference correctness (pyright) | `tests/typing/` |

### Key Fixture

`inspect_db(db_path)` in `tests/conftest.py` — queries SQLite directly, returns `list[dict]` of all rows. Use it to assert DB state after cache operations.

### Integration Test Pattern

```python
import beautyspot as bs

def test_cache(tmp_path):
    spot = bs.Spot(
        name="test",
        db=bs.SQLiteTaskDB(tmp_path / "t.db"),
        storage_backend=bs.LocalStorage(tmp_path / "blobs"),
    )
    @spot.mark()
    def fn(x): return x * 2

    assert fn(3) == 6   # cache miss → execute
    assert fn(3) == 6   # cache hit
```

## Common Tasks

### Adding a new `@mark` option

1. Add parameter to `Spot.mark()` in `core.py`
2. Thread through `_execute_sync` and `_execute_async`
3. Update `_resolve_settings` if it needs a Spot-level default
4. Update `Spot.cached_run()` if applicable
5. Update factory in `__init__.py` if it needs a constructor-level default
6. Tests: `tests/unit/` for logic, `tests/integration/core/` for end-to-end

### Adding a new storage backend

1. Subclass `BlobStorageBase` in `storage.py` (implement `save`, `load`, `delete`, `list_keys`)
2. Update `create_storage()` factory for auto-detection by URI scheme
3. Guard optional imports (see `S3Storage` / `boto3` pattern)
4. Tests: `tests/integration/storage/`

### Adding a new CLI command

1. Add `@app.command("name")` in `cli.py`
2. Use `get_service(db_path)` to get a `MaintenanceService`
3. Use `rich` Console/Table/Panel for output
4. Tests: `tests/integration/cli/`

## Deprecations

| Old | New | Status |
|---|---|---|
| `input_key_fn` | `keygen` | DeprecationWarning at decoration time |
| `@task` | `@mark` | Alias maintained |
| `Project` | `Spot` | Alias maintained |
| `run()` | `@mark` / `cached_run()` | Removed in v2.0 |

## Specification-Driven Development

This project uses Doorstop for traceability (REQ → SPEC → IMPL → TST). Documents are in `specification/`. See `.claude/DEV_LIFECYCLE.md` for the full 7-phase workflow.

## Communication

Respond in Japanese. When proposing architectural changes, present alternatives with tradeoffs and suggest creating an ADR in `docs/adr/`.

## Additional Context

- `.claude/REVIEW.md` — Known design concerns (DC-1 through DC-10)
- `AGENTS.md` — Agent behavior guidelines and coding rules
