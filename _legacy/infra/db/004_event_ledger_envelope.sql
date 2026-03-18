-- Event Ledger envelope (Phase 1)
-- Adds traceability + integrity fields required for reconstructability.

-- Ensure crypto primitives exist (digest, gen_random_bytes)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Traceability envelope
ALTER TABLE event_ledger
  ADD COLUMN IF NOT EXISTS actor_type       TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS actor_id         UUID NOT NULL DEFAULT uuid_v7(),
  ADD COLUMN IF NOT EXISTS zone_context     TEXT NOT NULL DEFAULT 'core',
  ADD COLUMN IF NOT EXISTS correlation_id   UUID NOT NULL DEFAULT uuid_v7(),
  ADD COLUMN IF NOT EXISTS causation_id     UUID,
  ADD COLUMN IF NOT EXISTS event_timestamp  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS valid_timestamp  TIMESTAMPTZ;

-- Integrity envelope (hash chaining fields)
-- NOTE: Hash computation is structurally present. Actual canonical hashing rules will be finalized when Event Ledger v1 exits DRAFT.
ALTER TABLE event_ledger
  ADD COLUMN IF NOT EXISTS previous_event_hash BYTEA,
  ADD COLUMN IF NOT EXISTS current_event_hash  BYTEA NOT NULL DEFAULT gen_random_bytes(32);
