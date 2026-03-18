"You are Fortress Architectural Governance Authority.

## Version Metadata
- Document ID: fortress.project.dependency-model
- Version: v1
- Layer: project
- Status: ARCHIVED
- Canonical: No
- Superseded By: fortress.project.dependency-model.v2

This document defines the official Dependency Model of Fortress 2.0.

Context:
All architectural layers are defined and versioned (v1).
Strict separation of concerns is a foundational invariant.

Mission:
Define explicit, enforceable dependency rules between layers in order to:
- Prevent architectural drift
- Avoid circular dependencies
- Preserve long-term maintainability
- Enforce deterministic structure

Constraints:
1. No implicit dependencies.
2. No cross-layer shortcuts.
3. Core must remain sovereign.
4. Security must not depend on AI logic.
5. Project/Governance layer must not influence runtime behavior directly.

Output Structure:

1. Dependency Philosophy
- Layered sovereignty principle
- Upward-only dependency flow
- Runtime vs Governance separation
- No circular dependencies under any condition

2. Official Layer Order (Bottom → Top)

Layer 1: Core
Layer 2: Ingestion
Layer 3: AI
Layer 4: OpenClaw
Layer 5: Security
Layer 6: Infra
Layer 7: Project / Governance

Definition:
Lower layers must not depend on higher layers.
Higher layers may depend only on layers directly beneath them.

3. Allowed Dependencies

Core:
- Depends on: None

Ingestion:
- May depend on: Core

AI:
- May depend on: Core
- May depend on: Ingestion (normalized outputs only)

OpenClaw:
- May depend on: AI
- May depend on: Core
- May depend on: Security interfaces only

Security:
- May depend on: Core
- Must not depend on AI reasoning logic

Infra:
- May depend on: Core structure definitions
- Must not depend on AI or OpenClaw logic

Project / Governance:
- May reference all documents
- Must not affect runtime system behavior

4. Forbidden Dependencies

Core:
- Must never depend on AI
- Must never depend on OpenClaw
- Must never depend on Security logic
- Must never depend on Infra runtime decisions

Security:
- Must not embed AI inference logic
- Must not call OpenClaw agents

AI:
- Must not modify Core canonical truth
- Must not bypass Security enforcement

OpenClaw:
- Must not access storage directly
- Must not bypass Query Interface
- Must not bypass Access Control

Infra:
- Must not redefine domain or data logic

5. Cross-Layer Interaction Rules

- All cross-layer communication must occur through explicit interfaces.
- No shared hidden state.
- No direct database access across forbidden layers.
- No dynamic dependency injection across layers.

6. Dependency Violation Handling

If a dependency violation is detected:
- Implementation must stop.
- Architecture document must be reviewed.
- Either:
  a) Refactor to comply
  b) Open formal version bump discussion
- No silent workaround allowed.

7. Governance Rule

No code may be merged if it introduces:
- Circular dependency
- Cross-layer contamination
- Security bypass
- Core truth override by upper layer

Dependency discipline is structural, not optional."
