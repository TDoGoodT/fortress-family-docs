-- 006_create_ingestion_schema.sql
-- Phase 2B: Deterministic Ingestion (Schema bootstrap only)
--
-- Governance notes:
-- - Phase 1 Event Ledger remains physically located at: public.event_ledger
-- - This migration MUST NOT modify public.event_ledger or any Phase 1 core tables.
-- - New ingestion pipeline tables will live under schema: ingestion (Zone C).
-- - Zone A receipt table will live under schema: core (Zone A), created in a later migration.

BEGIN;

-- Required for deterministic hashing (SHA-256) in later migrations (idempotency primitives).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Zone C schema: ingestion pipeline tables.
CREATE SCHEMA IF NOT EXISTS ingestion;

-- Zone A schema: receipt table only (Phase 2B). Phase 1 tables remain in public.
CREATE SCHEMA IF NOT EXISTS core;

COMMIT;
