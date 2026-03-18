-- 024_canonical_handoff_processor_contract.sql
--
-- Version Authority (explicit):
-- - fortress.ingestion.pipeline-architecture.v3
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 4A only:
-- - Processing contract + receipt-oriented decision surface
-- - No canonical aggregate writes
-- - No triggers, no functions, no workers
--
-- Hard scope rule:
-- Canonical aggregate mutation is out of scope until canonical aggregate
-- schema placement is formally resolved.
--
-- Allowed canonical target in this phase:
-- - core.canonical_handoff_receipt
--
-- Purpose:
-- - define a deterministic processing queue for canonical handoff handling
-- - prevent runtime logic from inventing ordering rules
-- - expose receipt status as derived/read-only state

BEGIN;

CREATE OR REPLACE VIEW core.canonical_handoff_processing_queue AS
WITH base AS (
    SELECT
        chr.handoff_request_id,
        chr.normalized_record_id,
        chr.target_entity_type,
        chr.target_entity_id,
        chr.handoff_payload,
        chr.run_id,
        nr.source_id,
        chr.run_id AS processing_scope_id,
        chr.created_at AS requested_at,
        nr.created_at AS normalized_at,
        nr.canonical_record_type,
        nr.schema_version,
        encode(chr.handoff_sha256, 'hex') AS handoff_sha256_hex,
        EXISTS (
            SELECT 1
            FROM core.canonical_handoff_receipt chrp
            WHERE chrp.handoff_request_id = chr.handoff_request_id
        ) AS already_receipted,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM core.canonical_handoff_receipt chrp
                WHERE chrp.handoff_request_id = chr.handoff_request_id
            )
            THEN 'receipted'::text
            ELSE 'pending_receipt'::text
        END AS processing_status,
        1::integer AS processing_phase_precedence,
        chr.created_at AS order_ts_1,
        nr.created_at AS order_ts_2,
        chr.normalized_record_id::text AS order_key_1,
        COALESCE(chr.target_entity_type, '') AS order_key_2,
        COALESCE(chr.target_entity_id::text, '') AS order_key_3,
        chr.handoff_request_id::text AS order_key_4
    FROM ingestion.canonical_handoff_request chr
    INNER JOIN ingestion.normalized_record nr
        ON nr.normalized_record_id = chr.normalized_record_id
)
SELECT
    row_number() OVER (
        PARTITION BY b.processing_scope_id
        ORDER BY
            b.order_ts_1 ASC,
            b.processing_phase_precedence ASC,
            b.order_ts_2 ASC,
            b.order_key_1 ASC,
            b.order_key_2 ASC,
            b.order_key_3 ASC,
            b.order_key_4 ASC
    )::bigint AS process_seq,
    b.processing_scope_id,
    b.handoff_request_id,
    b.normalized_record_id,
    b.target_entity_type,
    b.target_entity_id,
    b.handoff_payload,
    b.run_id,
    b.source_id,
    b.canonical_record_type,
    b.schema_version,
    b.requested_at,
    b.normalized_at,
    b.already_receipted,
    b.processing_status,
    b.handoff_sha256_hex,
    b.processing_phase_precedence,
    b.order_ts_1,
    b.order_ts_2,
    b.order_key_1,
    b.order_key_2,
    b.order_key_3,
    b.order_key_4
FROM base b;

COMMENT ON VIEW core.canonical_handoff_processing_queue IS
'Deterministic processing queue for canonical handoff handling, Phase 4A only. Receipt-oriented, read-only. Canonical aggregate mutation is out of scope until canonical aggregate schema placement is formally resolved.';

INSERT INTO public.schema_migrations(version)
VALUES ('024_canonical_handoff_processor_contract.sql');

COMMIT;
