-- Enforce UUIDv7 generation at DB level (Phase 1)
-- Source: RFC 9562 time-ordered UUID variant logic implemented in SQL

CREATE OR REPLACE FUNCTION uuid_v7()
RETURNS uuid
LANGUAGE plpgsql
AS $$
DECLARE
  unix_ts_ms bigint;
  rand_bytes bytea;
  uuid_bytes bytea;
BEGIN
  unix_ts_ms := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;

  -- 16 bytes random
  rand_bytes := gen_random_bytes(16);

  -- Build UUIDv7 bytes:
  -- 0-5: 48-bit unix epoch millis
  -- 6:   version (0b0111xxxx)
  -- 7:   random
  -- 8:   variant (0b10xxxxxx)
  -- 9-15 random

  uuid_bytes := decode(lpad(to_hex(unix_ts_ms), 12, '0'), 'hex') || substr(rand_bytes, 7); -- total 16 bytes

  -- Set version 7 in byte 6 (index 7 in 1-based substring)
  uuid_bytes := overlay(uuid_bytes placing set_byte(substr(uuid_bytes, 7, 1), 0, (get_byte(substr(uuid_bytes, 7, 1), 0) & 15) | 112) from 7 for 1);

  -- Set variant 10xxxxxx in byte 8 (index 9)
  uuid_bytes := overlay(uuid_bytes placing set_byte(substr(uuid_bytes, 9, 1), 0, (get_byte(substr(uuid_bytes, 9, 1), 0) & 63) | 128) from 9 for 1);

  RETURN encode(uuid_bytes, 'hex')::uuid;
END;
$$;

-- Apply defaults to primary key id columns
ALTER TABLE person      ALTER COLUMN person_id      SET DEFAULT uuid_v7();
ALTER TABLE household   ALTER COLUMN household_id   SET DEFAULT uuid_v7();
ALTER TABLE account     ALTER COLUMN account_id     SET DEFAULT uuid_v7();
ALTER TABLE asset       ALTER COLUMN asset_id       SET DEFAULT uuid_v7();
ALTER TABLE liability   ALTER COLUMN liability_id   SET DEFAULT uuid_v7();
ALTER TABLE transaction ALTER COLUMN transaction_id SET DEFAULT uuid_v7();
ALTER TABLE document    ALTER COLUMN document_id    SET DEFAULT uuid_v7();
ALTER TABLE contract    ALTER COLUMN contract_id    SET DEFAULT uuid_v7();
ALTER TABLE relationship ALTER COLUMN relationship_id SET DEFAULT uuid_v7();

-- Event ledger: enforce default for event_id only if not provided (still allowed app-side)
ALTER TABLE event_ledger ALTER COLUMN event_id SET DEFAULT uuid_v7();
