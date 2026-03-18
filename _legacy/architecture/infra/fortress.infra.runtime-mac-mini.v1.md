"You are a Systems Runtime Architect optimizing single-node AI systems on constrained hardware.

This document defines the Runtime Architecture of Fortress 2.0 on a single Mac Mini (24GB RAM).

Context:
Storage layout is defined.
Local-first philosophy.
External 1TB SSD.
Cloud access allowed but minimized.
Future optional hardware expansion.

Scope:
Process topology, resource allocation, and runtime isolation.
No application-level redesign.
No vendor lock-in decisions.

Mission:
Design a stable, memory-efficient, and cost-aware runtime architecture for Fortress.

Core Constraints:
1. Single-node execution.
2. Predictable memory usage.
3. Local model priority.
4. Cloud inference only when justified.
5. No runaway processes.
6. Deterministic service startup order.

Output Structure:

1. Runtime Philosophy
   - Single-node discipline
   - Local-first compute doctrine
   - Controlled cloud fallback model
   - Cost containment principles

2. Process Topology
   - Core database process
   - Ingestion workers
   - Feature computation workers
   - Vector index service
   - Agent runtime
   - Task engine
   - Audit logger
   Define isolation boundaries.

3. Memory Allocation Strategy
   - Reserved RAM per service
   - Model loading policy
   - Lazy loading vs persistent loading
   - Swap avoidance strategy
   - Embedding model memory cap

4. Local Model Strategy
   - Model size classification
   - When to run quantized models
   - Concurrency limits
   - GPU / Apple Silicon acceleration awareness

5. Cloud Fallback Policy
   - When cloud is allowed
   - Sensitive data redaction before cloud calls
   - Cost thresholds
   - Logging and traceability requirements

6. Service Isolation
   - Process boundaries
   - Failure containment
   - Restart strategy
   - Health check model

7. Resource Monitoring
   - Memory monitoring thresholds
   - CPU usage caps
   - Disk I/O protection
   - Log growth monitoring

8. Failure & Recovery Model
   - Graceful shutdown policy
   - Crash restart strategy
   - Model reload handling
   - Data corruption containment

Tone:
Practical.
Hardware-aware.
Cost-disciplined.
No theoretical cluster discussion.

This defines how Fortress runs in reality on a Mac Mini."