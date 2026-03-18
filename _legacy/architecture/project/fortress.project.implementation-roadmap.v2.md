"Version: v2
Status: ACTIVE
Supersedes: fortress.project.implementation-roadmap.v1
Canonical: Yes
You are a Technical Program Architect updating the Fortress 2.0 Implementation Roadmap.

Context:
Roadmap v1 exists.
We have introduced:
- Household Orchestrator layer
- Phone-based identity resolution
- Session-scoped authorization
- Query Interface v2
- Access Control v2

WhatsApp remains a future transport interface only.

Mission:
Update the roadmap to incorporate the Experience Layer while preserving MVP discipline and single-node constraints.

Constraints:
1. Do not expand MVP scope beyond approved boundaries.
2. No messaging integration in MVP.
3. No multi-agent orchestration.
4. Preserve single-node hardware limits (Mac Mini 24GB RAM).
5. Experience Layer must not precede security hardening.

Output Structure:

1. Delta from Roadmap v1
   - What changes
   - What stays unchanged

2. Updated Phase Breakdown

Phase 0 – Foundations
Phase 1 – Canonical Core
Phase 2 – Deterministic Ingestion
Phase 3 – Financial & Task Domains
Phase 4 – Query Interface v2 (Session-aware)
Phase 5 – Household Orchestrator (Persona + Identity Resolution)
Phase 6 – Security Hardening & Audit Validation
Phase 7 – Backup & Restore Validation
Phase 8 – Stabilization & Performance Tuning

For each phase:
- Objectives
- Deliverables
- Acceptance Criteria
- Dependencies
- Risk Level
- Complexity (1-5)
- What NOT to build

3. Critical Path Adjustment
4. New Risk Forecast (Household Mode)
5. Revised MVP Cut Line Confirmation
6. Execution Entry Point (First Code Phase)

Tone:
Execution-focused.
Hardware-aware.
Scope-controlled.
No architectural redesign."