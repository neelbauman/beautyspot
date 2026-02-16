# 25. Factory Function for Default Dependency Injection

Date: 2024-02-17

## Status

Accepted

## Context

In v2.0, `beautyspot` adopted a Dependency Injection (DI) architecture. The `Spot` class (in `core.py`) requires explicit instances of `TaskDB`, `Serializer`, and `Storage` for initialization.

While this is excellent for testability and flexibility, it creates a verbose API for end-users who just want a "quick start" experience:

```python
# Too verbose for simple scripts
db = SQLiteTaskDB(...)
storage = LocalStorage(...)
serializer = MsgpackSerializer()
spot = Spot(name="app", db=db, storage=storage, serializer=serializer)

```

## Decision

We decided to expose a **factory function** named `Spot` in `beautyspot/__init__.py`, which constructs the underlying `_Spot` class with sensible default implementations.

```python
def Spot(name: str, db=None, ...):
    resolved_db = db or SQLiteTaskDB(...)
    return _Spot(name, db=resolved_db, ...)

```

## Consequences

* **Positive**: **"Opinionated Defaults, Flexible Internals"**. Beginners get a one-liner initialization, while advanced users can still inject custom components.
* **Positive**: Keeps the core `_Spot` class pure and free from default implementation details (it doesn't need to import `SQLiteTaskDB`).
* **Negative**: Users cannot easily subclass `Spot` because the public symbol is a function, not a class. If inheritance is needed, they must import `_Spot` (aliased) from `core`. We consider composition preferable to inheritance for this library, so this is an acceptable trade-off.

