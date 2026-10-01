# وضعیت پیاده‌سازی دینا

این سند آن چیزی را توصیف می‌کند که **واقعاً** در کد هست. هر چیزی که هنوز ساخته نشده در بخش
[کجاها هنوز ناقص است](#کجاها-هنوز-ناقص-است) فهرست شده، نه اینکه حذف شود.

## چه چیزی وجود دارد

### احراز هویت (واقعی، نه نمایشی)

- Argon2id با `argon2-cffi`؛ hash به شکل PHC string ذخیره می‌شود و مسیر `needs_rehash` برای
  ارتقای hashهای قدیمی وجود دارد.
- توکن **دست‌نویس‌شده** است، نه encode شده: HMAC-SHA256 با `hmac.compare_digest` مقایسه می‌شود
  (`backend/src/auth.py`). الگوریتم از تنظیمات خوانده می‌شود، نه از هدر توکن، پس `alg: none`
  یا تبدیل کلید متقارن به کلید عمومی ممکن نیست.
- `token_expired` و `token_invalid` کدهای جدا هستند چون دو دستور متفاوت‌اند: یکی «توکن مال تو نیست،
  دور بریز»، دیگری «مال تو بود، تازه بگیر». توکن منقضی هم اول از نظر امضا بررسی می‌شود.
- endpointها: `POST /api/v1/auth/register`، `POST /api/v1/auth/login`، `GET /api/v1/auth/me`.

### سازمان، نقش و جداسازی tenant

- `InMemoryStore` نگاشت `user -> organization -> role` را نگه می‌دارد.
- `require_accounting_caller` در `backend/src/ledger_api.py` احراز هویت، عضویت و نقش را برای هر دو
  گزارش بررسی می‌کند: ۴۰۱ بدون توکن، ۴۰۴ وقتی سازمان وجود ندارد، ۴۰۳ وقتی نقش کافی نیست یا عضو نیست.
- `organization_id` **پارامتر مسیر** است و FastAPI آن را پیش از اجرای dependency مقداردهی می‌کند،
  پس بررسی عضویت به همان سازمانی گره می‌خورد که واقعاً درخواست شده — نه به چیزی از بدنه یا query.

### حسابداری

- چرخه‌ی بدهکار/بستانکار و اعتبارسنجی: `journal_empty`، `amount_must_be_non_negative`،
  `line_must_have_exactly_one_side`، `journal_not_balanced`. ترتیب بررسی‌ها بخشی از قرارداد است.
- `AccountingStore`: سازمان، حساب، سند (draft/posted/reversed)، ویرایش draft و حذف draft.
- گزارش‌ها: `GET /api/v1/organizations/{organization_id}/ledger` (با موجودی در حال اجرا به ازای هر حساب)
  و `GET /api/v1/organizations/{organization_id}/trial-balance` (با پارامتر اختیاری `as_of`، فقط
  اسناد posted/reversed).
- **تراز نامتوازن پنهان نمی‌شود.** اگر جمع بدهکار و بستانکار برابر نباشد، ارقام واقعی به‌همراه
  `is_balanced: false`، کد `trial_balance_unbalanced` و اختلاف دقیق برگردانده می‌شود. هیچ‌وقت
  خودکار اصلاح نمی‌شود.
- مبالغ `Decimal`/`NUMERIC` هستند، نه float.

### قرارداد خطا

همه خطاها — اعتبارسنجی، قواعد دامنه، احراز هویت، عضویت، مجوز و خطای پیش‌بینی‌نشده — در یک پاکت
`{"error": {"code", "message", "details"}}` برمی‌گردند. کدها و وضعیت HTTP در `backend/src/errors.py`
ثبت و در `docs/ERROR_CODES.md` مستند شده‌اند؛ تست `backend/tests/test_errors.py` یکی‌بودن جدول مستند
با رجیستری کد را بررسی می‌کند. خطای داخلی فقط پیام عمومی و `correlation_id` می‌دهد و traceback فقط
در لاگ ثبت می‌شود.

### Audit log

جدول `audit_logs` (migration `002_audit_logs.sql`) و سرویس `backend/src/audit.py`:

- **در سطح دیتابیس append-only است:** `UPDATE` و `DELETE` برای رول application لغو شده و یک trigger
  هر دو را حتی برای owner جدول رد می‌کند. در اپلیکیشن هم هیچ مسیر update/delete وجود ندارد.
  چون تضمین در کد اپلیکیشن نیست، تست آن هم در کد اپلیکیشن نیست: `backend/tests/test_audit_postgres.py`
  این را روی یک PostgreSQL واقعی بررسی می‌کند (`test_the_database_rejects_an_update`).
- `record(...)` هرگز exception پرتاب نمی‌کند؛ خطای نوشتن فقط log می‌شود و عملیات اصلی شکست نمی‌خورد.
- لایه redaction: کلیدهای حساس و مقادیر با شکل secret (JWT، argon2، hex طولانی، `key=value`) پیش از
  ذخیره `[REDACTED]` می‌شوند، به‌علاوه یک pass نهایی روی متن serialize‌شده به‌عنوان backstop.
- سقف metadata **پیش از** serialize شدن اعمال می‌شود تا payload همچنان parse‌شدنی بماند؛ بریدن JSONِ
  serialize‌شده آن را غیرقابل‌بازگردانی می‌کرد.
- `query_for_organization` فقط به `owner` و `manager` اجازه خواندن می‌دهد و `caller_organization_id`
  پارامتر اجباری است، پس یک cross-tenant read **impossible** است نه فقط empty: ردیف‌ها اصلاً fetch
  نمی‌شوند.

### CI

- سه job: backend (تست‌ها روی PostgreSQL واقعی)، Flutter lint/test/APK (لینوکس) و Flutter Windows build
  (روی runner ویندوزی، چون فقط آنجا ساخته می‌شود).
- هر build آرتیفکت تولیدشده را بررسی می‌کند؛ یک step که «موفق» شود ولی فایلی نسازد نباید سبز گزارش شود.
- فرمان‌های دقیق backend: `pip install -r backend/requirements.txt`، سپس اعمال
  `database/migrations/*.sql` به ترتیب نام فایل با `psql -v ON_ERROR_STOP=1`، سپس بررسی وجود جدول
  `audit_logs`، و در نهایت `pytest -q backend/tests`.

## کجاها هنوز ناقص است

این مهم‌ترین بخش سند است.

### ۱. هیچ چیز به‌جز audit به دیتابیس وصل نیست

**تمام state اپلیکیشن در حافظه‌ی فرایند است.** `app.state.memberships`، `app.state.accounting_store`
و `app.state.users` در `lifespan` به‌صورت `InMemoryStore({}, [])`، `AccountingStore()` و
`UserDirectory()` ساخته می‌شوند. با هر restart همه‌چیز از بین می‌رود و دو worker یکدیگر را نمی‌بینند.

`DATABASE_URL` در تنظیمات وجود دارد و در `.env.example` مستند شده، اما **هیچ کدی آن را نمی‌خواند** —
هیچ `psycopg.connect`ای در `src/` وجود ندارد و `set_default_store` هرگز صدا زده نمی‌شود. پس:

| کامپوننت | وضعیت |
| --- | --- |
| schema حسابداری | migration `001_accounting_core.sql` نوشته شده |
| جدول audit | migration `002_audit_logs.sql` نوشته و روی PostgreSQL واقعی تست شده |
| `PostgresAuditStore` | پیاده‌سازی و تست شده، ولی **در هیچ جا instantiate نشده** |
| `DEFAULT_STORE` | یک `InMemoryAuditStore` — dev-only، سقف ۱۰٬۰۰۰ ردیف، ازبین‌رفتنی با restart |
| کاربران، عضویت‌ها، حساب‌ها، اسناد | فقط در حافظه |

migrationها روی CI اجرا می‌شوند تا جدول `audit_logs` واقعاً ساخته و آزمایش شود، ولی اپلیکیشن در
runtime از آن‌ها استفاده نمی‌کند.

### ۲. `POST /api/v1/accounting/journals/validate` هنوز احراز هویت ندارد

تنها endpoint حسابداری بدون token است. عمداً tenant خودش را چک نمی‌کند چون هیچ read یا write
tenant-scoped انجام نمی‌دهد، پس نمی‌تواند داده‌ی سازمان دیگری را لو بدهد؛ و هر read در این سرویس از
طریق routerهای احراز هویت‌شده انجام می‌شود.

اما همین باعث می‌شود `organization_id` در بدنه یک **ادعا** باشد نه مجوز. به همین دلیل row ممیزی با
`organization_id = NULL` ثبت می‌شود و شناسه‌ی ادعاشده فقط زیر کلید `claimed_organization_id`
(که کلید tenant نیست) در metadata می‌آید. یک caller ناشناس **نمی‌تواند** row جعلی داخل trail یک
tenant دیگر بیندازد؛ این را `test_anonymous_caller_cannot_forge_an_audit_row_into_a_tenant`
پین می‌کند.

وقتی این endpoint پشت احراز هویت برود، سازمان باید از membership خوانده و فیلد بدنه نادیده گرفته شود.

### ۳. call siteهای audit ناقص‌اند

فقط journal به audit وصل است. برای بقیه helper وجود دارد ولی endpoint وجود ندارد:

| عملیات | وضعیت |
| --- | --- |
| journal | **وصل است** — `POST /api/v1/accounting/journals/validate` با `outcome` و `reason_code` |
| login موفق / ناموفق | helper آماده، call site وجود ندارد — باید به `auth_api` وصل شود |
| logout | helper آماده، call site وجود ندارد |
| ساخت organization | helper آماده، call site وجود ندارد |
| افزودن/حذف membership | helper آماده، call site وجود ندارد |
| ساخت account | helper آماده، call site وجود ندارد |
| posting، reversal، correction | helper آماده، endpoint وجود ندارد |
| payment | helper آماده، endpoint وجود ندارد |
| subscription | helper آماده، endpoint وجود ندارد |

### ۴. endpointهای موجود (فهرست کامل)

```
GET  /health
POST /api/v1/auth/register
POST /api/v1/auth/login
GET  /api/v1/auth/me
GET  /api/v1/organizations/{organization_id}/ledger
GET  /api/v1/organizations/{organization_id}/trial-balance
POST /api/v1/accounting/journals/validate
```

هیچ endpoint ثبت (post)، برگشت (reversal)، اصلاح (correction)، دریافت/پرداخت، صورتحساب مشتری یا
subscription وجود ندارد. اسناد فقط از طریق کد و در حافظه ساخته می‌شوند، نه از طریق API.

### ۵. تست‌های PostgreSQL فقط روی CI اجرا شده‌اند

`backend/tests/test_audit_postgres.py` روی یک سرویس `postgres:16` اجرا می‌شود. روی CI اگر
`DATABASE_URL` نباشد **fail** می‌شود نه skip، چون یک skip یعنی «پوشش داده شد» در حالی که چیزی اجرا
نشده. خارج از CI با یک skip صریح رد می‌شود تا `pytest backend/tests` روی لپ‌تاپ بدون سرور کار کند.

## اصول

Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با
reversal/correction انجام می‌شود؛ عملیات مالی tenant-scoped است؛ و هیچ endpoint حسابداری نباید
بدون تعیین تکلیف احراز هویت وارد production شود.
