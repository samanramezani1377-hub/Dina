# Legacy invoice accounting

New invoices created through `POST /api/v1/organizations/{organization_id}/invoices`
must include `receivable_account_id` and `revenue_account_id`. The backend
validates both accounts belong to the organization and have the expected account
types, then writes the invoice and its balanced posted journal entry in one
PostgreSQL transaction.

## Recovering older invoices

Migration 023 adds `receivable_account_id`, `revenue_account_id` and
`journal_entry_id` to legacy invoices. Existing rows are intentionally not
auto-mapped to accounts because guessing chart-of-accounts mappings can corrupt
financial reports.

For an unpaid historical invoice that has no journal entry:

1. Open the invoice in Dina and note its ID.
2. Choose the correct receivable asset account and revenue account for that
   invoice's business context.
3. Use the invoice page's **ثبت سند برای فاکتور قدیمی** action. This calls
   `POST /api/v1/organizations/{organization_id}/invoices/{invoice_id}/post`.
4. The server checks tenant ownership, account types, the open fiscal year and
   document-number uniqueness, then creates a balanced journal and attaches it
   to the invoice atomically. Repeating the same request with the same accounts
   is idempotent.

An old invoice with a non-zero paid balance but no ledger entry is not
automatically repaired. Its historic payments may have been recorded without
cash-account/journal references; posting the full invoice now would overstate
receivables. Those invoices require a manual reconciliation that maps each
historical payment to its cash account and ledger entry.

## Payment requirements

Invoice payments require:

- an `Idempotency-Key` header (maximum 200 characters);
- a cash/bank account linked to an asset account in the same organization;
- the same receivable account used by the invoice.

The payment row, balanced cash/receivable journal, cash transaction and invoice
paid balance are committed in one transaction. Reusing an idempotency key with
different invoice, amount, method, reference or account details is rejected.
