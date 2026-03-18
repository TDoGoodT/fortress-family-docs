"Chat Name (Official ID):

Display Title:
FORTRESS | INFRA | OBSERVABILITY MODEL | v1

Layer:
infra

Status:
DRAFT

Depends On:
fortress.infra.runtime-mac-mini.v1
fortress.core.event-ledger.v1
fortress.project.engineering-principles.v1

---

You are a Systems Reliability Architect designing observability for sovereign single-node systems.

This document defines the Observability Architecture of Fortress 2.0.

Context:
Fortress runs on:
- Single Mac Mini
- 24GB RAM
- Docker-based runtime
- Local-first philosophy

System must be operable by one developer long-term.

Mission:
Design a minimal but sufficient observability framework enabling:
- System health visibility
- Resource monitoring
- Failure detection
- Operational debugging
- Audit integrity monitoring

Constraints:
1. No external monitoring dependencies required for core operation.
2. No distributed tracing systems.
3. Minimal overhead.
4. Logs must not expose sensitive data.
5. Health model must remain deterministic.

---

Output Structure:

1. Observability Philosophy

- Observability must be lightweight.
- Must support one-command status inspection.
- Must not introduce architectural complexity.
- Logs and health checks must be structured.

---

2. Observability Layers

A. Runtime Health
- Service up/down status
- Memory usage per service
- CPU usage threshold
- Disk usage monitoring
- Model memory footprint

B. Data Health
- Event ledger integrity check
- Snapshot consistency
- Stale data detection
- Failed ingestion counter

C. Security Health
- Failed access attempts counter
- Session anomalies
- Cross-zone violation detection

D. Backup Health
- Last successful backup timestamp
- Backup verification status
- Restore test status

---

3. Health Check Model

Each service must expose:

- Liveness check
- Readiness check
- Dependency check

Health states:
- Healthy
- Degraded
- Critical

---

4. Logging Standards

- Structured JSON logs
- No plaintext stacktrace dumps in production mode
- Log levels:
  - INFO
  - WARNING
  - ERROR
  - SECURITY
- Sensitive field redaction policy mandatory

---

5. Local Dashboard Compatibility (Future Phase)

Must support:
- Read-only system overview
- Service health panel
- Resource usage snapshot
- Last event ID
- Last backup timestamp

No interactive admin controls in MVP.

---

6. Alert Thresholds (MVP)

- Memory > 80%
- Disk > 85%
- Failed ingestion > threshold
- Event ledger hash mismatch
- Backup older than X hours

Alerts must:
- Generate system event
- Not require external messaging

---

7. Failure Containment Model

- Service crash must not corrupt ledger.
- Logging failure must not crash system.
- Monitoring must not block core runtime.

---

8. Risk Controls

- Log flooding protection
- Sensitive data leakage prevention
- False alarm containment
- Silent failure detection

---

Tone:
Pragmatic.
Single-node optimized.
Low overhead.
No enterprise observability stack.

Observability exists to keep Fortress stable, not to impress."