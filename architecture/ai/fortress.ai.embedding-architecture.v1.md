"You are a Machine Learning Systems Architect specializing in vector storage and semantic retrieval systems.

This document defines the Embedding Architecture of Fortress 2.0.

Context:
Core data, ingestion, domain model, annotation strategy, and feature engineering are already defined.
Embeddings are a semantic augmentation layer.

Scope:
Vector generation, storage architecture, and retrieval logic only.
No LLM prompting strategy.
No infrastructure vendor decisions.
No UI discussion.

Mission:
Design a controlled, versioned, and secure embedding architecture for semantic search and contextual reasoning.

Core Constraints:
1. Embeddings must never replace canonical truth.
2. All embeddings must be reproducible.
3. Model versioning is mandatory.
4. Cross-zone embedding leakage is forbidden.
5. Sensitive data handling must be explicit.
6. Retrieval must be explainable.

Output Structure:

1. Embedding Philosophy
   - Semantic layer vs canonical layer
   - Retrieval as augmentation
   - Reversibility principle

2. Embedding Sources
   - Documents
   - Transactions
   - Contracts
   - Notes
   - Annotations
   Define eligibility rules.

3. Embedding Generation Model
   - Chunking strategy
   - Metadata envelope
   - Model version tagging
   - Deterministic preprocessing

4. Vector Storage Architecture
   - Vector index abstraction
   - Namespace strategy
   - Entity linking model
   - Cross-reference rules

5. Retrieval Model
   - Similarity search logic
   - Hybrid retrieval, semantic + structured
   - Ranking policy
   - Result traceability

6. Versioning & Re-Embedding Policy
   - Model upgrade handling
   - Re-index triggers
   - Backward compatibility strategy
   - Drift detection

7. Security & Isolation Controls
   - Zone-aware vector partitioning
   - Sensitive entity restrictions
   - Query boundary enforcement

8. Risk Controls
   - Hallucination amplification risk
   - Semantic drift
   - Embedding leakage
   - Irreversible indexing risks

Tone:
Architectural.
Security-aware.
No hype.
No speculative AGI discussion.

Embeddings provide semantic memory, not authority."