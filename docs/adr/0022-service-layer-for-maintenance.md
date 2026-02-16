# 22. Service Layer for Maintenance Operations

* Status: Proposed
* Date: 2026-02-16

## Context

Currently, `src/beautyspot/cli.py` contains significant business logic for:
1.  **Pruning**: Deleting old tasks based on timestamps.
2.  **Cleaning**: Identifying and deleting orphaned blob files (garbage collection).

This logic directly accesses the `sqlite3` driver and manipulates file paths, bypassing the `TaskDB` and `BlobStorageBase` abstractions. This leads to:
* **Coupling**: CLI is tightly coupled to SQLite and local file storage details.
* **Duplication**: If we want to run maintenance from a script or Web UI, we must duplicate this logic.
* **Inconsistency**: S3 storage support for "cleaning" is missing because logic is hardcoded for local paths.

## Decision

We will move the maintenance logic from `cli.py` to `core.py` (specifically the `Spot` class), transforming `Spot` into a unified Service Facade.

To support this, we will extend the lower-level interfaces:
* **`TaskDB`**: Add `prune(older_than)` and `get_blob_refs()` methods.
* **`BlobStorageBase`**: Add `list_keys()` method to allow iterating over stored objects.

## Consequences

### Positive
* **Testability**: Core logic can be unit-tested without invoking the CLI.
* **Reusability**: Pruning/Cleaning can be triggered programmatically.
* **Abstraction**: S3 and other storage backends will automatically support garbage collection if they implement `list_keys`.

### Negative
* **Interface Change**: `TaskDB` and `BlobStorageBase` interfaces expand, requiring updates to all implementations.

