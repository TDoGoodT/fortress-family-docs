-- 023_contract_envelope_alignment.sql
--
-- Version Authority (explicit):
-- - fortress.ingestion.pipeline-architecture.v3
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Canonical Phase 3B rule:
-- - Per-contract views remain semantic contract surfaces
-- - Unified queue view becomes transport ordering surface
-- - Emitter reads only from ingestion.ledger_contract_emit_queue
--   and orders by emit_seq only
--
-- Scope:
-- - Views only (read-only contract)
-- - No triggers, no functions, no tables, no schema changes beyond views
-- - No writes to public.event_ledger
--
-- Fixed ingestion system actor UUID (Option B, Master-approved constant):
-- - 00000000-0000-7000-8000-00000000000c

BEGIN;

-- ============================================================================
-- Envelope-aligned semantic contract views
-- - actor_type = 'system'
-- - actor_id   = fixed ingestion actor UUID
-- - zone_context = 'ZONE_C'
-- - emit_dedup_key = deterministic, identical recipe across all contracts
-- ============================================================================

CREATE OR REPLACE VIEW ingestion.ledger_contract_run_created AS
SELECT
    'ingestion.run'::text AS aggregate_type,
    r.run_id AS aggregate_id,
    'ingestion.run.created'::text AS event_type,
    jsonb_build_object(
        'run_id', r.run_id,
        'source_id', r.source_id
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    r.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    r.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                r.run_id::text,
                'ingestion.run',
                r.run_id::text,
                'ingestion.run.created',
                md5(
                    jsonb_build_object(
                        'run_id', r.run_id,
                        'source_id', r.source_id
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.run r;

COMMENT ON VIEW ingestion.ledger_contract_run_created IS
'Contract: proposed event_ledger row(s) for ingestion.run creation. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_run_state_appended AS
SELECT
    'ingestion.run'::text AS aggregate_type,
    rs.run_id AS aggregate_id,
    'ingestion.run_state.appended'::text AS event_type,
    jsonb_build_object(
        'run_id', rs.run_id,
        'state', rs.state,
        'state_seq', rs.state_seq
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    rs.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    rs.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                rs.run_id::text,
                'ingestion.run',
                rs.run_id::text,
                'ingestion.run_state.appended',
                md5(
                    jsonb_build_object(
                        'run_id', rs.run_id,
                        'state', rs.state,
                        'state_seq', rs.state_seq
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.run_state rs;

COMMENT ON VIEW ingestion.ledger_contract_run_state_appended IS
'Contract: proposed event_ledger row(s) for ingestion.run_state append. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_raw_object_ingested AS
SELECT
    'ingestion.raw_object'::text AS aggregate_type,
    ro.raw_object_id AS aggregate_id,
    'ingestion.raw_object.ingested'::text AS event_type,
    jsonb_build_object(
        'raw_object_id', ro.raw_object_id,
        'run_id', ro.run_id,
        'source_id', ro.source_id,
        'object_locator', ro.object_locator,
        'content_sha256_hex', encode(ro.content_sha256, 'hex')
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    ro.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    ro.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                ro.run_id::text,
                'ingestion.raw_object',
                ro.raw_object_id::text,
                'ingestion.raw_object.ingested',
                md5(
                    jsonb_build_object(
                        'raw_object_id', ro.raw_object_id,
                        'run_id', ro.run_id,
                        'source_id', ro.source_id,
                        'object_locator', ro.object_locator,
                        'content_sha256_hex', encode(ro.content_sha256, 'hex')
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.raw_object ro;

COMMENT ON VIEW ingestion.ledger_contract_raw_object_ingested IS
'Contract: proposed event_ledger row(s) for ingestion.raw_object ingestion. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_raw_record_created AS
SELECT
    'ingestion.raw_record'::text AS aggregate_type,
    rr.raw_record_id AS aggregate_id,
    'ingestion.raw_record.created'::text AS event_type,
    jsonb_build_object(
        'raw_record_id', rr.raw_record_id,
        'raw_object_id', rr.raw_object_id,
        'run_id', rr.run_id,
        'source_id', rr.source_id,
        'record_seq', rr.record_seq,
        'record_sha256_hex', encode(rr.record_sha256, 'hex')
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    rr.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    rr.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                rr.run_id::text,
                'ingestion.raw_record',
                rr.raw_record_id::text,
                'ingestion.raw_record.created',
                md5(
                    jsonb_build_object(
                        'raw_record_id', rr.raw_record_id,
                        'raw_object_id', rr.raw_object_id,
                        'run_id', rr.run_id,
                        'source_id', rr.source_id,
                        'record_seq', rr.record_seq,
                        'record_sha256_hex', encode(rr.record_sha256, 'hex')
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.raw_record rr;

COMMENT ON VIEW ingestion.ledger_contract_raw_record_created IS
'Contract: proposed event_ledger row(s) for ingestion.raw_record creation. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_normalized_record_created AS
SELECT
    'ingestion.normalized_record'::text AS aggregate_type,
    nr.normalized_record_id AS aggregate_id,
    'ingestion.normalized_record.created'::text AS event_type,
    jsonb_build_object(
        'normalized_record_id', nr.normalized_record_id,
        'raw_record_id', nr.raw_record_id,
        'run_id', nr.run_id,
        'source_id', nr.source_id,
        'schema_version', nr.schema_version,
        'normalized_sha256_hex', encode(nr.normalized_sha256, 'hex')
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    nr.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    nr.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                nr.run_id::text,
                'ingestion.normalized_record',
                nr.normalized_record_id::text,
                'ingestion.normalized_record.created',
                md5(
                    jsonb_build_object(
                        'normalized_record_id', nr.normalized_record_id,
                        'raw_record_id', nr.raw_record_id,
                        'run_id', nr.run_id,
                        'source_id', nr.source_id,
                        'schema_version', nr.schema_version,
                        'normalized_sha256_hex', encode(nr.normalized_sha256, 'hex')
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.normalized_record nr;

COMMENT ON VIEW ingestion.ledger_contract_normalized_record_created IS
'Contract: proposed event_ledger row(s) for ingestion.normalized_record creation. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_canonical_handoff_request_created AS
SELECT
    'ingestion.canonical_handoff_request'::text AS aggregate_type,
    chr.handoff_request_id AS aggregate_id,
    'ingestion.canonical_handoff_request.created'::text AS event_type,
    jsonb_build_object(
        'handoff_request_id', chr.handoff_request_id,
        'run_id', chr.run_id,
        'normalized_record_id', chr.normalized_record_id,
        'target_entity_type', chr.target_entity_type,
        'target_entity_id', chr.target_entity_id,
        'handoff_sha256', encode(chr.handoff_sha256, 'hex'),
        'handoff_payload', chr.handoff_payload
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    chr.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    chr.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                chr.run_id::text,
                'ingestion.canonical_handoff_request',
                chr.handoff_request_id::text,
                'ingestion.canonical_handoff_request.created',
                md5(
                    jsonb_build_object(
                        'handoff_request_id', chr.handoff_request_id,
                        'run_id', chr.run_id,
                        'normalized_record_id', chr.normalized_record_id,
                        'target_entity_type', chr.target_entity_type,
                        'target_entity_id', chr.target_entity_id,
                        'handoff_sha256', encode(chr.handoff_sha256, 'hex'),
                        'handoff_payload', chr.handoff_payload
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.canonical_handoff_request chr;

COMMENT ON VIEW ingestion.ledger_contract_canonical_handoff_request_created IS
'Contract: proposed event_ledger row(s) for ingestion.canonical_handoff_request creation. Read-only. Envelope aligned for Phase 3B.';

CREATE OR REPLACE VIEW ingestion.ledger_contract_error_recorded AS
SELECT
    'ingestion.error'::text AS aggregate_type,
    e.ingestion_error_id AS aggregate_id,
    'ingestion.error.recorded'::text AS event_type,
    jsonb_build_object(
        'ingestion_error_id', e.ingestion_error_id,
        'run_id', e.run_id,
        'stage', e.stage,
        'subject_type', e.subject_type,
        'subject_id', e.subject_id,
        'error_fingerprint_sha256_hex', encode(e.error_fingerprint_sha256, 'hex'),
        'attempt', e.attempt
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_C'::text AS zone_context,
    e.run_id AS correlation_id,
    NULL::uuid AS causation_id,
    e.created_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                e.run_id::text,
                'ingestion.error',
                e.ingestion_error_id::text,
                'ingestion.error.recorded',
                md5(
                    jsonb_build_object(
                        'ingestion_error_id', e.ingestion_error_id,
                        'run_id', e.run_id,
                        'stage', e.stage,
                        'subject_type', e.subject_type,
                        'subject_id', e.subject_id,
                        'error_fingerprint_sha256_hex', encode(e.error_fingerprint_sha256, 'hex'),
                        'attempt', e.attempt
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM ingestion.error e;

COMMENT ON VIEW ingestion.ledger_contract_error_recorded IS
'Contract: proposed event_ledger row(s) for ingestion.error events. Read-only. Envelope aligned for Phase 3B.';

-- ============================================================================
-- Unified transport ordering surface
-- - Global deterministic order per emit_scope_id (= correlation_id)
-- - Emitter reads only from this view and ORDER BY emit_seq
-- ============================================================================

CREATE OR REPLACE VIEW ingestion.ledger_contract_emit_queue AS
WITH unified AS (
    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        1::integer AS event_phase_precedence,
        c.aggregate_id::text AS source_key_1,
        NULL::text AS source_key_2
    FROM ingestion.ledger_contract_run_created c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        2::integer AS event_phase_precedence,
        (c.payload ->> 'state_seq') AS source_key_1,
        c.aggregate_id::text AS source_key_2
    FROM ingestion.ledger_contract_run_state_appended c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        3::integer AS event_phase_precedence,
        c.aggregate_id::text AS source_key_1,
        NULL::text AS source_key_2
    FROM ingestion.ledger_contract_raw_object_ingested c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        4::integer AS event_phase_precedence,
        lpad((c.payload ->> 'record_seq'), 12, '0') AS source_key_1,
        c.aggregate_id::text AS source_key_2
    FROM ingestion.ledger_contract_raw_record_created c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        5::integer AS event_phase_precedence,
        c.aggregate_id::text AS source_key_1,
        NULL::text AS source_key_2
    FROM ingestion.ledger_contract_normalized_record_created c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        6::integer AS event_phase_precedence,
        c.aggregate_id::text AS source_key_1,
        NULL::text AS source_key_2
    FROM ingestion.ledger_contract_canonical_handoff_request_created c

    UNION ALL

    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key,
        c.correlation_id AS emit_scope_id,
        7::integer AS event_phase_precedence,
        lpad((c.payload ->> 'attempt'), 12, '0') AS source_key_1,
        c.aggregate_id::text AS source_key_2
    FROM ingestion.ledger_contract_error_recorded c
)
SELECT
    row_number() OVER (
        PARTITION BY u.emit_scope_id
        ORDER BY
            u.event_timestamp ASC,
            u.event_phase_precedence ASC,
            u.source_key_1 ASC,
            u.source_key_2 ASC NULLS FIRST,
            u.aggregate_id ASC,
            u.event_type ASC
    )::bigint AS emit_seq,
    u.emit_scope_id,
    u.aggregate_type,
    u.aggregate_id,
    u.event_type,
    u.payload,
    u.actor_type,
    u.actor_id,
    u.zone_context,
    u.correlation_id,
    u.causation_id,
    u.event_timestamp,
    u.valid_timestamp,
    u.emit_dedup_key,
    u.event_phase_precedence,
    u.source_key_1,
    u.source_key_2
FROM unified u;

COMMENT ON VIEW ingestion.ledger_contract_emit_queue IS
'Transport ordering surface for ingestion event emission. Global deterministic emit_seq per emit_scope_id (= correlation_id). Emitter must read only from this view and ORDER BY emit_seq.';

INSERT INTO public.schema_migrations(version)
VALUES ('023_contract_envelope_alignment.sql');

COMMIT;
