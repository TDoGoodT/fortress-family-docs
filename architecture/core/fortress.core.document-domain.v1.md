"You are a Domain Architect specializing in structured document intelligence systems.

This document defines the Document Domain of Fortress 2.0 for MVP scope.

Context:
Core system, database blueprint, and domain model are already defined.
This document specializes the generic Document entity into actionable categories for MVP.

Scope:
Document domain only.
No embedding implementation.
No ingestion pipeline redesign.
No UI flows.

Mission:
Define a structured and practical Document Domain that enables real-world family intelligence use cases.

Constraints:
1. Documents are immutable once stored.
2. Extracted fields must be versioned.
3. Document types must be finite and explicit in MVP.
4. No speculative future domains.
5. Must support querying: “When does X expire?” and “How much do we pay for Y?”

Output Structure:

1. Document Domain Philosophy
   - Document as evidence
   - Document as event source
   - Document as knowledge container

2. MVP Document Type Taxonomy
   Define explicit types for v1 only:

   Financial
   - Insurance Policy
   - Mortgage Agreement
   - Investment Statement
   - Pension Statement
   - Bank Statement
   - Salary / RSU Grant Letter

   Legal
   - Contract
   - Amendment
   - NDA

   Operational
   - Subscription Agreement
   - Utility Bill

   Personal
   - Personal Letter
   - Recipe
   - Certificate
   - Identification Document

3. Required Extracted Fields Per Type
   For each document type define:
   - Mandatory fields
   - Optional fields
   - Expiration field (if applicable)
   - Financial amount fields
   - Linked entities (member / institution / account)

4. Document-to-Event Mapping
   - Which documents create financial obligations
   - Which create recurring payments
   - Which create expiration events
   - Which create informational-only events

5. Expiration Logic
   - Renewal detection rules
   - Expiration alert policy
   - Replacement linking model

6. Versioning Strategy
   - Original file hash
   - Extraction version
   - Annotation version
   - Replacement chain

7. Query-Ready Schema Definition
   - Fields that must be indexable
   - Fields eligible for embedding
   - Sensitive fields classification

8. Risk Controls
   - Misclassification risk
   - Expired document drift
   - Duplicate ingestion handling
   - Sensitive PII tagging rules

Tone:
Structured.
Practical.
MVP-focused.
No abstract theory.

This document defines how Fortress understands documents in reality."