# ARCHIVE STATUS

- Archived: Yes
- Archive Reason: planning document; implementation outcome is now partially verified and differs from the intended end-to-end flow
- Authority: historical / planning reference only
- Read This Instead: `README.md` and `architecture/_meta/fortress.current-state.verified.v1.md`

---

# Controlled Filesystem Inbox Intake Capability — Implementation Plan (v1, revised)

## SECTION 1 — INBOX BOUNDARY

- Inbox is an operator-managed external directory (default `~/FortressInbox`) and is treated strictly as a Zone C intake surface.
- Inbox must remain outside Fortress canonical/raw storage trees; watcher validates configured path is absolute, readable, and not nested under Fortress storage roots.
- Intake source identity uses existing ingestion source primitives:
  - `source_type = 'filesystem_inbox'`
  - `source_key = <normalized absolute inbox directory path>`
- **Decision: no DB migration is required for this capability.** Existing ingestion tables and constraints are sufficient for manual local inbox intake registration.

## SECTION 2 — WATCHER MODEL

- Smallest viable execution model is a manual poll command: `infra/runtime/intake_filesystem_inbox.sh`.
- One invocation processes one deterministic snapshot of inbox files (sorted lexicographically by normalized relative path).
- Watcher responsibilities are strictly limited to:
  1. detect eligible files,
  2. hash file bytes,
  3. copy file to raw storage,
  4. register ingestion writes.
- Watcher performs no AI processing (no classification/extraction/interpretation/normalization).
- **Decision: zero-file polls do not create a run.** Rationale: this capability is manual debugging intake; run rows should represent concrete intake work, avoiding ledger/run noise from idle polls.

## SECTION 3 — HASHING AND IDEMPOTENCY

- Hash algorithm: SHA-256 over exact source bytes.
- Persist digest as `ingestion.raw_object.content_sha256` (`bytea`).
- Idempotency enforcement relies on existing uniqueness contract:
  - `UNIQUE (source_id, object_locator, content_sha256)` on `ingestion.raw_object`.
- **Resolved object_locator policy (explicit):**
  - `object_locator` represents the **original external inbox file path** (normalized absolute path, e.g., `filesystem:///Users/<user>/FortressInbox/subdir/file.pdf`).
  - It does **not** represent the copied raw storage path.
- Why this is correct:
  - Idempotency is explicitly scoped to **external source path + content hash**.
  - Identical content at a **different inbox path** is treated as a **distinct intake object**.
  - Identical content at the **same inbox path** is treated as a **duplicate**.
  - Raw storage placement is an internal implementation detail and may change by storage policy without changing source identity.

## SECTION 4 — RAW STORAGE COPY FLOW

- For each detected file:
  1. read/hash source bytes,
  2. copy bytes (never move) into existing approved raw storage layout,
  3. verify copied-bytes SHA-256 equals source SHA-256,
  4. only then perform raw_object registration.
- Copy uses staged write in raw zone plus atomic finalize (rename) where possible.
- Original inbox file must remain untouched.
- No new raw storage layout is introduced.

## SECTION 5 — INGESTION REGISTRATION

### Explicit Ingestion Write Map (Watcher)

Write Order | Target Table | Required/Conditional | Purpose | Key Fields Written
---|---|---|---|---
1 | `ingestion.source` | Conditional (create-if-missing) | Resolve deterministic source identity for this inbox | `source_type='filesystem_inbox'`, `source_key=<normalized inbox dir>`
2 | `ingestion.run` | Required (only if at least 1 eligible file) | Create ingestion run for this poll batch | `source_id`
3 | `ingestion.run_state` | Required | Mark run start | `run_id`, `state_seq=1`, `state='started'`
4 | `ingestion.raw_object` | Required per successfully copied+verified file | Register intake object | `run_id`, `source_id`, `object_locator=<external inbox file path>`, `content_sha256`, only fields already supported by the existing ingestion contract, with no new payload structure introduced in this phase
5 | `ingestion.run_state` | Conditional per file outcome | Track per-file status progression | `run_id`, incrementing `state_seq`, `state` in `{file_registered,file_duplicate,file_failed}`
6 | `ingestion.error` | Conditional (failure only) | Record deterministic ingestion failure metadata | `run_id`, `stage`, `error_class`, `error_code`, `attempt`, `subject_type`, `subject_id` (if available), `error_fingerprint_sha256`, `details`
7 | `ingestion.run_state` | Required | Mark run completion summary | `run_id`, final `state_seq`, `state='completed'` or `'completed_with_errors'`

