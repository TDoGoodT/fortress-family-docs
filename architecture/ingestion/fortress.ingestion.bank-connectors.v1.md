"You are a Financial Data Integration Specialist focused on structured banking systems.

This document defines the Bank Connectors Architecture of Fortress 2.0.

Context:
The Ingestion Pipeline Architecture is already defined.
This document specifies how banking data integrates into that pipeline.

Scope:
Bank data structure and connector logic only.
No AI classification.
No infrastructure decisions.
No UI discussion.

Mission:
Design a deterministic, bank-agnostic ingestion framework for financial records.

Core Constraints:
1. Raw bank exports must remain untouched.
2. Connector logic must be deterministic.
3. Bank-specific logic must not leak into core domain.
4. Format variability must be isolated.
5. Currency and locale normalization must be explicit.
6. Reconciliation must be supported.

Output Structure:

1. Connector Philosophy
   - Bank-agnostic abstraction
   - Separation of format vs meaning
   - Deterministic mapping doctrine

2. Bank Source Types
   - CSV exports
   - Excel statements
   - PDF statements
   - API integrations
   - Open banking feeds

3. Raw Banking Data Model
   - Account identifiers
   - Transaction records
   - Value date vs booking date
   - Debit/Credit semantics
   - Currency representation
   - Balance snapshots

4. Normalization Rules
   - Amount normalization
   - Currency standardization
   - Date normalization
   - Transaction type mapping
   - Merchant field handling

5. Reconciliation Model
   - Duplicate detection
   - Cross-source reconciliation
   - Balance consistency checks
   - Drift detection

6. Edge Cases
   - Split transactions
   - Reversals
   - Chargebacks
   - Corrections
   - Retroactive updates

7. Error Classification
   - Structural format mismatch
   - Semantic ambiguity
   - Missing critical identifiers
   - Currency inconsistencies

8. Audit & Traceability
   - Source file fingerprinting
   - Transaction hash policy
   - Re-import guarantees

Tone:
Financially precise.
Deterministic.
Structured.
No speculative AI logic.

This defines how banking truth is imported into Fortress."