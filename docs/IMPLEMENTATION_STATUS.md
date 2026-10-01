# وضعیت پیاده‌سازی دینا

این سند وضعیت واقعی شاخه main را ثبت می‌کند. مسیر اصلی از حالت prototype خارج شده و backend عملیاتی، persistence و APIهای اصلی روی آن قرار گرفته‌اند.

## تکمیل‌شده

### Persistence و tenant isolation
- محیط production از PostgreSQL استفاده می‌کند؛ InMemoryStore فقط برای test environment است.
- کاربران، عضویت‌ها، سازمان‌ها، حساب‌ها و اسناد در PostgreSQL ذخیره می‌شوند.
- entry_date در migration پایدار شده است.
- tenant predicate در خواندن حساب‌ها و اسناد اعمال می‌شود.
- PostgreSQL integration test برای ساخت/ذخیره/post/query و tenant isolation وجود دارد.
- Audit در production به PostgresAuditStore وصل است و migration آن append-only است.

### Authentication
- ثبت‌نام، ورود و /me با access token امضاشده HMAC کار می‌کنند.
- مسیرهای عملیاتی در production هویت را از Authorization: Bearer می‌گیرند.
- X-User-Id فقط در محیط test برای fixtureهای قدیمی پذیرفته می‌شود.
- Argon2id برای password و rehash هنگام login فعال است.

### Accounting API
- ساخت و فهرست حساب‌ها.
- ساخت، دریافت، ویرایش و حذف draft journal.
- post کردن journal.
- reversal برای سند posted.
- ledger و trial balance.
- مبالغ با Decimal/NUMERIC نگهداری می‌شوند.
- tenant و role در backend enforce می‌شوند.
- audit برای ساخت حساب، ساخت سند، posting، reversal و correction ثبت می‌شود.

### SaaS / عملیات
- سازمان و membership.
- مشتریان.
- فاکتورها.
- ثبت پرداخت و محاسبه وضعیت open/partial/paid.
- subscription با وضعیت‌های trial/active/past_due/cancelled/expired.
- migration 004_saas.sql برای این بخش اضافه شده است.
- پرداخت و تغییر subscription audit می‌شوند.

### APIهای اصلی
GET  /health
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/organizations
POST /api/v1/organizations/{organization_id}/members
DELETE /api/v1/organizations/{organization_id}/members/{member_user_id}
GET  /api/v1/organizations/{organization_id}/ledger
GET  /api/v1/organizations/{organization_id}/trial-balance
POST /api/v1/organizations/{organization_id}/accounts
GET  /api/v1/organizations/{organization_id}/accounts
POST /api/v1/organizations/{organization_id}/journals
GET  /api/v1/organizations/{organization_id}/journals/{entry_id}
PATCH /api/v1/organizations/{organization_id}/journals/{entry_id}
DELETE /api/v1/organizations/{organization_id}/journals/{entry_id}
POST /api/v1/organizations/{organization_id}/journals/{entry_id}/post
POST /api/v1/organizations/{organization_id}/journals/{entry_id}/reverse
POST /api/v1/organizations/{organization_id}/customers
GET  /api/v1/organizations/{organization_id}/customers
POST /api/v1/organizations/{organization_id}/invoices
GET  /api/v1/organizations/{organization_id}/invoices
POST /api/v1/organizations/{organization_id}/invoices/{invoice_id}/payments
PUT  /api/v1/organizations/{organization_id}/subscription
GET  /api/v1/organizations/{organization_id}/subscription

## تست و CI
CI سه بخش اصلی دارد:
- Backend + PostgreSQL واقعی + تمام backend/tests.
- Flutter lint/test/APK.
- Flutter Windows build.

Migrationها به ترتیب نام اجرا می‌شوند و build artifact نیز بعد از build واقعاً بررسی می‌شود.

## نکته نهایی
سبز بودن CI فقط بعد از اجرای GitHub Actions روی آخرین commit قابل اعلام است. بنابراین «کد تکمیل شده» و «CI سبز تأییدشده» دو وضعیت جدا هستند و دومی باید از run واقعی GitHub تأیید شود.
