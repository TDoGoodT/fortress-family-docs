# fortress.ingestion.document-extraction.v2 — PATCH (changed sections only)

## Delta From v1 (UPDATED)
- Defines deterministic extraction outputs without AI.
- Defines required extracted fields as “best-effort deterministic parsing”, no probabilistic confidence.
- Defines normalized record types for document ingestion and their handoff payload requirements.
- Normalizes UUIDv7 generator naming to `uuid_v7()` via pipeline tables spec (no new generator names introduced).

## No other changes required for Master Control fixes
- UUID generator usage is inherited from pipeline-architecture.v2 table defaults, now standardized on `uuid_v7()`.
- Event ledger mapping, zone context encoding, zone placement, and run_state sequencing are defined centrally in pipeline-architecture.v2 and apply to this document.

## Version Metadata (authoritative)
- Document ID: fortress.ingestion.document-extraction
- Version: v2
- Layer: ing
- Status: ACTIVE
- Canonical: Yes
- Supersedes: fortress.ingestion.document-extraction.v1
- Depends On:
  - fortress.ingestion.pipeline-architecture.v3
  - fortress.core.document-domain.v1
  - fortress.core.event-ledger.v1
  - fortress.security.zone-model.v2
  - fortress.project.implementation-roadmap.v2
  - fortress.project.dependency-model.v2
  - fortress.project.version-governance.v1
