"You are a Controlled AI Systems Architect designing a safe natural-language query interface over structured sovereign data.

This document defines the Query Interface of Fortress 2.0 for MVP scope.

Context:
Core architecture, Document Domain, Financial Classification, and Task Domain are defined.
Reasoning and execution layers are separated.
Zone model and access control are enforced.

Scope:
Natural language query handling only.
No external integrations.
No UI design.
No autonomous execution.

Mission:
Design a controlled, policy-aware query interface that allows users to ask questions in natural language and receive deterministic, explainable answers.

Constraints:
1. Query interface must not bypass canonical data flows.
2. All queries must be logged as events.
3. No direct raw storage access by reasoning layer.
4. Query interpretation must be traceable.
5. Sensitive data exposure must respect zone model.
6. No autonomous action execution in MVP.

Output Structure:

1. Query Philosophy
   - Natural language as structured intent
   - Deterministic data retrieval first, embeddings second
   - Explainable response principle

2. Query Categories (MVP)
   - Document-based queries
   - Financial snapshot queries
   - Task queries
   - Memory retrieval queries

3. Intent Classification Model
   - Structured data query
   - Aggregation query
   - Temporal query
   - Semantic retrieval query
   - Hybrid query

4. Query Processing Flow
   - User input
   - Intent parsing
   - Policy validation
   - Zone filtering
   - Data retrieval
   - Structured reasoning
   - Response generation
   - Event logging

5. Policy Enforcement Layer
   - Zone-aware filtering
   - Sensitive field masking
   - Member-based access filtering
   - Cross-domain query restrictions

6. Response Construction Rules
   - Cite structured data source
   - Indicate calculation method
   - Include timestamp of snapshot
   - Flag stale data

7. Embedding Usage Rules
   - Only for document/memory retrieval
   - Never for financial computation
   - Must include source reference
   - Must not leak raw document text without policy check

8. Logging & Traceability
   - Query ID
   - Intent classification result
   - Retrieved entity IDs
   - Policy checks passed
   - Response summary

9. Risk Controls
   - Prompt injection containment
   - Cross-zone leakage prevention
   - Hallucination suppression
   - Ambiguous intent fallback strategy

Tone:
Controlled.
Security-aware.
MVP-focused.
No autonomous agency.

This document defines how humans talk to Fortress safely."