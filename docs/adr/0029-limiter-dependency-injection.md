# 29. Limiter Dependency Injection

Date: 2026-02-18

## Status

Accepted

## Context

Previously, the `Spot` class in `core.py` was tightly coupled with the `TokenBucket` implementation. It accepted a `tpm` (tokens per minute) integer argument and instantiated the `TokenBucket` internally.

This design had several limitations:
1.  **Testing**: Unit tests were slow because they relied on real `time.sleep` calls within `TokenBucket`.
2.  **Extensibility**: Users could not provide custom rate limiters (e.g., Redis-based distributed limiters) or different algorithms.
3.  **Separation of Concerns**: `core.Spot` was managing the lifecycle and configuration of the limiter, which violated the Single Responsibility Principle.

## Decision

We decided to decouple the rate limiter from `core.Spot` using Dependency Injection (DI).

1.  **Protocol Definition**: Define a `LimiterProtocol` in `beautyspot.limiter` that mandates `consume(cost: int)` and `consume_async(cost: int)` methods.
2.  **Explicit Inheritance**: The default `TokenBucket` implementation will explicitly inherit from `LimiterProtocol` to ensure type safety and clarity.
3.  **Injection**: Modify `core.Spot.__init__` to accept a `limiter: LimiterProtocol` instance instead of `tpm`.
4.  **Factory Responsibility**: The `Spot` factory function in `__init__.py` will handle the creation of the default `TokenBucket` if no custom limiter is provided.
5.  **Isolation**: The limiter will not share the `Executor` or `io_workers` with `Spot`. If a limiter requires background threads (e.g., for network I/O), it must manage its own resources or receive them via its own DI.

## Consequences

* **Positive**: **Testability**. We can now inject a `MockLimiter` or `NoOpLimiter` during tests to eliminate sleep times.
* **Positive**: **Flexibility**. Users can implement custom limiters (e.g., sliding window, external stores) without modifying the core logic.
* **Positive**: **Clean Core**. `core.Spot` is simplified as it no longer handles rate limiter initialization.
* **Negative**: The signature of the internal class `_Spot` changes, breaking any code that instantiated it directly (though `Spot` factory usage remains compatible).

