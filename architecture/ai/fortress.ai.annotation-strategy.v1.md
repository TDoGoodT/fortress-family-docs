"You are a Data Scientist designing AI annotation and model output governance systems.

This document defines the AI Annotation Strategy of Fortress 2.0.

Context:
Core data, ingestion, and domain models are already defined.
AI is a secondary intelligence layer that must not alter canonical truth.

Scope:
AI outputs, annotations, scoring, and model governance only.
No training pipelines.
No infrastructure decisions.
No core schema redesign.

Mission:
Design a controlled annotation system where AI augments data without contaminating it.

Core Constraints:
1. AI outputs must never override canonical data.
2. All model outputs must be versioned.
3. Model metadata must be attached to every annotation.
4. Deterministic traceability is required.
5. Human override must be supported.
6. AI logic must remain replaceable.

Output Structure:

1. AI Layer Philosophy
   - AI as augmentation
   - Separation of truth vs inference
   - Reversibility principle

2. Annotation Model
   - Annotation object definition
   - Linkage to core entities
   - Annotation lifecycle
   - Expiration policy

3. Model Versioning Strategy
   - Model ID structure
   - Version tagging
   - Backward comparability rules
   - Re-scoring policy

4. Confidence & Scoring Framework
   - Confidence score definition
   - Calibration principles
   - Threshold governance
   - Human review triggers

5. Annotation Types
   - Classification annotations
   - Risk annotations
   - Semantic tagging
   - Behavioral inference
   - Predictive outputs

6. Storage Separation Rules
   - Where annotations live
   - How they reference core entities
   - No overwrite guarantee

7. Governance & Audit
   - Model audit logging
   - Annotation provenance tracking
   - Drift monitoring principles

8. AI Risk Controls
   - Hallucination containment
   - Overfitting detection signals
   - Feedback loop isolation
   - Cross-zone inference restrictions

Tone:
Scientific.
Controlled.
Governance-driven.
No hype.
No implementation speculation.

AI is an intelligence layer, not the authority."