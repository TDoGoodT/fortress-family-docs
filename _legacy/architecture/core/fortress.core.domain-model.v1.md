"You are a Senior Domain Architect specialized in Event-Driven Systems.

This document defines the Domain Model of Fortress 2.0.

Context:
The System Overview and Database Blueprint are already defined.
This document formalizes the conceptual domain layer.
It defines meaning, not tables.

Scope:
Conceptual domain modeling only.
No schema fields.
No storage discussion.
No infrastructure.

Mission:
Define the semantic backbone of Fortress.

Design Principles:
1. Domain-first, database-second.
2. Events are first-class citizens.
3. Entities represent stable identity.
4. Relationships express meaning, not joins.
5. Temporal awareness is mandatory.
6. No AI assumptions at the domain level.

Output Structure:

1. Domain Philosophy
   - What is a Domain in Fortress
   - Bounded Context definition
   - Aggregate philosophy

2. Core Aggregates
   Define aggregates and their invariants:
   - Person
   - Household
   - Account
   - Asset
   - Liability
   - Transaction
   - Document
   - Contract
   - Event

   For each:
   - Purpose
   - Identity boundary
   - Lifecycle model
   - Invariants

3. Relationship Semantics
   - Ownership
   - Control
   - Beneficiary
   - Delegation
   - Temporal relationships

4. Event Taxonomy
   - Financial events
   - Legal events
   - Lifecycle events
   - System events
   - Derived analytical events

5. Temporal Model
   - Valid time vs System time
   - Retroactive corrections
   - Snapshot philosophy

6. Consistency Boundaries
   - What must be strongly consistent
   - What can be eventually consistent
   - Cross-aggregate interaction rules

7. Domain Risks
   - Where conceptual drift may occur
   - Over-modeling risks
   - AI leakage risk

Tone:
Precise.
Semantic.
Conceptual.
No technical implementation discussion.

This defines the language of Fortress."