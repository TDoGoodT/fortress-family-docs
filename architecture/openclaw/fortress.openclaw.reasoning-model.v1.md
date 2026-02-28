"You are a Cognitive Systems Architect designing structured reasoning frameworks for controlled AI planning systems.

This document defines the Reasoning Model of Fortress 2.0.

Context:
Agent Architecture and Task Orchestration are already defined.
Reasoning is separated from execution.
This document defines structured planning logic.

Scope:
Reasoning framework only.
No infrastructure.
No model vendor selection.
No UI prompt engineering.

Mission:
Design a controlled, explainable, and policy-aware reasoning framework.

Core Constraints:
1. Reasoning must be decomposable into steps.
2. Plans must be traceable.
3. Policy constraints must be enforced before execution.
4. Reasoning must be interruptible.
5. No hidden memory state.
6. Deterministic guardrails must wrap probabilistic reasoning.

Output Structure:

1. Reasoning Philosophy
   - Structured planning vs free-form generation
   - Reasoning as controlled decomposition
   - Policy-first thinking

2. Planning Model
   - Goal definition structure
   - Subtask decomposition rules
   - Dependency resolution
   - Plan validation stage

3. Tool Selection Framework
   - Capability registry lookup
   - Tool eligibility constraints
   - Zone-aware tool filtering
   - Risk-aware tool gating

4. Policy Enforcement Layer
   - Pre-execution policy checks
   - Access validation
   - Sensitivity classification checks
   - Cross-zone restriction logic

5. Step Execution Contract
   - Input validation
   - Output validation
   - Structured result expectations
   - Failure classification

6. Interrupt & Override Model
   - Human intervention triggers
   - Confidence threshold gating
   - Escalation criteria
   - Manual approval pathways

7. Reasoning Traceability
   - Plan ID structure
   - Step logging format
   - Decision rationale capture
   - Cross-reference to task engine logs

8. Risk Controls
   - Recursive reasoning containment
   - Hallucination boundary enforcement
   - Scope creep prevention
   - Over-planning safeguards

Tone:
Controlled.
Policy-aware.
Architectural.
No speculative AGI framing.

Reasoning is structured planning under constraints."