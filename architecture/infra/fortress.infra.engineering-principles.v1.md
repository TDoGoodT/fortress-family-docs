"You are the Systems Engineering Authority of Fortress 2.0.

Context:
Fortress 2.0 is:
- A sovereign single-node AI system
- Running on a Mac Mini (24GB RAM)
- Using a 1TB SSD
- Local-first compute
- Potential future open-source project
- Built as a long-term personal system

Mission:
Define the official Engineering Principles that govern all implementation decisions.

Constraints:
1. No over-engineering.
2. No distributed architecture.
3. No microservices explosion.
4. No premature scalability decisions.
5. Everything must be maintainable by a single developer long-term.
6. Must remain compatible with future open-source packaging.

Output Structure:

1. Engineering Philosophy
   - Single-node discipline
   - Deterministic design
   - Simplicity over cleverness
   - Stability over speed
   - Sovereignty over convenience

2. Runtime Architecture Principles
   - Monorepo
   - Docker Compose only
   - No Kubernetes
   - Minimal service count
   - Clear service boundaries

3. Database Strategy
   - PostgreSQL as primary datastore
   - JSONB for flexible payloads
   - Append-only event ledger table
   - No file-based event logging
   - pgvector extension for future embeddings

4. Event Ledger Principles
   - Append-only
   - UUIDv7 IDs
   - Hash chaining
   - No update/delete policy
   - Full replay capability

5. Local Model Strategy
   - Quantized local models
   - Controlled inference queue
   - Memory guardrails
   - Explicit cloud fallback only

6. Infrastructure Constraints
   - No message brokers
   - No distributed queues
   - No background cluster
   - No external dependency required for core function

7. Dev Environment Principles
   - Docker-based reproducibility
   - One command startup
   - Clean reset capability
   - Environment parity between dev and prod

8. Open-Source Readiness Principles
   - No machine-specific paths
   - No hardcoded secrets
   - Environment-variable configuration
   - Clear README onboarding path

Tone:
Authoritative.
Non-speculative.
Strictly implementation-guiding."