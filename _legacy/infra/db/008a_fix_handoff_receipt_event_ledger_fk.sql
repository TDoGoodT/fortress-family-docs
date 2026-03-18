-- 008a_fix_handoff_receipt_event_ledger_fk.sql
-- Patch: make event_ledger FK schema-qualified for determinism
-- Scope: core.canonical_handoff_receipt only
-- No triggers, no new uniques.

BEGIN;

ALTER TABLE core.canonical_handoff_receipt
  DROP CONSTRAINT IF EXISTS canonical_handoff_receipt_applied_event_id_fkey;

ALTER TABLE core.canonical_handoff_receipt
  ADD CONSTRAINT canonical_handoff_receipt_applied_event_id_fkey
  FOREIGN KEY (applied_event_id)
  REFERENCES public.event_ledger(event_id)
  ON DELETE RESTRICT;

COMMIT;
