-- Complete the journal reversal relation used by the persistent repository.
ALTER TABLE journal_entries
    ADD COLUMN IF NOT EXISTS reversal_of_entry_id BIGINT REFERENCES journal_entries(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS idx_journal_entries_reversal
    ON journal_entries(reversal_of_entry_id);
