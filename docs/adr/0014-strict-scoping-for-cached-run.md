# 14. Strict Scoping for Imperative Execution (Runtime Guard)

Date: 2026-02-01
Status: Accepted

## Context

The `spot.cached_run()` context manager allows users to temporarily apply caching behavior to functions. 
However, due to Python's scoping rules for `with` statements, variables bound within the block (e.g., `with ... as task:`) remain accessible after the block exits.

This creates a risk where users might inadvertently reuse a function wrapper that has specific context-bound configurations (like `version="v1"` or temporary storage settings) outside of that intended context, leading to subtle bugs or resource leaks.

## Decision

We will implement a **Runtime Guard** pattern for the `ScopedMark` context manager.

1.  **State Tracking**: The context manager will maintain an active state flag.
2.  **Wrapper Guard**: The functions returned by `cached_run` will be wrapped in a guard that checks this flag before execution.
3.  **Fail Fast**: If a wrapped function is called outside the `with` block, it will immediately raise a `RuntimeError`.

## Consequences

### Positive
* **Safety**: Eliminates the risk of using "stale" or "context-specific" wrappers outside their intended scope.
* **Clarity**: Enforces the mental model that the "caching magic" is strictly temporary.
* **Resource Management**: Makes it safer to use `spot` instances that might be short-lived or injected, as the function references become invalid immediately after use.

### Negative
* **Runtime Overhead**: Adds a negligible check (boolean flag access) to every function call within the block.
* **Complexity**: The `ScopedMark` implementation becomes slightly more complex due to the additional wrapper layer.

