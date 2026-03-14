"Document ID: fortress.project.stage-a-baseline-evidence
Version: v1
Layer: project
Status: DRAFT
Canonical: No
Purpose: Stage A baseline verification evidence pack (execution attempt under current environment).

## 1) Micro-Scope

Deliverables:
1. Attempt Stage A baseline command execution for migration and integrity checks.
2. Capture deterministic command outputs as evidence.
3. Report gate status and environment blockers.

## 2) Source Documents (ID + version)

- `fortress.project.execution-plan-to-production.v1`
- `fortress.project.master-control.v1`
- `fortress.project.qa-governance.v1`
- `fortress.project.dependency-model.v2`
- `fortress.core.event-ledger.v1`

## 3) Commands Executed and Raw Outputs

### Command A
`./infra/db/apply_migrations.sh`

Output:
`ERROR: PGURI is not set. Example:
  export PGURI='host=127.0.0.1 port=5432 dbname=fortress user=fortress password=fortress_dev_password'`

Result:
- BLOCKED (environment variable not configured).

### Command B
`./infra/runtime/check_ledger_integrity.sh`

Output:
`Phase 4E: ledger integrity diagnostics
./infra/runtime/check_ledger_integrity.sh: line 6: docker: command not found`

Result:
- BLOCKED (runtime dependency `docker` unavailable).

## 4) Acceptance Checklist (Stage A)

- [ ] Migrations applied on clean DB using controlled runner.
- [ ] Ledger integrity diagnostics executed successfully.
- [ ] Projection consistency checks executed successfully.
- [ ] Deterministic rebuild checks executed successfully.
- [ ] Legacy/deprecated script hygiene verified.

Current status:
- Stage A gate is **NOT PASSING** due to environment prerequisites not met.

## 5) Risks and Non-Goals

Risks:
- Running additional Stage A scripts without PostgreSQL connectivity and Docker runtime will produce non-actionable failures.
- Proceeding to Stage B without Stage A pass violates execution governance.

Non-goals in this evidence cycle:
- No schema changes.
- No runtime logic changes.
- No event ledger writes.

## 6) Required Environment Prerequisites to Unblock Stage A

1. Provide `PGURI` pointing to Fortress PostgreSQL instance.
2. Ensure Docker CLI is installed and available in PATH if runtime scripts depend on `docker compose exec`.
3. Ensure PostgreSQL container/service is running and reachable with configured credentials.

## 7) Master Approval Request

Requesting Master acknowledgment of Stage A blocked state due to environment prerequisites, and approval to rerun Stage A immediately once prerequisites are provided.

## 8) Prerequisite Verification Snapshot (Post-Ruling)

Commands:
- `if [ -n "${PGURI:-}" ]; then echo "PGURI_SET"; else echo "PGURI_MISSING"; fi`
- `if command -v docker >/dev/null 2>&1; then echo "DOCKER_PRESENT"; else echo "DOCKER_MISSING"; fi`
- `if command -v psql >/dev/null 2>&1; then echo "PSQL_PRESENT"; else echo "PSQL_MISSING"; fi`

Observed outputs:
- `PGURI_MISSING`
- `DOCKER_MISSING`
- `PSQL_MISSING`

Interpretation:
- Stage A rerun remains blocked because required execution prerequisites are still not available in the current environment.
- No Stage A deterministic validation commands can complete successfully until prerequisites are provisioned.

## 9) Master-Directed Prerequisite Provisioning and Stage A Rerun Protocol

### 9.1 Provisioning Checklist (must be TRUE before rerun)

- [ ] `PGURI` is set to a reachable Fortress PostgreSQL instance.
- [ ] `docker` CLI is installed and available in PATH.
- [ ] `psql` CLI is installed and available in PATH.
- [ ] PostgreSQL service/container is running and accepting connections.

Deterministic probes:
- `if [ -n "${PGURI:-}" ]; then echo "PGURI_SET"; else echo "PGURI_MISSING"; fi`
- `if command -v docker >/dev/null 2>&1; then echo "DOCKER_PRESENT"; else echo "DOCKER_MISSING"; fi`
- `if command -v psql >/dev/null 2>&1; then echo "PSQL_PRESENT"; else echo "PSQL_MISSING"; fi`

