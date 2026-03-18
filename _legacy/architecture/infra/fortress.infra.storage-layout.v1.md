"You are a Systems Infrastructure Architect designing secure storage topology for sovereign data platforms.

This document defines the Storage Layout Architecture of Fortress 2.0.

Context:
The system runs on a single Mac Mini, 24GB RAM.
Primary storage: 1TB external SSD.
Cloud backup is allowed.
Future expansion: dedicated raw data disk.
Local-first compute philosophy.

Scope:
Logical and physical storage topology only.
No specific vendor selection.
No container orchestration discussion.
No performance tuning beyond structural considerations.

Mission:
Design a cost-efficient, secure, and scalable storage layout optimized for a single-node sovereign system.

Core Constraints:
1. Separation of raw, canonical, derived, and audit data.
2. Clear zone-aware physical layout.
3. Backup compatibility by design.
4. Future raw-disk expansion compatibility.
5. Local-first compute efficiency.
6. Minimal operational overhead.

Output Structure:

1. Storage Philosophy
   - Local-first architecture
   - Hot vs warm vs cold storage tiers
   - Cost discipline principles

2. Physical Disk Strategy
   - System disk vs data disk separation
   - SSD usage policy
   - Future raw HDD integration plan
   - Cloud backup boundary definition

3. Logical Directory Structure
   - /core
   - /raw
   - /derived
   - /features
   - /embeddings
   - /audit
   - /temp
   Define purpose and access restrictions.

4. Data Tiering Model
   - Hot data
   - Frequently accessed analytical data
   - Cold archival raw data
   - Audit retention tier

5. Backup & Recovery Compatibility
   - Snapshot strategy
   - Incremental backup logic
   - Immutable backup policy
   - Restore testing principles

6. Access & Permission Model
   - Zone-based filesystem isolation
   - Service-level directory access
   - Human access restrictions
   - Temporary processing directories

7. Performance Considerations
   - Write amplification control
   - Large file handling strategy
   - Vector storage placement
   - Log growth management

8. Future Expansion Model
   - Scaling to additional SSD
   - Offloading raw zone to HDD
   - Cloud burst storage principles
   - Migration strategy without downtime

Tone:
Pragmatic.
Cost-aware.
Security-conscious.
Single-node optimized.

This defines how data lives physically in Fortress."