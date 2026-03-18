-- 030_core_person_projection_rule.sql
-- Phase 5: core.person projection rule

BEGIN;

CREATE OR REPLACE VIEW core.ledger_projection_person_created AS
SELECT
    event_id,
    event_timestamp,

    aggregate_id AS person_id,

    CASE
        WHEN NULLIF(payload ->> 'household_id','') IS NULL
        THEN NULL::uuid
        ELSE (payload ->> 'household_id')::uuid
    END AS household_id,

    NULLIF(payload ->> 'display_name','') AS display_name,

    event_timestamp AS created_at

FROM public.event_ledger
WHERE
    aggregate_type = 'core.person'
    AND event_type = 'core.person.created';

INSERT INTO public.schema_migrations(version)
VALUES ('030_core_person_projection_rule.sql');

COMMIT;
