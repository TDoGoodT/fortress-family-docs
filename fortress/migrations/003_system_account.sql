-- Fortress 2.0 System Account
-- Insert system account for automated operations

BEGIN;

INSERT INTO family_members (id, name, phone, role, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    'Fortress System',
    '0000000000',
    'other',
    true
)
ON CONFLICT (phone) DO NOTHING;

COMMIT;
