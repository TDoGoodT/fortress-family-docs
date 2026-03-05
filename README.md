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
