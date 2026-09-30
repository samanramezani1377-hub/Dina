# وضعیت پیاده‌سازی دینا

- Flutter پایه Android/Windows
- FastAPI با `/api/v1`
- Organization و Membership/Role
- password hashing/verification پایه
- tenant-scoped membership check
- Double-entry validation و API آن
- PostgreSQL schema پایه حسابداری
- تست API، امنیت، tenant isolation و تراز بدهکار/بستانکار
- CI واقعی Backend و Flutter
- Audit log: جدول append-only، سرویس `backend/src/audit.py` با redaction، tenant-scoped query

## گام بعد
ثبت دائمی سند، token authentication و اتصال PostgreSQL.

## Audit log

سرویس `backend/src/audit.py` و جدول `audit_logs` (migration `002_audit_logs.sql`) اضافه شده‌اند.

- جدول append-only است: `UPDATE` و `DELETE` برای رول application در سطح DB لغو شده و trigger هر دو را رد می‌کند. در اپلیکیشن هیچ مسیر update/delete وجود ندارد.
- `record(...)` هرگز exception پرتاب نمی‌کند؛ خطای نوشتن audit فقط log می‌شود و عملیات اصلی شکست نمی‌خورد.
- لایه redaction: کلیدهای حساس (password، hash، token، authorization و ...) و مقادیر با شکل secret (JWT، argon2، hex طولانی، `key=value`) پیش از ذخیره با `[REDACTED]` جایگزین می‌شوند. یک pass نهایی روی متن serialize‌شده به‌عنوان backstop وجود دارد؛ اگر چیزی از آن رد شود کل metadata دور ریخته می‌شود.
- `query_for_organization(store, organization_id, caller_organization_id, role=...)` فقط به `owner` و `manager` اجازه خواندن می‌دهد. `organization_id` از context مجوز می‌آید، نه از ورودی کاربر. پارامتر `caller_organization_id` الزامی است و باید با `organization_id` هم‌خوانی داشته باشد؛ در غیر این صورت `AuditError` پرتاب می‌شود — یک cross-tenant read بنابراین impossible است، نه تنها empty.

### وضعیت wiring

| عملیات | وضعیت |
| --- | --- |
| login موفق / ناموفق | helper آماده (`record_login_succeeded` / `record_login_failed`)، call site وجود ندارد — با JWT auth باید وصل شود |
| logout | helper آماده، call site وجود ندارد |
| ساخت organization | helper آماده، call site وجود ندارد |
| افزودن/حذف membership | helper آماده، call site وجود ندارد |
| ساخت account | helper آماده، call site وجود ندارد |
| journal | helper آماده؛ `POST /api/v1/accounting/journals/validate` به `journal.created` با `outcome` و `reason_code` وصل شده است. `organization_id` در audit row به صورت `None` ثبت می‌شود و `claimed_organization_id` در metadata ذخیره می‌شود (چون endpoint هنوز authentication ندارد). |
| posting، reversal، correction | helper آماده، endpoint هنوز وجود ندارد |
| payment | helper آماده، endpoint هنوز وجود ندارد |
| subscription | helper آماده، endpoint هنوز وجود ندارد |

### Gap‌های شناخته‌شده

- **PostgresAuditStore هنوز wire نشده است**. در حال حاضر `DEFAULT_STORE` یک `InMemoryAuditStore` با سقف ۱۰٬۰۰۰ ردیف است که dev-only و non-durable است (در restart از بین می‌رود). برای production باید `set_default_store(PostgresAuditStore(...))` با connection pool واقعی صدا زده شود، پس از اینکه `DATABASE_URL` و لایه persistence (bead `d7c3ddf6`) در دسترس باشد.
- `POST /api/v1/accounting/journals/validate` authentication ندارد؛ `organization_id` در audit trail قابل اعتماد نیست و تحت `claimed_organization_id` ثبت می‌شود. وقتی JWT/RBAC بیاید، org از membership dependency حل شود.

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.