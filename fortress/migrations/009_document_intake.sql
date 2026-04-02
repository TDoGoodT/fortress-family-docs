-- Migration 009: Document Intake & Retrieval
-- Adds tags, confidence, review_state to documents table.
-- Creates document_facts table for structured fact storage.
-- All DDL uses IF NOT EXISTS for idempotency.

BEGIN;

-- Extend documents table with new columns only
-- (doc_type, vendor, doc_date, ai_summary, raw_text already exist)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS confidence DECIMAL DEFAULT 0.0;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_state TEXT DEFAULT 'pending';

-- Flexible fact storage table
CREATE TABLE IF NOT EXISTS document_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    fact_type TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    confidence DECIMAL DEFAULT 0.0,
    source_excerpt TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_document_facts_document_id ON document_facts(document_id);
CREATE INDEX IF NOT EXISTS idx_document_facts_fact_key ON document_facts(fact_key);

COMMIT;
