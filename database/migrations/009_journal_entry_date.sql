-- Add the accounting document date required by period reports and fiscal-year boundaries.
ALTER TABLE journal_entries
    ADD COLUMN IF NOT EXISTS entry_date DATE NOT NULL DEFAULT CURRENT_DATE;
CREATE INDEX IF NOT EXISTS idx_journal_entries_org_date
    ON journal_entries(organization_id, entry_date);
