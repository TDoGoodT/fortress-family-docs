-- 029_core_person_created_contract.sql
-- Phase 5: core.person contract surface

CREATE OR REPLACE VIEW core.ledger_contract_person_created AS
SELECT
    'core.person'::text AS aggregate_type,
    target_entity_id AS aggregate_id,
    'core.person.created'::text AS event_type,

    jsonb_build_object(
        'person_id', target_entity_id,
        'handoff_request_id', handoff_request_id,
        'normalized_record_id', normalized_record_id,
        'run_id', run_id,
        'source_id', source_id,
        'display_name', handoff_payload ->> 'display_name',
        'household_id', handoff_payload ->> 'household_id',
        'canonical_record_type', canonical_record_type,
        'schema_version', schema_version
    ) AS payload,

    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_A'::text AS zone_context,

    run_id AS correlation_id,
    handoff_request_id AS causation_id,
    requested_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,

    encode(
        digest(
            concat_ws(
                '|',
                run_id::text,
                'core.person',
                target_entity_id::text,
                'core.person.created',
                md5(
                    jsonb_build_object(
                        'person_id', target_entity_id,
                        'handoff_request_id', handoff_request_id,
                        'normalized_record_id', normalized_record_id,
                        'run_id', run_id,
                        'source_id', source_id,
                        'display_name', handoff_payload ->> 'display_name',
                        'household_id', handoff_payload ->> 'household_id',
                        'canonical_record_type', canonical_record_type,
                        'schema_version', schema_version
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key

FROM core.canonical_handoff_processing_queue q
WHERE
    already_receipted = false
    AND target_entity_id IS NOT NULL
    AND lower(target_entity_type) = ANY (
        ARRAY['person','core.person']
    );
