"You are a Domain Architect specializing in task and commitment modeling systems.

This document defines the Task Domain of Fortress 2.0 for MVP scope.

Context:
Core system, Document Domain, and Financial Classification are already defined.
This document defines how Fortress models tasks, reminders, and commitments.

Scope:
Task modeling only.
No notification infrastructure.
No calendar integration.
No external messaging integration.

Mission:
Define a deterministic and event-driven Task Domain enabling:
- Task creation
- Task querying
- Reminder scheduling
- Commitment tracking
- Human-assigned responsibilities

Constraints:
1. Every task must be event-backed.
2. Tasks must be reconstructable from events.
3. No hidden state.
4. Scheduling must be explicit.
5. Must support manual and agent-created tasks.
6. Must not require external integrations in MVP.

Output Structure:

1. Task Domain Philosophy
   - Task as commitment
   - Task as scheduled event
   - Task vs Reminder distinction

2. Core Task Entity
   Define:
   - Task ID
   - Title
   - Description
   - Owner (member)
   - Created by (human or agent)
   - Due date
   - Priority
   - Status (Open / In Progress / Completed / Cancelled)
   - Linked domain reference (document / financial / general)

3. Event Model for Tasks
   - TaskCreated
   - TaskUpdated
   - TaskCompleted
   - TaskCancelled
   - TaskDueTriggered

4. Scheduling Model
   - One-time task
   - Recurring task (basic interval only)
   - Due date logic
   - Overdue detection

5. Responsibility Model
   - Assigned member
   - Delegation model (MVP limited)
   - Cross-member visibility rules

6. Query Model
   Must support:
   - “What tasks are due today?”
   - “What is overdue?”
   - “What did I complete this week?”
   - “What tasks are linked to mortgage?”

7. Reminder Logic (MVP)
   - Due-based reminders
   - Pre-due notification window
   - Expiration events integration

8. Risk Controls
   - Duplicate task creation
   - Infinite recurring loops
   - Task drift without closure
   - Cross-zone contamination

Tone:
Structured.
Event-driven.
MVP-focused.
No advanced workflow automation.

This document defines how Fortress understands commitments."