-- Migration 008: add is_admin flag to family_members
ALTER TABLE family_members ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false;

-- Set shgev as admin (by ADMIN_PHONE env or by name)
UPDATE family_members SET is_admin = true WHERE phone = current_setting('app.admin_phone', true);
