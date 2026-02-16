# 22. Service Layer for Maintenance Operations

* Status: Accepted
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

We will extract the maintenance logic from `cli.py` into a dedicated service layer, **`MaintenanceService`** (`src/beautyspot/maintenance.py`).

Instead of adding these responsibilities to the `Spot` class (which focuses on runtime execution context and caching), we separate the concerns:

* **`MaintenanceService`**: Handles administrative tasks such as pruning records, cleaning orphaned blobs, and querying history. It orchestrates `TaskDB` and `BlobStorageBase`.
* **`Spot`**: Remains focused on `mark` (registration) and `cached_run` (execution) for the application runtime.

Both classes will share the underlying `TaskDB` and `BlobStorageBase` abstractions.

## Consequences

### Positive
* **Separation of Concerns**: The runtime logic (`Spot`) is kept lightweight and focused, while administrative logic resides in its own service.
* **Testability**: Core maintenance logic can be unit-tested without invoking the CLI.
* **Reusability**: Pruning/Cleaning can be triggered programmatically from other scripts or the dashboard.
* **Abstraction**: S3 and other storage backends will automatically support garbage collection if they implement `list_keys`.

### Negative
* **Interface Expansion**: `TaskDB` and `BlobStorageBase` interfaces need to expand to support maintenance operations (e.g., `list_keys`, `get_blob_refs`), affecting all backend implementations.

