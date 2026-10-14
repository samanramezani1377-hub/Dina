-- Make the legacy single-total invoice workflow accountable and traceable.
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS receivable_account_id BIGINT REFERENCES accounts(id),
    ADD COLUMN IF NOT EXISTS revenue_account_id BIGINT REFERENCES accounts(id),
    ADD COLUMN IF NOT EXISTS journal_entry_id BIGINT REFERENCES journal_entries(id);

CREATE INDEX IF NOT EXISTS idx_invoices_org_journal
    ON invoices(organization_id, journal_entry_id);

CREATE OR REPLACE FUNCTION dina_guard_invoice_account_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    customer_org BIGINT;
    receivable_org BIGINT;
    revenue_org BIGINT;
    journal_org BIGINT;
BEGIN
    SELECT organization_id INTO customer_org FROM customers WHERE id=NEW.customer_id;
    SELECT organization_id INTO receivable_org FROM accounts WHERE id=NEW.receivable_account_id;
    SELECT organization_id INTO revenue_org FROM accounts WHERE id=NEW.revenue_account_id;

    IF customer_org IS NULL OR receivable_org IS NULL OR revenue_org IS NULL THEN
        RAISE EXCEPTION 'invoice references a missing customer or account'
            USING ERRCODE = '23503';
    END IF;
    IF NEW.organization_id <> customer_org
       OR NEW.organization_id <> receivable_org
       OR NEW.organization_id <> revenue_org THEN
        RAISE EXCEPTION 'invoice, customer and ledger accounts must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.journal_entry_id IS NOT NULL THEN
        SELECT organization_id INTO journal_org
          FROM journal_entries WHERE id=NEW.journal_entry_id;
        IF journal_org IS NULL THEN
            RAISE EXCEPTION 'invoice references a missing journal entry'
                USING ERRCODE = '23503';
        END IF;
        IF journal_org <> NEW.organization_id THEN
            RAISE EXCEPTION 'invoice and journal entry must belong to the same organization'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_invoices_account_tenant_guard ON invoices;
CREATE TRIGGER trg_invoices_account_tenant_guard
BEFORE INSERT OR UPDATE OF organization_id, customer_id, receivable_account_id,
                           revenue_account_id, journal_entry_id
ON invoices
FOR EACH ROW EXECUTE FUNCTION dina_guard_invoice_account_tenant();