- Final required write target is explicitly `ingestion.run_state` (terminal append only), with final state set to `completed` or `completed_with_errors`.

### Registration Rules

- All writes remain in ingestion zone tables only; no direct writes to canonical aggregates.
- Duplicate registration (`raw_object` unique conflict) is treated as deterministic duplicate, not a fatal batch error.
- State sequencing remains append-only and monotonic per run.

## SECTION 6 — OBSERVABILITY

- Reuse existing ingestion event contracts and emitter infrastructure.
- **Decision: event emission is a separate operator-triggered step** (existing `infra/runtime/emit_ingestion_events.sh <run_id>`), not automatic in watcher execution.
- Rationale:
  - preserves current operational pattern,
  - keeps intake command minimal and deterministic,
  - allows operators to inspect ingestion rows before emission during debugging.
- Watcher still prints deterministic summary: discovered/processed/registered/duplicates/failures and resulting run_id.

## SECTION 7 — FAILURE MODES

- **Default policy: continue-on-error within a run.**
- Justification for debugging mode:
  - maximizes diagnostic coverage from one manual poll,
  - surfaces multiple failing files in one execution,
  - preserves successful registrations while still recording failures deterministically.
- Failure handling behavior:
  - inbox unreadable at start: fail before any writes.
  - source file disappears before hash/copy: record `ingestion.error`, append `file_failed`, continue.
  - copy failure (permission/full disk/I/O): record `ingestion.error`, append `file_failed`, continue.
  - post-copy hash mismatch: record integrity error, discard/quarantine temp copy, append `file_failed`, continue.
  - duplicate raw_object conflict: append `file_duplicate`, continue.
- Run terminal state:
  - `completed` if zero failures,
  - `completed_with_errors` if one or more file failures occurred.

## SECTION 8 — FILES TO CHANGE

Planned minimal implementation-phase change set:

1. **Create** `infra/runtime/intake_filesystem_inbox.sh`
   - manual poller implementing detection/hash/copy/registration and deterministic run_state/error handling.
2. **Modify** `README.md`
   - document controlled inbox intake usage and operator emission step.
3. **Possibly modify** `docker-compose.yml`
   - only if explicit env/mount wiring is required in local runtime.
4. **No DB migration planned**.
   - execution proceeds using existing ingestion schema/contracts.

## SECTION 9 — VERIFICATION PLAN

- Happy path:
  1. place deterministic file in inbox,
  2. run intake command,
  3. verify inbox file still exists and hash unchanged,
  4. verify raw copy exists and hash matches,
  5. verify `source/run/run_state/raw_object` writes per map.
- Zero-file behavior:
  - run intake on empty inbox,
  - verify no `ingestion.run` created.
- Idempotency:
  - re-run unchanged inbox file,
  - verify duplicate classification and no duplicate `raw_object` row.
- Observability:
  - run `emit_ingestion_events.sh <run_id>` manually,
  - verify ingestion events are emitted through existing contracts.
- Failure drills:
  - unreadable file,
  - forced copy failure,
  - mid-flight deletion,
  - verify `ingestion.error` rows and `completed_with_errors` terminal run state.

## SECTION 10 — OPEN QUESTIONS

1. Should per-file `subject_id` in `ingestion.error` reference `raw_object_id` only when available, and otherwise remain null with path details in `details`?
2. Should watcher include optional CLI flag for fail-fast override (default remains continue-on-error)?
3. Should watcher persist copied raw path in `details` metadata for operator diagnostics while keeping `object_locator` bound to external source path?
