"You are a Financial Domain Architect specializing in personal asset and liquidity modeling.

This document defines the Financial Classification Model of Fortress 2.0 for MVP scope.

Context:
Core architecture and Document Domain are already defined.
This document specializes financial entities to enable liquidity computation and obligation tracking.

Scope:
Financial classification only.
No banking API integration.
No advanced portfolio analytics.
No tax modeling.

Mission:
Define a clear and deterministic financial classification system that enables:
- Liquidity calculation
- Obligation tracking
- Net worth snapshot
- Recurring payment awareness

Constraints:
1. All classifications must be explicit.
2. No probabilistic labeling.
3. Must work without real-time bank sync.
4. Must support manual data entry.
5. Liquidity must be computable at any point in time.

Output Structure:

1. Financial Modeling Philosophy
   - Asset vs Liability
   - Liquid vs Illiquid
   - Short-term vs Long-term
   - Ownership attribution model

2. Core Financial Entities for MVP
   - Cash Account
   - Investment Account
   - Retirement Account
   - RSU / Equity Grant
   - Real Estate Asset
   - Loan / Mortgage
   - Credit Obligation
   - Recurring Payment Obligation

3. Liquidity Classification Model
   Define categories:

   Tier 1: Immediate Liquidity
   - Checking
   - Savings
   - Cash equivalents

   Tier 2: Near Liquidity
   - Brokerage
   - Vested RSUs
   - Short-term funds

   Tier 3: Restricted / Locked
   - Retirement accounts
   - Locked savings
   - Illiquid assets

   Define rules for classification.

4. Valuation Rules
   - Manual valuation entry
   - Statement-based valuation
   - Currency normalization
   - Staleness detection

5. Obligation Tracking Model
   - Fixed recurring payments
   - Variable recurring payments
   - One-time obligations
   - Expiration-linked obligations

6. Net Worth Computation Model
   - Snapshot calculation
   - Event-based recalculation
   - Liability offset rules

7. Liquidity Query Model
   Must support questions like:
   - “How much liquid money do I have today?”
   - “How much is locked?”
   - “What obligations are due this month?”

8. Risk Controls
   - Double counting prevention
   - Currency mismatch
   - Manual entry inconsistency
   - Data staleness warning

Tone:
Clear.
Deterministic.
MVP-focused.
No hedge-fund level complexity.

This document defines how Fortress understands money."