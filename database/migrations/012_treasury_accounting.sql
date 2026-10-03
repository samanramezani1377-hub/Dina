-- Link treasury records to the accounting ledger.
ALTER TABLE cash_accounts ADD COLUMN IF NOT EXISTS account_id BIGINT REFERENCES accounts(id);
ALTER TABLE cash_transactions ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
ALTER TABLE payments ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);
CREATE INDEX IF NOT EXISTS idx_cash_accounts_org_account ON cash_accounts(organization_id, account_id);
CREATE INDEX IF NOT EXISTS idx_cash_tx_journal ON cash_transactions(journal_entry_id);
CREATE INDEX IF NOT EXISTS idx_payments_journal ON payments(journal_entry_id);
