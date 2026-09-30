# Dina Accounting Platform — Project Specification

## Product direction

Dina is an online-first accounting platform for Android and Windows. Both clients use the same central server-side data source over HTTPS. The server is authoritative; offline-first synchronization is out of scope for the initial architecture.

## Architecture

- Flutter/Dart clients for Android and Windows
- HTTPS REST API
- Backend service with server-side business rules
- PostgreSQL as the authoritative accounting database
- Central authentication and organization/membership model
- Role-based permissions
- Subscription, licensing and payment services separated from accounting data
- Automated backups, audit logging and monitoring

## Accounting foundation

Dina uses double-entry accounting. Every posted journal entry must satisfy `total_debits = total_credits`. Financial balances are derived from journal records rather than independently editable client values. Posted financial history should use reversal/correction workflows instead of destructive edits.

Core accounting concepts:

- Chart of accounts
- Fiscal years/periods
- Journal entries and journal lines
- Opening balances
- General ledger
- Trial balance
- Profit and loss
- Balance sheet
- Cash and bank accounts
- Receivables and payables

## Business modules

- Dashboard
- Customers
- Suppliers
- Products and services
- Sales invoices
- Purchases
- Payments
- Inventory and warehouses
- Cash and banks
- Checks
- Financial reports
- Audit history

## Multi-tenant model

A user belongs to one or more organizations/businesses through memberships. Accounting and business records are organization-scoped. Tenant isolation must be enforced server-side on every relevant read and write.

Suggested roles include Owner, Administrator, Accountant, Sales, Inventory and Read-only. Permissions must be enforced by the backend, not only by the clients.

## SaaS and payments

Dina may be delivered as SaaS while the project owns or operates the infrastructure. Suggested billing concepts:

- Plans
- Subscriptions
- Entitlements
- Licenses
- Billing periods
- Payments and payment attempts
- Provider verification/webhooks
- Expiration/grace-period rules

Payment confirmation must be idempotent so repeated callbacks cannot create duplicate payments or subscription periods. Expired subscriptions must be enforced by the backend; accounting data must not be deleted because of expiration.

## API rules

- Version the API, e.g. `/api/v1`
- Validate every request server-side
- Use stable machine-readable error codes
- Use database transactions for financial mutations
- Support pagination/filtering/sorting
- Enforce authorization server-side
- Use idempotency for retriable financial/payment operations
- Never expose internal exceptions or secrets in production responses

## Security

Required baseline controls:

- HTTPS only
- Secure password hashing
- Protected sessions/tokens
- Server-side authorization
- Tenant isolation
- Input validation
- Rate limiting for sensitive endpoints
- Secret management outside source control
- Audit logging
- Dependency/security updates
- Protected backups

## Data and money

Monetary values must use exact decimal/numeric storage, never floating-point persistence. Currency, precision, rounding, tax and discount rules must be explicit.

## Client architecture

The Flutter application should separate presentation, application/state, API/repository and domain-facing concerns. Clients display and collect data; the server owns accounting rules, authorization, subscription enforcement and final validation.

The Android and Windows clients should expose the same business capabilities, with platform-specific UX only where necessary for touch, keyboard/mouse, windows, printing or native integrations.

## Reliability and concurrency

The backend must support concurrent use from multiple devices through transactions, appropriate locking/concurrency controls, unique constraints, idempotency and safe document/number generation.

## Backup and recovery

- Automated PostgreSQL backups
- Retention policy
- Off-server backup where practical
- Backup integrity verification
- Documented restore process
- Periodic recovery testing

## Testing

CI and automated tests should cover:

- Backend/unit tests
- API integration tests
- Flutter formatting, analysis and tests
- Android build
- Windows build
- Database migrations
- Authentication and tenant isolation
- Accounting invariants
- Invoice/payment posting
- Payment idempotency
- Subscription lifecycle
- End-to-end business workflows

At minimum, every posted journal entry must be tested for balanced debit/credit totals.

## Proposed repository structure

```text
/
├── app/              # Flutter Android/Windows application
├── backend/          # API/backend
├── database/         # migrations/seeds/schema support
├── docs/             # specifications and architecture decisions
├── infra/            # deployment/infrastructure
└── tests/             # cross-system/E2E tests where appropriate
```

The exact structure can change after the existing repository is inspected.

## Roadmap

### Phase 0 — Foundation

- Repository structure
- Flutter foundation
- Backend foundation
- Database migrations
- CI
- Development/staging environments

### Phase 1 — Identity and tenancy

- Registration/login
- Organizations
- Memberships
- Roles and permissions
- Sessions

### Phase 2 — Accounting core

- Chart of accounts
- Fiscal periods
- Journal entries/lines
- Posting and reversal
- General ledger
- Trial balance

### Phase 3 — Flutter clients

- Shared design system
- Navigation
- Authentication
- API client
- State management
- Android/Windows layouts

### Phase 4 — Operations

- Customers/suppliers
- Products/services
- Sales/purchases
- Payments
- Basic inventory

### Phase 5 — Financial operations

- Banks/cash
- Checks
- Reconciliation
- Receivables/payables
- Advanced reports

### Phase 6 — SaaS

- Plans
- Subscriptions
- Licensing
- Payment gateway abstraction
- Verification/webhooks
- Entitlement enforcement

### Phase 7 — Hardening and release

- Security review
- Backup/restore test
- Performance/concurrency testing
- E2E tests
- Monitoring
- Android/Windows release pipelines

## Architectural decisions

| Decision | Direction |
|---|---|
| Client platforms | Android + Windows |
| Client framework | Flutter |
| Primary data location | Central server |
| Connectivity | Online required |
| Offline-first | No |
| Database | PostgreSQL |
| API | HTTPS REST |
| Accounting model | Double-entry |
| Server authority | Yes |
| Multi-device shared data | Yes |
| Multi-user support | Yes |
| SaaS subscriptions | Yes |
| Payment abstraction | Yes |
| Backups | Required |
| Audit trail | Required |

## Decisions to finalize during implementation

- Exact backend framework
- Hosting/VPS architecture
- Production PostgreSQL topology
- Payment provider(s)
- SMS/email providers
- Subscription plans and limits
- Regulatory/tax requirements
- Invoice numbering and fiscal-year rules
- Inventory valuation method
- Printing/PDF requirements
- Localization details

## Engineering rules

1. Never make the client authoritative for accounting calculations.
2. Never persist monetary values as floating point.
3. Use transactions for financial mutations.
4. Enforce authorization on the server.
5. Keep payment providers behind an abstraction.
6. Preserve posted financial history through reversal/correction workflows.
7. Do not introduce offline synchronization without an explicit architecture decision.
8. Test the accounting effect of every financial workflow.
9. Enforce organization isolation on every tenant-scoped query.
10. Never commit production secrets.
11. Document changes to the accounting model.
12. Keep CI as a real validation gate.