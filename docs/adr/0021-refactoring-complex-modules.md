# 21. Refactoring Complex Modules with Single Dispatch

* Status: Accepted
* Date: 2026-02-16

## Context

The `quality_report` highlighted that `src/beautyspot/cachekey.py` has a high Cyclomatic Complexity (Rank D), specifically in the `canonicalize` function. This function uses a long chain of `if-elif-else` statements checking for various types (`dict`, `list`, `set`, `numpy`, `type`, etc.) to normalize objects for hashing.

This structure violates the Open-Closed Principle: adding support for a new type requires modifying the core function, increasing the risk of regression.

## Decision

We will refactor `canonicalize` using Python's standard library `functools.singledispatch`.

* **Default Dispatch**: Handles primitives, fallback logic (`str`), and duck-typing checks (e.g., Numpy arrays, objects with `__dict__`).
* **Registered Handlers**: Specific logic for `dict`, `list`, `tuple`, `set`, `frozenset`, and `type` will be moved to decorated functions.

## Consequences

### Positive
* **Reduced Complexity**: The main function logic is split into smaller, focused handlers.
* **Extensibility**: Future types can be supported by registering new handlers without changing existing code.
* **Readability**: Each handler focuses on a single type responsibility.

### Negative
* **Duck Typing Limitation**: `singledispatch` relies on types. Duck typing logic (like checking for `.shape` on Numpy-like objects) must still reside in the default handler or a base checking layer.

