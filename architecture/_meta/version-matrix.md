# Fortress 2.0 – Version Matrix

This document defines the official version authority state of all
Fortress 2.0 architectural documents.

This matrix identifies the current document authority state for Fortress. Agents and contributors should distinguish between verified current-state documents, target-state architecture, and archived historical artifacts.

If a document has multiple versions:
- Only one may be marked Canonical: Yes
- All prior versions must be immutable
- Superseding relationships must be explicit

This matrix is the fast-reference truth for architectural status.

---

## Verified Current-State Authority

These documents should be read first when the question is "what is currently implemented and verified?"

| Document ID | Layer | Version | Status | Authority Type | Notes |
|-------------|-------|---------|--------|----------------|-------|
| fortress.current-state.verified | meta | v1 | ACTIVE | VERIFIED CURRENT STATE | Primary source for verified repository state |

---

## Canonical Architecture Documents (Target / Design Authority)

These documents remain canonical design authority, but many describe target-state architecture rather than fully verified implementation.

| Document ID | Layer | Current Version | Status | Canonical | Supersedes |
|-------------|-------|----------------|--------|-----------|------------|
| fortress.core.system-overview (Core architecture authority) | core | v1 | ACTIVE | Yes | — |
| fortress.core.database-blueprint | core | v1 | ACTIVE | Yes | — |
| fortress.core.event-ledger (Event ledger doctrine authority) | core | v1 | ACTIVE | Yes | — |
| fortress.core.account-domain (Account aggregate authority) | core | v1 | ACTIVE | Yes | — |
| fortress.core.document-domain | core | v1 | ACTIVE | Yes | — |
| fortress.core.financial-classification | core | v1 | ACTIVE | Yes | — |
| fortress.core.task-domain | core | v1 | ACTIVE | Yes | — |
| fortress.ingestion.pipeline-architecture (Ingestion pipeline authority) | ingestion | v3 | ACTIVE | Yes | v2 |
| fortress.ingestion.bank-connectors | ingestion | v2 | ACTIVE | Yes | v1 |
| fortress.ingestion.document-extraction | ingestion | v2 | ACTIVE | Yes | v1 |
| fortress.ai.annotation-strategy | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.feature-engineering | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.embedding-architecture | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.anomaly-detection | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.query-interface | ai | v2 | ACTIVE | Yes | v1 |
| fortress.openclaw.agent-architecture | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.reasoning-model | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.task-orchestration | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.household-orchestrator | openclaw | v1 | ACTIVE | Yes | — |
| fortress.security.zone-model | security | v2 | ACTIVE | Yes | v1 |
| fortress.security.access-control | security | v2 | ACTIVE | Yes | v1 |
| fortress.security.audit-model | security | v1 | ACTIVE | Yes | — |
| fortress.infra.storage-layout | infra | v1 | ACTIVE | Yes | — |
| fortress.infra.runtime-mac-mini | infra | v1 | ACTIVE | Yes | — |
| fortress.infra.backup-strategy | infra | v1 | ACTIVE | Yes | — |
| fortress.infra.observability-model | infra | v1 | ACTIVE | Yes | — |
| fortress.infra.engineering-principles | infra | v1 | ACTIVE | Yes | — |
| fortress.project.knowledge-architecture | project | v1 | ACTIVE | Yes | — |
| fortress.project.master-control | project | v1 | ACTIVE | Yes | — |
| fortress.project.product-management | project | v1 | ACTIVE | Yes | — |
| fortress.project.executive-brief | project | v1 | ACTIVE | Yes | — |
| fortress.project.implementation-roadmap | project | v2 | ACTIVE | Yes | v1 |
| fortress.project.product-backlog | project | v1 | ACTIVE | Yes | — |
| fortress.project.build-buy-matrix | project | v1 | ACTIVE | Yes | — |
| fortress.project.ai-development-protocol | project | v1 | ACTIVE | Yes | — |
| fortress.project.qa-governance | project | v1 | ACTIVE | Yes | — |
| fortress.project.dependency-model (Development governance authority) | project | v2 | ACTIVE | Yes | v1 |
| fortress.project.version-governance | project | v1 | ACTIVE | Yes | — |
| fortress.project.knowledge-update.household-layer | project | v1 | ACTIVE | Yes | — |
| fortress.project.ceo-pitch | project | v1 | ACTIVE | Yes | — |

