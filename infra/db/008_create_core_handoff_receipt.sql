-- 008_create_core_handoff_receipt.sql
-- Phase 2B: Deterministic Ingestion (Zone A receipt only)
--
-- Hard requirements:
-- - Create only core.canonical_handoff_receipt
-- - PK handoff_receipt_id uuid NOT NULL DEFAULT uuid_v7()
-- - FK handoff_request_id -> ingestion.canonical_handoff_request(handoff_request_id)
-- - FK applied_event_id -> public.event_ledger(event_id) ON DELETE RESTRICT (NO ACTION)
-- - No triggers, no unique constraints beyond PK
-- - Minimal indexes on FK columns

BEGIN;

CREATE TABLE IF NOT EXISTS core.canonical_handoff_receipt (
  handoff_receipt_id uuid NOT NULL DEFAULT uuid_v7(),
  handoff_request_id uuid NOT NULL,
  applied_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (handoff_receipt_id),
  CONSTRAINT canonical_handoff_receipt_handoff_request_id_fkey
    FOREIGN KEY (handoff_request_id)
    REFERENCES ingestion.canonical_handoff_request(handoff_request_id)
    ON DELETE RESTRICT,
  CONSTRAINT canonical_handoff_receipt_applied_event_id_fkey
    FOREIGN KEY (applied_event_id)
    REFERENCES public.event_ledger(event_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_core_handoff_receipt_handoff_request_id
  ON core.canonical_handoff_receipt(handoff_request_id);

CREATE INDEX IF NOT EXISTS idx_core_handoff_receipt_applied_event_id
  ON core.canonical_handoff_receipt(applied_event_id);

COMMIT;
