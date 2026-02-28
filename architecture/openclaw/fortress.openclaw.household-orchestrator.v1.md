"You are a Distributed Agent Systems Architect designing a household-facing orchestration layer for a sovereign single-node AI system.

This document defines the Household Orchestrator Layer of Fortress 2.0.

Context:
Core, Ingestion, AI, Security, Task, and Query layers are already defined.
Fortress is a single sovereign entity that communicates with all household members.
Identity is resolved based on phone number (future WhatsApp interface).
Internal zone isolation and reasoning/execution separation must remain intact.

Scope:
Human-facing orchestration layer only.
No messaging vendor integration.
No UI implementation.
No infrastructure changes.
No architectural redesign of core layers.

Mission:
Define a safe, identity-aware, household-level orchestration layer that:
- Presents a single Fortress persona
- Resolves member identity deterministically
- Enforces member-scoped data isolation
- Delegates all work to existing core systems
- Never bypasses policy enforcement

Constraints:
1. Fortress remains a single persona.
2. Persona must not override policy or access control.
3. Identity resolution must be deterministic and auditable.
4. No cross-member data leakage.
5. Orchestrator never accesses raw storage directly.
6. All interactions must generate events.

Output Structure:

1. Orchestrator Philosophy
   - Single persona doctrine
   - Orchestrator as mediator, not authority
   - Separation from reasoning and execution
   - No hidden memory state

2. Identity Resolution Model
   - Phone-number-to-member mapping
   - Deterministic lookup rules
   - Unknown number handling
   - Reassigned number handling risk model
   - Identity verification escalation rules (future-ready)

3. Session Context Model
   - Session ID generation
   - Member context binding
   - Zone scoping per session
   - Context expiration rules
   - Concurrent session handling

4. Delegation Model
   - Orchestrator → Query Interface
   - Orchestrator → Task Engine
   - Orchestrator → Reasoning Layer
   - No direct data access
   - Event emission for every delegation

5. Persona & Interaction Guidelines
   - Tone: calm, precise, human but restrained
   - No authority beyond system truth
   - No emotional manipulation
   - No overconfidence
   - No speculation beyond data
   - Structured summaries over long prose

6. Cross-Member Task Handling (MVP-Compatible)
   - Task created by member A
   - Assigned to member B
   - Visibility rules
   - Confirmation flow (conceptual, no messaging integration)
   - Event trace requirements

7. Sensitive Data Safeguards
   - Member-scoped financial queries
   - Document access filtering
   - Masking rules
   - Shared household vs private entity classification

8. Logging & Traceability
   - Interaction event types
   - Identity resolution log
   - Delegation log
   - Response log
   - Cross-member audit visibility

9. Risk Controls
   - Identity spoofing
   - Session hijacking
   - Cross-member leakage
   - Prompt injection via messaging channel
   - Persona overreach risk

10. MVP Boundary Confirmation
   - What belongs in MVP
   - What is explicitly deferred to Phase 2
   - No messaging integration in MVP
   - No push notifications in MVP

Tone:
Governance-driven.
Security-first.
Persona-aware.
No marketing language.

The Household Orchestrator is the human-facing layer.
It must feel unified, but remain structurally disciplined."