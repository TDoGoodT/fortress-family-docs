# fortress.ingestion.pipeline-architecture.v2 — PATCH (changed sections only)

## Delta From v1 (UPDATED)
- Introduces deterministic ingestion data contracts: Raw, Normalized, Canonical Handoff Request, Error.
- Introduces explicit idempotency primitives (hash definitions + unique constraints).
- Introduces canonical stage model with transition conditions.
- Introduces mandatory event taxonomy for ingestion transitions with correlation and causation policy.
- Introduces trace policy: run_id, source_id, object_id, record_id propagation across tables and events.
- Normalizes UUIDv7 generator naming to `uuid_v7()` (global Core consistency).
- Adds Event Ledger field mapping to actual Phase 1 column names.
- Normalizes `zone_context` encoding and reconciles Phase 1 legacy values without rewrite.
- Adds explicit DB Zone Placement (schema-to-zone mapping and allowed cross-zone flows).
- Makes run_state sequencing determiniic (`state_seq` contract).

---

## 1) Canonical Tables Specification (DB migrations 006+) — DEFAULTS PATCH

### 1.1 ingestion.source (DEFAULT UPDATED)
- source_id: uuid, not null, default uuid_v7()

### 1.2 ingestion.run (DEFAULT UPDATED)
- run_id: uuid, not null, default uuid_v7()

### 1.3 ingestion.run_state (DEFAULT UPDATED)
- run_state_id: uuid, not null, default uuid_v7()

### 1.4 ingestion.raw_object (DEFAULT UPDATED)
- raw_object_id: uuid, not null, default uuid_v7()

### 1.5 ingestion.raw_record (DEFAULT UPDATED)
- raw_record_id: uuid, not null, default uuid_v7()

### 1.6 ingestion.normalized_record (DEFAULT UPDATED)
- normalized_record_id: uuid, not null, default uuid_v7()

### 1.7 ingestion.canonical_handoff_request (DEFAULT UPDATED)
- handoff_request_id: uuid, not null, default uuid_v7()

### 1.8 core.canonical_handoff_receipt (DEFAULT UPDATED)
- handoff_receipt_id: uuid, not null, default uuid_v7()

### 1.9 ingestion.error (DEFAULT UPDATED)
- ingestion_error_id: uuid, not null, default uuid_v7()

---

## 5) Event Emission Spec — LEDGER FIELD MAPPING (NEW)

### 5.X Ledger Field Mapping (Spec v1 terms → Phase 1 DB columns)
This section is authoritative for deterministic implementation.

- `entity_type` (spec) = `aggregate_type` (event_ledger column)
- `entity_id` (spec) = `aggregate_id` (event_ledger column)
- `event_timestamp` (spec) = `event_timestamp` (event_ledger column, authoritative time of event)
- `created_at` (event_ledger column) = write-time metadata, NOT authoritative for event time

Rule:
- Consumers MUST treat `event_timestamp` as authoritative for ordering and temporal semantics.
- `created_at` is retained for operational diagnostics only.

---

## 5) Event Emission Spec — ZONE CONTEXT NORMALIZATION (PATCH)

### 5.1 Event Envelope Requirements (UPDATED)
All ingestion events must be written to core.event_ledger with:
- actor_type: system
- actor_id: 'ingestion'
- zone_context: see “Zone Context Encoding” below
- correlation_id policy: correlation_id = run_id for run-scoped events; correlation_id = raw_record_id / normalized_record_id / handoff_request_id for record-scoped events
- causation_id policy:
  - for state transitions: causation_id = previous state transition event_id (same run)
  - for record transitions: causation_id = prior stage event_id for that record, else null

### 5.Y Zone Context Encoding (NEW)
Canonical encoding going forward:
- zone_context ∈ { 'ZONE_A', 'ZONE_B', 'ZONE_C' }

Reconciliation rule (no Phase 1 history rewrite):
- Existing Phase 1 rows may contain zone_context = 'core' (legacy).
- Legacy value 'core' remains unchanged in-place.
- Interpretation for governance and audits:
  - 'core' is treated as “LEGACY_CORE”, semantically equivalent to Zone A for Phase 1 scope, but not a valid canonical encoding for new writes.
- From migrations 006+ onward:
  - ingestion pipeline writes must use 'ZONE_C'
  - Zone A receipt writes must use 'ZONE_A'

---

## 6) DB Zone Placement (NEW)

### 6.X DB Zone Placement and Allowed Flows (Authoritative)
Schema-to-zone mapping:
- Schema `ingestion.*` tables are Zone C.
- Schema `core.*` tables are Zone A, including:
  - core.event_ledger (spine)
  - core.canonical_handoff_receipt (Zone A receipt)

Allowed flows (single DB, strict discipline):
- Zone C may append:
  - ingestion.* tables
  - core.event_ledger events with zone_context = 'ZONE_C'
- Zone C may NOT write to any Zone A canonical aggregates (out of scope for Phase 2A/2B).
- Zone A may append:
  - core.canonical_handoff_receipt
  - core.event_ledger events with zone_context = 'ZONE_A'
- Cross-zone linkage constraints:
  - ingestion.canonical_handoff_request may be referenced by core.canonical_handoff_receipt via handoff_request_id (receipt is the controlled transfer acknowledgment).
  - Only the receipt may reference applied_event_id, and it must point to an event_ledger row (event_id) representing the canonical application event in Zone A.

---

## 4) Canonical Stage Transitions — RUN STATE SEQUENCING (NEW)

### 4.X Run State Sequencing (Authoritative)
- `state_seq` assignment is deterministic:
  - starts at 1 per run_id
  - increments by exactly 1 for each new state row
  - no gaps permitted
- If an implementation attempts to insert a state with a non-next `state_seq`, it must fail the transition and record ingestion.error with:
  - stage = 'RUN_STATE'
  - error_class = 'INTEGRITY_FAILED'
  - is_retryable = false

---

## Version Metadata (authoritative)
- Document ID: fortress.ingestion.pipeline-architecture
- Version: v2
- Layer: ingestion
- Status: ACTIVE
- Canonical: Yes
- Supersedes: fortress.ingestion.pipeline-architecture.v1
- Depends On:
  - fortress.core.database-blueprint.v1
  - fortress.core.event-ledger.v1
  - fortress.security.zone-model.v1
  - fortress.project.implementation-roadmap.v2
  - fortress.project.dependency-model.v1
  - fortress.project.version-governance.v1

---

## Governance Alignment Addendum (v2.0.1, canonical for Phase 2B execution)

### A) event_ledger physical placement (Phase 2 reality)
- The authoritative Event Ledger table remains **public.event_ledger** for Phase 2.
- References to `core.event_ledger` in older terminology are conceptual only.
- Ledger field mapping remains valid because it targets the actual Phase 1 columns in **public.event_ledger**.

### B) Hash storage encoding (idempotency primitives)
- DB storage type for SHA-256 digests: **bytea** (using `pgcrypto.digest(..., 'sha256')`).
- External / human representation: **hex string char(64)** derived via `encode(hash_bytea, 'hex')`.
- Canonical unique constraints and duplicate detection operate on the **bytea** value.

### C) run_state sequencing enforcement (deterministic + no side effects)
- The database MUST reject any non-next `state_seq` insert by raising an exception.
- The ingestion runtime (not part of Phase 2B DB-only scope) is responsible for recording `ingestion.error` rows explicitly after a failed transition attempt.
- This avoids hidden side effects inside triggers while preserving deterministic failure semantics.