---

## Partial / Target-State Documents

These documents are still useful, but should be treated as target-state, planning, or partially implemented references unless verified against code and runtime behavior.

| Document Group | Layer | Status |
|----------------|-------|--------|
| AI documents (`fortress.ai.*`) | ai | TARGET STATE / PARTIAL IMPLEMENTATION |
| OpenClaw documents (`fortress.openclaw.*`) | openclaw | TARGET STATE / NOT VERIFIED IN CODE |
| Security control and access documents (`fortress.security.*`) | security | TARGET STATE / PARTIAL IMPLEMENTATION |
| Domain documents beyond minimal implemented surfaces (`document-domain`, `task-domain`, `financial-classification`) | core | TARGET STATE / BROADER THAN VERIFIED IMPLEMENTATION |
| Project roadmap and product planning documents | project | TARGET STATE / PLANNING |

---

## Archived Versions

| Document ID | Layer | Version | Status | Superseded By |
|-------------|-------|---------|--------|---------------|
| fortress.ingestion.pipeline-architecture | ingestion | v1 | ARCHIVED | v2 |
| fortress.ingestion.pipeline-architecture | ingestion | v2 | ARCHIVED | v3 |
| fortress.ingestion.bank-connectors | ingestion | v1 | ARCHIVED | v2 |
| fortress.ingestion.document-extraction | ingestion | v1 | ARCHIVED | v2 |
| fortress.security.zone-model | security | v1 | ARCHIVED | v2 |
| fortress.security.access-control | security | v1 | ARCHIVED | v2 |
| fortress.ai.query-interface | ai | v1 | ARCHIVED | v2 |
| fortress.project.implementation-roadmap | project | v1 | ARCHIVED | v2 |
| fortress.project.dependency-model | project | v1 | ARCHIVED | v2 |

---

## Archived Operational / Historical Documents

These documents were moved to `architecture/_archive/` because they are historical execution artifacts, stale plans, or misleading status snapshots.

| Document ID | Current Path | Status |
|-------------|--------------|--------|
| fortress.project.execution-plan-to-production | `architecture/_archive/project/fortress.project.execution-plan-to-production.v1.md` | ARCHIVED |
| fortress.project.stage-a-baseline-evidence | `architecture/_archive/project/fortress.project.stage-a-baseline-evidence.v1.md` | ARCHIVED |
| fortress.project.stage-a-daily-wrapup | `architecture/_archive/project/fortress.project.stage-a-daily-wrapup.md` | ARCHIVED |
| fortress.project.controlled-filesystem-inbox-intake-plan | `architecture/_archive/project/fortress.project.controlled-filesystem-inbox-intake-plan.v1.md` | ARCHIVED |
| fortress.infra.clean-baseline | `architecture/_archive/infra/fortress.infra.clean-baseline.v1.md` | ARCHIVED |

---

## Draft Documents

Draft documents are not yet canonical authority.
They may be refined without version bump until marked ACTIVE.

| Document ID | Layer | Version | Status |
|-------------|-------|---------|--------|
| fortress.core.domain-model | core | v1 | DRAFT |

---

## Governance Rule

Before implementation:

- Document must be ACTIVE
- Document must be Canonical if multiple versions exist
- Version must be referenced explicitly in development prompt

No code may be written against ambiguous version state.

## Recommended Reading Order

1. `architecture/_meta/fortress.current-state.verified.v1.md`
2. `architecture/_meta/version-matrix.md`
3. `architecture/core/fortress.core.event-ledger.v1.md`
4. `architecture/ingestion/fortress.ingestion.pipeline-architecture.v3.md`
5. `architecture/project/fortress.project.dependency-model.v2.md`
6. `README.md`

---

Fortress evolves deliberately.
Version state is architectural memory.
