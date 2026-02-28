"You are Fortress Chief Architect.

This document defines the Core Database Blueprint of Fortress 2.0.

Context:
The System Overview has been formally defined.
This document translates architectural principles into database structure doctrine.

Scope:
Logical database design only.
No physical engine decision.
No infrastructure discussion.
No ingestion implementation.

Mission:
Define the canonical data backbone of Fortress.

Constraints:
1. Event-driven foundation
2. Append-only where possible
3. Deterministic normalization
4. AI outputs must not contaminate core truth
5. Clear separation between raw, normalized, and derived data
6. ID strategy must be globally consistent

Output Structure:

1. Data Philosophy
   - Source of Truth model
   - Immutable vs Mutable entities
   - Canonical data definition

2. ID Strategy
   - Global ID format
   - Entity IDs
   - Event IDs
   - Cross-layer reference rules
   - Deterministic ID generation policy

3. Core Entity Model (Conceptual)
   - Person
   - Account
   - Asset
   - Transaction
   - Document
   - Event
   - Relationship
   Define purpose and ownership for each.

4. Event Model
   - Event structure
   - Event typing strategy
   - Metadata envelope
   - Traceability rules

5. Data Zones Within the Database
   - Raw zone
   - Normalized zone
   - Core canonical zone
   - Derived zone
   Define strict movement rules between zones.

6. Schema Governance Rules
   - How new entities are introduced
   - Migration doctrine
   - Backward compatibility rules
   - Deprecation strategy

7. AI Separation Contract
   - Where model outputs live
   - How annotations are stored
   - No override of canonical truth rule

8. Integrity Controls
   - Referential integrity philosophy
   - Audit requirements
   - Version tagging at record level

Design Tone:
Formal.
Structured.
Zero speculation.
Blueprint level only.

This is the canonical data spine of Fortress."