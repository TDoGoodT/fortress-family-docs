-- 028_core_person_alignment.sql
-- Phase 5: core.person aggregate introduction

BEGIN;

CREATE TABLE IF NOT EXISTS core.person (
    person_id    uuid PRIMARY KEY,
    household_id uuid NOT NULL,
    display_name text NOT NULL,
    created_at   timestamptz NOT NULL
);

INSERT INTO public.schema_migrations(version)
VALUES ('028_core_person_alignment.sql');

COMMIT;
