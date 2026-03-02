BEGIN;

-- ingestion.raw_object
ALTER TABLE ingestion.raw_object
  ADD COLUMN object_locator text NOT NULL,
  ADD COLUMN raw_payload bytea,
  ADD COLUMN raw_payload_json jsonb,
  ADD COLUMN content_sha256 bytea NOT NULL;

-- ingestion.raw_record
ALTER TABLE ingestion.raw_record
  ADD COLUMN record_type text NOT NULL,
  ADD COLUMN record_payload jsonb NOT NULL,
  ADD COLUMN record_external_id text,
  ADD COLUMN record_seq integer NOT NULL,
  ADD COLUMN record_sha256 bytea NOT NULL;

-- ingestion.normalized_record
ALTER TABLE ingestion.normalized_record
  ADD COLUMN canonical_record_type text NOT NULL,
  ADD COLUMN schema_version integer NOT NULL,
  ADD COLUMN normalized_payload jsonb NOT NULL,
  ADD COLUMN normalized_sha256 bytea NOT NULL;

-- ingestion.canonical_handoff_request
ALTER TABLE ingestion.canonical_handoff_request
  ADD COLUMN target_entity_type text NOT NULL,
  ADD COLUMN target_entity_id uuid,
  ADD COLUMN handoff_payload jsonb NOT NULL,
  ADD COLUMN handoff_sha256 bytea NOT NULL;

-- ingestion.error
ALTER TABLE ingestion.error
  ADD COLUMN error_code text NOT NULL,
  ADD COLUMN attempt integer NOT NULL,
  ADD COLUMN error_fingerprint_sha256 bytea NOT NULL;

INSERT INTO public.schema_migrations(version)
VALUES ('010_add_missing_ingestion_columns.sql');

COMMIT;
