# وضعیت پیاده‌سازی دینا

- Flutter پایه Android/Windows
- FastAPI با `/api/v1`
- Organization و Membership/Role
- password hashing/verification با Argon2id (`argon2-cffi`) و ذخیره به صورت PHC string، به‌همراه مسیر `needs_rehash` برای ارتقای hashهای قدیمی
- تنظیمات برنامه از environment (`backend/src/config.py`)؛ در محیط غیر تست، نبودن یا خالی بودن `SECRET_KEY` مانع راه‌اندازی سرویس می‌شود و هیچ secret پیش‌فرضی در کد وجود ندارد (`.env.example` فقط placeholder دارد)
- tenant-scoped membership check
- Double-entry validation و API آن
- PostgreSQL schema پایه حسابداری
- تست API، امنیت، tenant isolation و تراز بدهکار/بستانکار
- گزارش تراز بدهکار/بستانکار (`GET /api/v1/organizations/{organization_id}/trial-balance`) با پارامتر اختیاری `as_of`، فقط بر اساس اسناد posted/reversed؛ اگر جمع بدهکار و بستانکار برابر نباشد، ارقام واقعی به‌همراه `is_balanced: false`، کد خطای `trial_balance_unbalanced` و اختلاف دقیق برگردانده می‌شود و در لاگ و audit ثبت می‌گردد؛ اختلاف هرگز خودکار اصلاح نمی‌شود.
- CI واقعی Backend و Flutter
<<<<<<< HEAD
- قرارداد خطای یکپارچه: همه خطاها (اعتبارسنجی، قواعد دامنه، احراز هویت، عضویت، مجوز و خطای پیش‌بینی‌نشده) در یک پاکت `{"error": {"code", "message", "details"}}` برگردانده می‌شوند؛ کدها و وضعیت HTTP هر کد در `backend/src/errors.py` ثبت و در `docs/ERROR_CODES.md` مستند است. خطاهای داخلی فقط پیام عمومی و `correlation_id` می‌دهند و traceback فقط در لاگ ثبت می‌شود.
- ثبت‌نام، ورود و `GET /api/v1/auth/me` با توکن دست‌نویس‌شده HMAC (`backend/src/auth.py`، `backend/src/auth_api.py`) و خطاهای `email_already_registered`، `invalid_credentials`، `token_expired` و `token_invalid`. کاربران و عضویت‌ها هنوز در حافظه‌ی فرایند هستند.
=======
- Audit log: جدول append-only، سرویس `backend/src/audit.py` با redaction، tenant-scoped query
>>>>>>> origin/main

## گام بعد
ثبت دائمی سند، جایگزینی user directory درون‌حافظه‌ای با repository مبتنی بر PostgreSQL، و اتصال PostgreSQL.

## Audit log

سرویس `backend/src/audit.py` و جدول `audit_logs` (migration `002_audit_logs.sql`) اضافه شده‌اند.

- جدول append-only است: `UPDATE` و `DELETE` برای رول application در سطح DB لغو شده و trigger هر دو را رد می‌کند. در اپلیکیشن هیچ مسیر update/delete وجود ندارد.
- `record(...)` هرگز exception پرتاب نمی‌کند؛ خطای نوشتن audit فقط log می‌شود و عملیات اصلی شکست نمی‌خورد.
- لایه redaction: کلیدهای حساس (password، hash، token، authorization و ...) و مقادیر با شکل secret (JWT، argon2، hex طولانی، `key=value`) پیش از ذخیره با `[REDACTED]` جایگزین می‌شوند. یک pass نهایی روی متن serialize‌شده به‌عنوان backstop وجود دارد؛ اگر چیزی از آن رد شود کل metadata دور ریخته می‌شود.
- `query_for_organization(store, organization_id, caller_organization_id, role=...)` فقط به `owner` و `manager` اجازه خواندن می‌دهد. `organization_id` از context مجوز می‌آید، نه از ورودی کاربر. پارامتر `caller_organization_id` الزامی است و باید با `organization_id` هم‌خوانی داشته باشد؛ در غیر این صورت `AuditError` پرتاب می‌شود — یک cross-tenant read بنابراین impossible است، نه تنها empty. نقش به‌تنهایی هیچ چیزی را به `organization_id` وصل نمی‌کند.
- سقف metadata **پیش از** serialize شدن اعمال می‌شود، نه روی متن serialize‌شده: هر مقدار رشته‌ای به `MAX_METADATA_STRING_CHARS` محدود و در صورت نیاز کلیدها از انتها حذف می‌شوند تا مجموع از `MAX_METADATA_CHARS` بگذرد تا payload همچنان parse‌شدنی بماند (`metadata_truncated: true`). بریدنِ JSONِ serialize‌شده payload را غیرقابل‌بازگردانی می‌کرد.

### کجاها هنوز ناقص است

- **Store پیش‌فرض durable نیست.** `DEFAULT_STORE` یک `InMemoryAuditStore` است: dev-only، با سقف `DEFAULT_STORE_MAX_ROWS` (۱۰٬۰۰۰ ردیف) و از بین‌رفتنی با restart. سقف ردیف‌های موجود را حذف نمی‌کند (حذف، مسیر delete است)؛ پس از رسیدن به سقف append بعدی خطا می‌دهد و `record` آن را log می‌کند. `PostgresAuditStore` پیاده‌سازی و تست شده اما **هنوز در هیچ جایی instantiate نشده**؛ پس از در دسترس قرار گرفتن `DATABASE_URL` و لایه persistence (bead `d7c3ddf6`) باید `set_default_store(PostgresAuditStore(...))` صدا زده شود. تا آن زمان audit row‌ها بین restartها از بین می‌روند.
- **call site بدون احراز هویت.** `POST /api/v1/accounting/journals/validate` هنوز auth ندارد، پس tenant از بدنهٔ درخواست قابل اعتماد نیست. به همین دلیل row با `organization_id = NULL` ثبت می‌شود و شناسهٔ ادعاشده فقط با کلید `claimed_organization_id` در metadata می‌آید (کلید tenant نیست). پس از landing شدن JWT/RBAC باید از membership dependency خوانده شود.
- helperها `store`، `correlation_id`، `ip_address` و `metadata` را به‌صورت keyword-only صریح می‌گیرند؛ `**kwargs` حذف شده تا یک تایپ اشتباه به‌جای سکوت، `TypeError` بدهد.
- `InMemoryAuditStore.clear()` حذف شده است؛ fixtureها هر بار یک store تازه می‌سازند.

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

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.