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

Baseline status: partially verified.

Authoritative verified state:

- `architecture/_meta/fortress.current-state.verified.v1.md`

Current capabilities:

- Event Ledger with hash chain
- Idempotent ingestion constraints
- Deterministic migration runner from a clean database
- Canonical projections and query views for document, person, task, and account

Known limitations:

- Ledger integrity diagnostics currently report 5 hash-chain mismatches under investigation
- Controlled filesystem inbox intake currently stops at `ingestion.run` / `ingestion.raw_object`
- No automatic filesystem path currently creates `raw_record`, `normalized_record`, or canonical handoff rows

## Recommended Reading Order

1. `architecture/_meta/fortress.current-state.verified.v1.md`
2. `architecture/_meta/version-matrix.md`
3. `architecture/core/fortress.core.event-ledger.v1.md`
4. `architecture/ingestion/fortress.ingestion.pipeline-architecture.v3.md`
5. `architecture/project/fortress.project.dependency-model.v2.md`
6. `README.md`


## Controlled Filesystem Inbox Intake (Manual Debugging)

Fortress supports a controlled local filesystem inbox intake command for deterministic ingestion boundary testing.

- Command: `infra/runtime/intake_filesystem_inbox.sh [inbox_path]`
- Default inbox path: `~/FortressInbox` (or `FORTRESS_INBOX_PATH`)
- Required env: `FORTRESS_RAW_STORAGE_DIR` (existing approved raw storage directory)

Behavior:

- Inbox is an external intake surface and must remain outside Fortress storage trees.
- Files are copied (never moved) to raw storage, then registered as `ingestion.raw_object`.
- `object_locator` is the external inbox file path (`filesystem://...`).
- Zero-file polls do not create an ingestion run.
- Event emission is operator-triggered after intake (`infra/runtime/emit_ingestion_events.sh <run_id>`).
- Intake does not currently perform raw-record extraction, normalization, or handoff creation.

Example:

```bash
export FORTRESS_RAW_STORAGE_DIR="$HOME/fortress_raw"
infra/runtime/intake_filesystem_inbox.sh "$HOME/FortressInbox"
```
