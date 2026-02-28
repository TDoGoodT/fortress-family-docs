CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS event_ledger (
    -- NOTE: event_id MUST be UUIDv7, generated app-side in Phase 1 (no DB default)
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Append-only protection
CREATE OR REPLACE FUNCTION prevent_event_update_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'event_ledger is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER event_no_update
BEFORE UPDATE ON event_ledger
FOR EACH ROW EXECUTE FUNCTION prevent_event_update_delete();

CREATE TRIGGER event_no_delete
BEFORE DELETE ON event_ledger
FOR EACH ROW EXECUTE FUNCTION prevent_event_update_delete();
