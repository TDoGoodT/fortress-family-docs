"Document ID: fortress.project.execution-plan-to-production
Version: v1
Layer: project
Status: DRAFT
Canonical: No
Purpose: Master-Control execution plan derived from current repository state.

## 0) Governance Preamble (Master-Control V4 Conditions)

Mandatory rules for every stage and micro-scope:
- Every deliverable must reference canonical source documents by ID + version.
- No in-place mutation of `public.event_ledger` history (append-only invariant).
- No in-place mutation of historical canonical truth; corrections must be appended as events.
- No alternate processor paths per aggregate; exactly one authoritative processor.
- Stage progression requires evidence pack: commands, outputs, diffs, acceptance checklist.
- Legacy/deprecated scripts must be blocked or archived before executing a new stage.

Global architecture references:
- `fortress.project.master-control.v1`
- `fortress.project.dependency-model.v2`
- `fortress.project.version-governance.v1`
- `fortress.project.implementation-roadmap.v2`
- `fortress.project.qa-governance.v1`

## 1) Current Repository Reality (Observed)

- Architecture corpus exists across core / ingestion / ai / security / infra / project.
- Database-first implementation exists under `infra/db` with deterministic SQL migrations (001-033).
- Runtime scripts exist for migration, ledger integrity, handoff processing, projection consistency checks, and deterministic aggregate rebuild.
- `README.md` declares `Phase 2C complete`; next focus is projections and consumers.

Operational interpretation:
- Foundations + event-ledger + deterministic ingestion contracts are materially in place.
- Core aggregate paths exist for document/person/task; account readiness must be explicitly validated before Stage B account execution.
- Query Interface v2, Household Orchestrator, and Security hardening remain execution phases, not fully completed product surfaces.

## 2) Production Path (Master-Control Approval Gates)

### Stage A — Baseline Verification (must pass before new feature work)

Source docs (ID + version):
- `fortress.core.event-ledger.v1`
- `fortress.core.database-blueprint.v1`
- `fortress.project.qa-governance.v1`
- `fortress.project.dependency-model.v2`

Goal:
- Prove environment reproducibility and deterministic baseline integrity.

Execution:
1. Apply migrations on clean DB using controlled runner.
2. Run ledger integrity diagnostics (hash-chain, envelope, zone violations).
3. Run projection consistency checks for account/person/document/task.
4. Run deterministic rebuild checks from ledger for each aggregate.
5. Archive/block deprecated runtime scripts before continuing.

Monitoring commands (minimum evidence set):
- `infra/db/apply_migrations.sh`
- `infra/runtime/check_ledger_integrity.sh`
- `infra/runtime/check_account_projection_consistency.sh`
- `infra/runtime/check_person_projection_consistency.sh`
- `infra/runtime/check_projection_consistency.sh`
- `infra/runtime/check_task_projection_consistency.sh`
- `infra/runtime/rebuild_core_account_from_ledger.sh`
- `infra/runtime/rebuild_core_person_from_ledger.sh`
- `infra/runtime/rebuild_core_document_from_ledger.sh`
- `infra/runtime/rebuild_core_task_from_ledger.sh`

Master approval gate A:
- All diagnostics pass with zero invariant violations.
- Legacy/deprecated script hygiene confirmed.

What NOT to do:
- No feature additions.
- No schema redesign.

---

### Stage B — Canonical Domain Completion for MVP Cut

Source docs (ID + version):
- `fortress.core.account-domain.v1`
- `fortress.core.document-domain.v1`
- `fortress.core.task-domain.v1`
- `fortress.core.event-ledger.v1`
- `fortress.project.implementation-roadmap.v2`

Goal:
- Close any missing canonical aggregate paths required by MVP locked scope.

Precondition (Master condition):
- `core.account` operational validation must be closed before account-slice execution in this stage.

Execution:
1. Validate parity per aggregate: contract view → processor → projection → consistency check.
2. Validate receipt-based idempotency under re-processing.
3. Add/verify invariant checks for append-only + hash-chain behavior.
4. Preserve single authoritative processor per aggregate.

Monitoring commands (minimum evidence set):
- Aggregate processor scripts (`infra/runtime/process_*_handoffs.sh`)
- Projection consistency checks per aggregate
- Ledger integrity diagnostics

Master approval gate B:
- Each MVP aggregate has exactly one authoritative processor path.
- No alternate write paths into canonical entities.
- `core.account` readiness evidence accepted.

What NOT to do:
- No orchestrator persona logic yet.
- No UX expansion.

---

### Stage C — Query Interface v2 Read Surfaces

Source docs (ID + version):
- `fortress.ai.query-interface.v2`
- `fortress.security.access-control.v2`
- `fortress.project.dependency-model.v2`

Goal:
- Expose governed session-aware read interfaces for canonical and derived data.