Expected gate-open outputs:
- `PGURI_SET`
- `DOCKER_PRESENT`
- `PSQL_PRESENT`

### 9.2 Stage A Rerun Command Set (execute only after gate-open probes)

1. `./infra/db/apply_migrations.sh`
2. `./infra/runtime/check_ledger_integrity.sh`
3. `./infra/runtime/check_account_projection_consistency.sh`
4. `./infra/runtime/check_person_projection_consistency.sh`
5. `./infra/runtime/check_projection_consistency.sh`
6. `./infra/runtime/check_task_projection_consistency.sh`
7. `./infra/runtime/rebuild_core_account_from_ledger.sh`
8. `./infra/runtime/rebuild_core_person_from_ledger.sh`
9. `./infra/runtime/rebuild_core_document_from_ledger.sh`
10. `./infra/runtime/rebuild_core_task_from_ledger.sh`

Fail-fast rule:
- Any non-zero exit code halts Stage A and requires updated evidence submission before retry.

### 9.3 Deterministic Submission Bundle for Master Gate A

Required artifacts:
- Full command transcript for probes + rerun command set.
- Pass/fail matrix for each command.
- Updated acceptance checklist status.
- Any blocker details with exact stderr output.

Gate decision rule:
- Stage A can be marked PASS only when all commands above complete successfully and no invariant violations are reported.

## 10) Execution Readiness Gate State (Current)

Gate state:
- `MASTER_APPROVED_PROTOCOL`: TRUE
- `ENVIRONMENT_READY_FOR_STAGE_A_RERUN`: FALSE

External prerequisites pending (platform-provisioned):
1. `PGURI` must be configured for reachable Fortress PostgreSQL.
2. Docker CLI must be installed and available in PATH.
3. `psql` CLI must be installed and available in PATH.

Execution-owned actions once environment is ready:
1. Re-run prerequisite probes and record outputs.
2. Execute full Stage A rerun command set (Section 9.2) with fail-fast behavior.
3. Submit deterministic Gate A evidence pack per Section 9.3.

Progression rule:
- No transition to Stage B is permitted unless Stage A checklist is fully passing and Master signs Gate A.

## 11) Gate-Flag Transition Control (Master-Ruled)

Current enforced value:
- `ENVIRONMENT_READY_FOR_STAGE_A_RERUN: FALSE`

Transition policy (`FALSE -> TRUE`):
- Transition is allowed only when all prerequisite probes return gate-open outputs:
  - `PGURI_SET`
  - `DOCKER_PRESENT`
  - `PSQL_PRESENT`
- Transition must be accompanied by command transcript evidence in this artifact.

Execution after transition:
1. Execute full Stage A rerun command set (Section 9.2).
2. Apply fail-fast rule for any non-zero exit code.
3. Submit deterministic Gate A bundle (Section 9.3) for Master decision.

Post-condition:
- Stage B remains blocked unless Stage A checklist is fully passing and Master Gate A is explicitly signed.

## 12) Stage A Execution Cycle (Current Attempt)

Cycle objective:
- Execute Stage A baseline command set under fail-fast governance and capture deterministic outputs.

Prerequisite probes (pre-run):
- `PGURI_MISSING`
- `DOCKER_MISSING`
- `PSQL_MISSING`

Execution trace:
1. Ran `./infra/db/apply_migrations.sh`
2. Output:
   - `ERROR: PGURI is not set. Example:`
   - `export PGURI='host=127.0.0.1 port=5432 dbname=fortress user=fortress password=fortress_dev_password'`
3. Fail-fast outcome:
   - Stage A command chain halted at first command due unmet prerequisite.
   - Remaining Stage A commands were not executed in this cycle.

Gate flag update:
- `ENVIRONMENT_READY_FOR_STAGE_A_RERUN: FALSE` (unchanged; prerequisites still unmet)
- `GATE_A_STATUS: PENDING` (Stage A baseline verification not complete)

Checkpoint statement:
- This artifact now contains the latest deterministic execution boundary for continuation in the next Codex App session.

