# AGENTS

## 1. What Fortress Is

Fortress is a sovereign, local-first household knowledge infrastructure. It converts documents and digital traces into structured household information that agents can use for management assistance under strict architectural governance.

## 2. What Fortress Is NOT

- Not a bank
- Not a financial ledger product
- Not a document vault
- Not a chatbot with memory

## 3. Core Architectural Principles

- Raw documents are immutable.
- Canonical truth is stored as structured entities.
- System state evolves through events recorded in the append-only event ledger.
- The event ledger is append-only.
- Historical events are never mutated.
- AI cannot override canonical truth.
- Agents never access storage directly.
- Raw storage and canonical entity storage must remain strictly separated across system zones.

## 4. Event Model

- Canonical state transitions are recorded as events.
- Canonical entities are projections derived from event history.
- Corrections must be appended as corrective events.
- AI outputs are derived artifacts and must never modify canonical entities or event history.

## 5. Aggregate Identity Doctrine

`canonical_handoff_request.target_entity_id` becomes the canonical `aggregate_id` used across projections and core tables.

## 6. Processor Discipline

Each aggregate must have exactly one authoritative processor responsible for converting handoff requests into events.

## 7. Development Rules for Agents

- Do not modify the event ledger history.
- Do not introduce alternate processor paths.
- Do not bypass contract views.
- Do not allow AI layers to modify canonical entities.