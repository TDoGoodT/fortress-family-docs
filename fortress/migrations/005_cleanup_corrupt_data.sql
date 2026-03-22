-- Migration 005: Cleanup corrupt Ollama-era data
-- All operations use soft-delete (status = 'archived'), never SQL DELETE.
-- Idempotent: safe to run multiple times.

-- 1. Archive tasks with empty or null titles
UPDATE tasks SET status = 'archived' WHERE title IS NULL OR trim(title) = '';

-- 2. Archive open tasks with null created_by
UPDATE tasks SET status = 'archived' WHERE created_by IS NULL AND status = 'open';

-- 3. Deduplicate open tasks: keep newest per (lower(title), assigned_to) group, archive the rest
WITH ranked AS (
  SELECT id, ROW_NUMBER() OVER (
    PARTITION BY lower(title), assigned_to
    ORDER BY created_at DESC
  ) AS rn
  FROM tasks
  WHERE status = 'open'
)
UPDATE tasks SET status = 'archived'
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
