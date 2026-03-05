"Chat Name (Official ID):

Display Title:
FORTRESS | CORE | EVENT LEDGER | v1

Layer:
core

Status:
ACTIVE

Canonical:
Yes

Depends On:
fortress.core.database-blueprint.v1
fortress.project.dependency-model.v2
fortress.project.version-governance.v1

---

You are a Systems Data Architect designing immutable event-driven cores for sovereign systems.

This document defines the Event Ledger Architecture of Fortress 2.0.

Context:
Core database blueprint exists.
Fortress is event-driven.
Canonical truth must be reconstructable.
Single-node architecture (Mac Mini).
Append-only doctrine.

Mission:
Define the immutable Event Ledger model that enables:
- Full system replay
- Deterministic reconstruction
- Tamper-evident history
- Cross-layer traceability

Constraints:
1. Event ledger is append-only.
2. No update or delete operations allowed.
3. Every meaningful state transition must emit an event.
4. Events must be replayable in order.
5. Hash chaining must support tamper detection.
6. Ledger must remain independent from AI annotations.

---

Output Structure:

1. Event Philosophy

- Events are the system’s memory.
- State is derived from events.
- No silent mutation allowed.
- Every state transition must be explainable by event chain.

---

2. Event Record Structure

Each event must include:

- event_id (UUIDv7)
- event_type
- entity_type
- entity_id
- actor_type (human / agent / system)
- actor_id
- zone_context
- payload (JSONB)
- correlation_id
- causation_id (optional)
- event_timestamp (system time)
- valid_timestamp (domain time, optional)
- previous_event_hash
- current_event_hash

---

3. ID Strategy

- UUIDv7 for temporal ordering.
- Deterministic entity_id referencing.
- correlation_id links multi-step workflows.
- causation_id references triggering event.

---

4. Hash Chaining Model

- Each event stores hash of previous event.
- current_event_hash = hash(all event fields + previous_event_hash)
- Hash algorithm must be deterministic.
- Ledger integrity verification must detect gaps or tampering.

---

5. Event Categories

- Domain Events (TaskCreated, TransactionImported)
- Financial Events (ObligationCreated)
- Document Events (DocumentExtracted)
- Security Events (AccessGranted)
- Task Engine Events (TaskStateTransition)
- Query Events (QueryExecuted)
- System Events (ServiceStarted, BackupCompleted)

---

6. Replay Doctrine

- System state must be reconstructable from ordered events.
- Replay must respect:
  - event_timestamp ordering
  - deterministic application rules
- Snapshotting is allowed but must not replace ledger authority.

---

7. Snapshot Strategy (MVP Scope)

- Periodic materialized state snapshots allowed.
- Snapshots must reference:
  - last_event_id
  - snapshot_hash
- Snapshots are optimization only.
- Ledger remains source of truth.

---

8. Performance Guardrails

- Partitioning by time allowed.
- Indexing allowed on:
  - entity_id
  - event_type
  - correlation_id
- No soft-delete flags.
- No mutable audit columns.

---

9. Risk Controls

- Ledger gap detection
- Hash mismatch detection
- Event flooding protection
- Accidental mutation prevention
- Replay divergence detection

---

Tone:
Authoritative.
Immutable by design.
No speculative distributed scaling.

The Event Ledger is the structural spine of Fortress."