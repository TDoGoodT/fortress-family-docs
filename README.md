# Fortress 2.0

Fortress is a sovereign, local-first family intelligence system.

The system provides deterministic data ingestion, auditable event history,
and structured domain models for managing household knowledge, documents,
finances, and operational workflows.

Core principles:

- Deterministic architecture
- Event-ledger as the system spine
- Idempotent ingestion pipeline
- Layered security zones
- Reproducible database migrations

## Architecture Layers

- core – canonical data structures and event ledger
- ingestion – deterministic ingestion pipeline
- ai – annotation, embeddings, anomaly detection
- security – zone model and access boundaries
- project – governance and dependency rules

## Infrastructure

Database: PostgreSQL  
Migration model: deterministic SQL migrations  
Execution: `infra/db/apply_migrations.sh`

## Status

Phase 2C complete.

Current capabilities:

- Event Ledger with hash chain
- Idempotent ingestion constraints
- Deterministic event - Controlled migration runner

Next phase: domain projections and consumers.


## Controlled Filesystem Inbox Intake (Manual Debugging)

Fortress supports a controlled local filesystem inbox intake command for deterministic ingestion boundary testing.

- Command: `infra/runtime/intake_filesystem_inbox.sh [inbox_path]`
- Default inbox path: `~/FortressInbox` (or `FORTRESS_INBOX_PATH`)
- Required env: `FORTRESS_RAW_STORAGE_DIR` (existing approved raw storage directory)

Behavior:

- Inbox is an external intake surface and must remain outside Fortress storage trees.
- Files are copied (never moved) to raw storage, then registered through existing `ingestion.*` contracts.
- `object_locator` is the external inbox file path (`filesystem://...`).
- Zero-file polls do not create an ingestion run.
- Event emission is operator-triggered after intake (`infra/runtime/emit_ingestion_events.sh <run_id>`).

Example:

```bash
export FORTRESS_RAW_STORAGE_DIR="$HOME/fortress_raw"
infra/runtime/intake_filesystem_inbox.sh "$HOME/FortressInbox"
```