Execution:
1. Implement read contracts/views aligned with Query Interface v2.
2. Enforce session-scoped authorization boundaries.
3. Add integration checks proving no direct storage bypass from agent paths.
4. Keep runtime behavior read-only relative to canonical state for this stage.

Monitoring commands (minimum evidence set):
- Query interface integration checks
- Access-control boundary checks (allow/deny)
- Ledger/projection consistency checks (no regression)

Master approval gate C:
- All reads flow through governed query interfaces.
- Security denies out-of-scope sessions.

What NOT to do:
- No messaging channels.
- No multi-agent orchestration.

---

### Stage D — Household Orchestrator (MVP-safe slice)

Source docs (ID + version):
- `fortress.openclaw.household-orchestrator.v1`
- `fortress.security.access-control.v2`
- `fortress.ai.query-interface.v2`
- `fortress.project.dependency-model.v2`

Goal:
- Introduce minimal persona + phone-based identity resolution without dependency drift.

Execution:
1. Implement phone-based identity resolution exactly as documented.
2. Keep orchestrator pluggable and interface-bound.
3. Enforce no direct storage access by agents.
4. Maintain single-agent control flow only.

Monitoring commands (minimum evidence set):
- Interface-path checks (query + security)
- Deny tests for direct DB path attempts from orchestrator layer
- Ledger/projection consistency checks (no regression)

Master approval gate D:
- Orchestrator operates only via Query Interface + Security interfaces.
- No direct DB access by agent layer.

What NOT to do:
- No autonomous multi-agent behavior.
- No WhatsApp integration in MVP.

---

### Stage E — Security Hardening & Audit Validation

Source docs (ID + version):
- `fortress.security.zone-model.v2`
- `fortress.security.access-control.v2`
- `fortress.security.audit-model.v1`
- `fortress.project.qa-governance.v1`

Goal:
- Validate zone isolation, access control, and audit completeness before production.

Execution:
1. Run explicit deny tests across zone boundaries.
2. Validate audit trace completeness for canonical transitions.
3. Execute red-team style read/write bypass attempts.
4. Confirm append-only and processor-discipline invariants remain intact.

Monitoring commands (minimum evidence set):
- Security allow/deny test suite
- Audit coverage checks
- Ledger integrity diagnostics
- Projection consistency checks

Master approval gate E:
- Zero critical security bypasses.
- Audit traceability complete.

What NOT to do:
- No performance optimization before security pass.

---

### Stage F — Backup/Restore + Operational Production Readiness

Source docs (ID + version):
- `fortress.infra.backup-strategy.v1`
- `fortress.infra.runtime-mac-mini.v1`
- `fortress.project.qa-governance.v1`

Goal:
- Prove recoverability and stable day-2 operations.

Execution:
1. Execute backup + restore drills on realistic data volume.
2. Re-run full deterministic integrity suite on restored environment.
3. Finalize operational runbook (startup, incident response, rollback policy).

Monitoring commands (minimum evidence set):
- Backup job + restore verification commands
- Post-restore ledger integrity diagnostics
- Post-restore projection consistency checks + rebuild checks

Master approval gate F:
- Recovery thresholds accepted.
- Restored system passes deterministic checks.

---

### Stage G — Stabilization to Production

Source docs (ID + version):
- `fortress.project.implementation-roadmap.v2`
- `fortress.project.product-backlog.v1`
- `fortress.project.qa-governance.v1`

Goal:
- Final production cut under deterministic, security-approved constraints.

Execution:
1. Performance tuning only after correctness/security pass.
2. Freeze scope and execute release checklist.
3. Perform final go/no-go review with risk register and evidence pack.

Monitoring commands (minimum evidence set):
- Full regression validation suite
- Ledger/projection/security/audit summary checks

Master approval gate G (Production):
- All prior gates signed.
- Open critical issues = 0.

## 3) Stage Evidence Pack (Required for Every Master Gate)

For each stage submission, include:
1. Micro-scope statement (1-3 deliverables max).
2. Source documents (ID + version).
3. File diffs / PR links.
4. Command list executed.
5. Raw command outputs (or attached logs).
6. Acceptance checklist (pass/fail per item).
7. Risk notes and explicit non-goals.
8. Master approval request.

## 4) Suggested Working Method with Master Control

Execution loop:
1. Master defines approved micro-scope.
2. Agent returns implementation plan + acceptance checks + non-goals + document references.
3. Master approves/edit.
4. Agent executes, with fail-fast halt on invariant violation.
5. Agent submits evidence pack.
6. Master signs gate or requests remediation.

## 5) Efficiency Recommendations

- Work in vertical aggregate slices (contract -> processor -> projection -> consistency).
- Keep one stage checklist and one runbook (single source of truth).
- Treat deterministic diagnostics as merge blockers.
- Prefer deterministic scripts over manual DB operations.
- Prevent architecture drift by mapping each change to explicit document IDs + versions.
