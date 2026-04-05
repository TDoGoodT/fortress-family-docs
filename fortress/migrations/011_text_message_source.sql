-- Migration 011: Add 'text_message' to documents source CHECK constraint
-- Required for text-based knowledge ingestion (Sprint 1)

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_check;
ALTER TABLE documents ADD CONSTRAINT documents_source_check
    CHECK (source IN ('whatsapp', 'email', 'filesystem', 'manual', 'text_message'));
