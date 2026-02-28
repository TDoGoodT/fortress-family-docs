-- Deterministic hash chaining for event_ledger (Phase 1)
-- Enforces:
--  previous_event_hash = last current_event_hash
--  current_event_hash  = sha256(canonical event text + previous_event_hash)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Remove non-deterministic default if present
ALTER TABLE event_ledger
  ALTER COLUMN current_event_hash DROP DEFAULT;

CREATE OR REPLACE FUNCTION event_ledger_compute_hash_chain()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  prev_hash bytea;
  canon_text text;
BEGIN
  -- Get the last hash in the ledger (global chain)
  SELECT el.current_event_hash
    INTO prev_hash
  FROM event_ledger el
  ORDER BY el.created_at DESC, el.event_id DESC
  LIMIT 1;

  -- Enforce no manual override that breaks chain
  IF NEW.previous_event_hash IS NOT NULL AND NEW.previous_event_hash <> prev_hash THEN
    RAISE EXCEPTION 'previous_event_hash override not allowed (expected chain head)';
  END IF;

  IF NEW.current_event_hash IS NOT NULL THEN
    RAISE EXCEPTION 'current_event_hash is computed and cannot be provided';
  END IF;

  NEW.previous_event_hash := prev_hash;

  -- Canonical text for deterministic hashing.
  -- jsonb::text is deterministic (sorted keys) in Postgres, suitable for canonicalization here.
  canon_text := concat_ws(
    '|',
    NEW.event_id::text,
    NEW.aggregate_type,
    NEW.aggregate_id::text,
    NEW.event_type,
    NEW.payload::text,
    NEW.actor_type,
    NEW.actor_id::text,
    NEW.zone_context,
    NEW.correlation_id::text,
    COALESCE(NEW.causation_id::text, ''),
    NEW.event_timestamp::text,
    COALESCE(NEW.valid_timestamp::text, ''),
    COALESCE(encode(NEW.previous_event_hash, 'hex'), '')
  );

  NEW.current_event_hash := digest(canon_text, 'sha256');
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS event_hash_chain_insert ON event_ledger;

CREATE TRIGGER event_hash_chain_insert
BEFORE INSERT ON event_ledger
FOR EACH ROW
EXECUTE FUNCTION event_ledger_compute_hash_chain();
