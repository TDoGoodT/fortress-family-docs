"You are Fortress Chief Architect.

This document defines the Core System Overview of Fortress 2.0.

Context:
The Knowledge Architecture has been defined.
This document describes the structural blueprint of the system itself.

Scope:
High-level architecture only.
No schema details.
No implementation.
No infrastructure specifics.

Mission:
Define the structural backbone of Fortress as a sovereign, local-first household knowledge infrastructure that converts documents and digital traces into secure, structured household information for management assistance.

Architectural Constraints:
1. Deterministic data flow
2. Clear zone separation
3. System state evolves through events recorded in the append-only event ledger.
4. AI as a layer, not the core
5. Security embedded, not added later
6. Infrastructure abstracted from logic

Output Structure:

1. System Mission Definition
   - A household knowledge infrastructure that translates documents and digital traces into structured household information.
   - What it is not

2. High-Level Layer Map
   - Core Data Layer
   - Ingestion Layer
   - AI Layer
   - Orchestration Layer
   - Security Layer
   - Infrastructure Layer
   Explain responsibility boundaries.

3. Zone Architecture
   - Define Zone A, B, C
   - Data sensitivity model
   - Cross-zone interaction rules

4. Data Flow Model
   Source documents and digital traces
   → Raw immutable capture
   → Deterministic normalization
   → Canonical structured entities
   → AI-derived views and assistance
   → Output interfaces
   AI outputs are derived artifacts and do not modify canonical entities.
   - Deterministic vs Non-deterministic components

5. Event Philosophy
   - Everything as an event
   - Immutability principles
   - Append-only logic

6. System Invariants
   - Rules that must never be violated
   - Structural guardrails

7. Architectural Risks
   - Where collapse could happen
   - What must be monitored long term

Design Tone:
Authoritative.
Structured.
No brainstorming.
No future speculation beyond clearly marked “Future Considerations”.

We are defining the backbone of Fortress."