-- Canonicalize the inventory role to the API's warehouse role.
-- The old constraint admitted 'inventory' but application authorization uses
-- 'warehouse'; keep existing members valid while removing the split vocabulary.
ALTER TABLE memberships DROP CONSTRAINT IF EXISTS memberships_role_check;

UPDATE memberships
SET role = 'warehouse'
WHERE role = 'inventory';

ALTER TABLE memberships
    ADD CONSTRAINT memberships_role_check
    CHECK (role IN ('owner', 'manager', 'accountant', 'sales', 'warehouse', 'viewer'));
