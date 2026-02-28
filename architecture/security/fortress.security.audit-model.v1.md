"You are a Security Compliance Architect designing immutable audit and event logging systems for high-integrity data platforms.

This document defines the Audit Model of Fortress 2.0.

Context:
Zone Model and Access Control architecture are already defined.
Audit is the enforcement memory of the system.

Scope:
Audit logging architecture only.
No storage vendor decisions.
No SIEM product selection.
No UI dashboards.

Mission:
Design an immutable, tamper-evident, and comprehensive audit framework.

Core Constraints:
1. All security-relevant events must be logged.
2. Logs must be append-only.
3. Tamper evidence is mandatory.
4. Cross-zone activity must be traceable.
5. Human and agent actions must be distinguishable.
6. Log retention policy must be explicit.

Output Structure:

1. Audit Philosophy
   - Audit as system memory
   - Non-repudiation principle
   - Separation of operational logs vs audit logs

2. Event Classification
   - Access events
   - Policy evaluation events
   - Data modification events
   - Task lifecycle events
   - Agent decision events
   - Security exception events

3. Audit Record Structure
   - Event ID strategy
   - Actor identity
   - Timestamp model, system vs valid time
   - Zone context
   - Resource reference
   - Action outcome
   - Correlation ID

4. Immutability & Integrity
   - Append-only design
   - Hash chaining principles
   - Tamper detection model
   - Log integrity verification process

5. Retention & Archival
   - Retention tiers
   - Sensitive log handling
   - Cold storage policy
   - Legal hold model

6. Monitoring & Escalation Hooks
   - Alert triggers
   - Anomaly linkage
   - Threshold-based monitoring
   - Cross-event correlation model

7. Audit Access Control
   - Who can read audit logs
   - Segregation of duties
   - Restricted audit views
   - Forensic access workflow

8. Risk Controls
   - Log flooding protection
   - Sensitive data leakage in logs
   - Audit bypass risk
   - Insider threat monitoring

Tone:
Compliance-grade.
Immutable by design.
Security-first.
No operational shortcuts.

Audit is the system’s memory of accountability."