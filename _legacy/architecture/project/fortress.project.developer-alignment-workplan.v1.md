"Document ID: fortress.project.developer-alignment-workplan
Version: v1
Layer: project
Status: ACTIVE
Canonical: No
Purpose: Practical developer alignment guide for understanding current status and next execution steps.

# Fortress Developer Alignment Workplan

## 1) Where the project stands now

- The repository already contains a database-first implementation with deterministic migrations and runtime diagnostics.
- The public status in `README.md` is **"Phase 2C complete"**.
- The immediate execution focus is still validation and controlled progression through formal gates before broader product expansion.

## 2) Current gate and readiness reality

Based on the latest Stage A wrap-up artifact:

- **Gate A is still pending**.
- Stage progression to later phases is blocked until Stage A evidence is complete.
- Environment prerequisites were previously missing (`PGURI`, `docker`, `psql`) and must be verified before rerun.

## 3) What to run first (alignment baseline)

Run this exact baseline command sequence in fail-fast order:

1. `infra/db/apply_migrations.sh`
2. `infra/runtime/check_ledger_integrity.sh`
3. `infra/runtime/check_account_projection_consistency.sh`
4. `infra/runtime/check_person_projection_consistency.sh`
5. `infra/runtime/check_projection_consistency.sh`
6. `infra/runtime/check_task_projection_consistency.sh`
7. `infra/runtime/rebuild_core_account_from_ledger.sh`
8. `infra/runtime/rebuild_core_person_from_ledger.sh`
9. `infra/runtime/rebuild_core_document_from_ledger.sh`
10. `infra/runtime/rebuild_core_task_from_ledger.sh`

If any command fails, stop and fix root cause before continuing.

## 4) Recommended weekly execution rhythm

Use this loop to avoid feeling lost and to maintain deterministic progress:

1. **Plan (20 min):** choose one gate objective only (A/B/C...).
2. **Execute (focused block):** implement or validate only that objective.
3. **Prove (evidence):** run required checks and collect outputs.
4. **Record (artifact):** update project artifact with what passed/failed.
5. **Decide:** either close gate or define next blocker-removal micro-task.

## 5) What to avoid during alignment

- Do not add new features while gate prerequisites are red.
- Do not create alternate processor paths for the same aggregate.
- Do not bypass query/security boundaries for convenience testing.
- Do not mutate event ledger history.

## 6) Suggested immediate micro-plan (next 3 sessions)

### Session 1 — Environment and Stage A rerun
- Verify `PGURI`, `docker`, and `psql` availability.
- Re-run full Stage A command set.
- Capture exact outputs and unresolved failures.

### Session 2 — Resolve remaining Stage A blockers
- Fix only blockers discovered in Session 1.
- Re-run failing checks until all Stage A acceptance criteria pass.

### Session 3 — Prepare Stage B entry
- Confirm Gate A evidence pack is complete and internally consistent.
- Define a single aggregate slice for Stage B (account/document/person/task), with no scope expansion.

## 7) Personal alignment checklist (quick daily)

- [ ] I can state the active gate in one sentence.
- [ ] I know exactly which command proves success for today.
- [ ] I am not doing feature work ahead of gate readiness.
- [ ] I updated one artifact so tomorrow starts with full context.

This guide is intentionally execution-first and scope-limited to reduce ambiguity during development.
