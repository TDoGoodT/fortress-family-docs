"You are Fortress Knowledge Governance Authority.

We are introducing a new product direction:

Fortress is a single sovereign entity that communicates with all household members, 
resolves identity based on phone number (future WhatsApp interface),
while maintaining strict data isolation and zone enforcement internally.

Your task:

1. Identify which architectural documents require:
   - Amendment
   - Version bump
   - No change

2. Specify exactly:
   - What changes
   - What must not change
   - Where risk increases

3. Produce:

Section A – New Required Document
Define the purpose of:
fortress.openclaw.household-orchestrator.v1

Section B – Documents requiring v2
List and justify:
- security.access-control
- ai.query-interface
- implementation-roadmap
(Only if necessary)

Section C – No Change Justification
List documents that remain valid under this product shift.

Section D – Architectural Risk Impact
Analyze:
- Identity spoofing risk
- Cross-member leakage risk
- Prompt injection via messaging interface
- Session hijacking
- Phone number reassignment risk

Section E – MVP Impact
Confirm whether Household Orchestrator belongs in MVP or Phase 2.

Constraints:
- No architectural redesign.
- Preserve all existing invariants.
- Zone isolation must remain structural.
- Reasoning/execution separation must remain intact.

Tone:
Governance-level.
Precise.
Non-speculative.
No product marketing."