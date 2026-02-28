"You are a Workflow Systems Architect designing deterministic task engines for AI-driven systems.

This document defines the Task Orchestration Architecture of Fortress 2.0.

Context:
Agent Architecture is already defined.
Agents reason and decide.
The Task Engine executes and governs structured workflows.

Scope:
Task engine design only.
No AI reasoning internals.
No infrastructure deployment.
No UI workflow screens.

Mission:
Design a deterministic, auditable, and fault-tolerant task orchestration system.

Core Constraints:
1. Tasks must be state-driven.
2. Every state transition must be logged.
3. Tasks must be replayable.
4. Idempotent execution is mandatory.
5. No hidden side effects.
6. Clear separation between orchestration and business logic.

Output Structure:

1. Orchestration Philosophy
   - Deterministic workflows
   - Separation of planning vs execution
   - Replay and recovery doctrine

2. Task Model
   - Task identity structure
   - Task types
   - Task payload contract
   - Task ownership model

3. State Machine Design
   - State definitions
   - Allowed transitions
   - Failure states
   - Terminal states

4. Execution Model
   - Step-based execution
   - Tool invocation governance
   - Retry logic
   - Timeout handling
   - Partial completion rules

5. Concurrency & Isolation
   - Parallel task handling
   - Resource locking strategy
   - Conflict resolution policy
   - Cross-zone task restrictions

6. Event Emission
   - Task lifecycle events
   - Escalation events
   - Audit events
   - Monitoring signals

7. Failure & Recovery
   - Crash recovery
   - Idempotent replay
   - Compensating actions
   - Dead-letter handling

8. Governance & Controls
   - Task versioning
   - Policy enforcement hooks
   - Manual override model
   - Audit trail requirements

Tone:
System-engineered.
Deterministic.
Failure-aware.
No speculative reasoning logic.

The task engine executes structure. It does not think."