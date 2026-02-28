# Fortress 2.0 – Version Matrix

This document defines the official version authority state of all
Fortress 2.0 architectural documents.

If a document has multiple versions:
- Only one may be marked Canonical: Yes
- All prior versions must be immutable
- Superseding relationships must be explicit

This matrix is the fast-reference truth for architectural status.

---

## Canonical Documents (Active Authority)

| Document ID | Layer | Current Version | Status | Canonical | Supersedes |
|-------------|-------|----------------|--------|-----------|------------|
| fortress.core.system-overview | core | v1 | ACTIVE | Yes | — |
| fortress.core.database-blueprint | core | v1 | ACTIVE | Yes | — |
| fortress.core.event-ledger | core | v1 | DRAFT | No | — |
| fortress.core.domain-model | core | v1 | DRAFT | No | — |
| fortress.core.document-domain | core | v1 | ACTIVE | Yes | — |
| fortress.core.financial-classification | core | v1 | ACTIVE | Yes | — |
| fortress.core.task-domain | core | v1 | ACTIVE | Yes | — |
| fortress.ingestion.pipeline-architecture | ingestion | v1 | ACTIVE | Yes | — |
| fortress.ingestion.bank-connectors | ingestion | v1 | ACTIVE | Yes | — |
| fortress.ingestion.document-extraction | ingestion | v1 | ACTIVE | Yes | — |
| fortress.ai.annotation-strategy | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.feature-engineering | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.embedding-architecture | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.anomaly-detection | ai | v1 | ACTIVE | Yes | — |
| fortress.ai.query-interface | ai | v2 | ACTIVE | Yes | v1 |
| fortress.openclaw.agent-architecture | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.reasoning-model | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.task-orchestration | openclaw | v1 | ACTIVE | Yes | — |
| fortress.openclaw.household-orchestrator | openclaw | v1 | ACTIVE | Yes | — |
| fortress.security.zone-model | security | v1 | ACTIVE | Yes | — |
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
| fortress.project.dependency-model | project | v1 | ACTIVE | Yes | — |
| fortress.project.version-governance | project | v1 | ACTIVE | Yes | — |
| fortress.project.knowledge-update.household-layer | project | v1 | ACTIVE | Yes | — |
| fortress.project.ceo-pitch | project | v1 | ACTIVE | Yes | — |

---

## Archived Versions

| Document ID | Layer | Version | Status | Superseded By |
|-------------|-------|---------|--------|---------------|
| fortress.security.access-control | security | v1 | ARCHIVED | v2 |
| fortress.ai.query-interface | ai | v1 | ARCHIVED | v2 |
| fortress.project.implementation-roadmap | project | v1 | ARCHIVED | v2 |

---

## Draft Documents

Draft documents are not yet canonical authority.
They may be refined without version bump until marked ACTIVE.

| Document ID | Layer | Version | Status |
|-------------|-------|---------|--------|
| fortress.core.event-ledger | core | v1 | DRAFT |
| fortress.core.domain-model | core | v1 | DRAFT |

---

## Governance Rule

Before implementation:

- Document must be ACTIVE
- Document must be Canonical if multiple versions exist
- Version must be referenced explicitly in development prompt

No code may be written against ambiguous version state.

---

Fortress evolves deliberately.
Version state is architectural memory.