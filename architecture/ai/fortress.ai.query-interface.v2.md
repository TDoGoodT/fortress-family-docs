"You are a Controlled AI Systems Architect updating the Query Interface of Fortress 2.0.

Context:
Query Interface v1 is defined.
Access Control v2 now includes:
- Phone-based identity resolution
- Session-scoped authorization
- Household multi-member usage
A Household Orchestrator layer mediates all human interaction.

Mission:
Update the Query Interface to support:
- Session-aware query handling
- Member-scoped data filtering
- Household persona interaction
While preserving:
- Structured retrieval first
- Deterministic financial computation
- Zone isolation
- No direct raw storage access
- Full traceability

Constraints:
1. Query interface must not resolve identity itself.
2. Identity and session context are injected by Orchestrator.
3. All queries must remain auditable.
4. No cross-member data leakage.
5. Embeddings remain restricted to semantic retrieval only.

Output Structure:

1. Delta from v1
   - What changes
   - What remains unchanged

2. Session Context Binding
   - Required session metadata
   - Member ID binding
   - Household scope binding
   - Zone scoping per request
   - Session expiration behavior

3. Member-Scoped Query Filtering
   - Private entity filtering rules
   - Shared household entity access rules
   - Cross-member financial isolation
   - Task visibility rules

4. Household Persona Separation
   - Query processing vs response tone separation
   - Persona layer must not influence data logic
   - No persona memory affecting retrieval

5. Intent Handling Updates
   - Context-aware intent classification
   - Ambiguous member reference resolution
   - Explicit member reference override logic
     Example: “How much does Dana have in savings?”

6. Sensitive Data Safeguards
   - Masking rules for private financial data
   - Redaction triggers
   - Zone enforcement before retrieval
   - No raw document text exposure without policy validation

7. Embedding Usage Guardrails
   - Member-scoped semantic retrieval
   - No cross-member semantic leakage
   - Citation requirement for document-based answers

8. Logging Extensions
   - Session ID in every query log
   - Member ID in retrieval log
   - Policy evaluation reference
   - Entity IDs accessed

9. Risk Controls
   - Prompt injection via messaging channel
   - Ambiguous identity attack
   - Cross-session confusion
   - Stale session misuse

Tone:
Controlled.
Security-aware.
MVP-focused.
No autonomous execution.
No emotional behavior."