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
- قرارداد خطای یکپارچه: همه خطاها (اعتبارسنجی، قواعد دامنه، احراز هویت، عضویت، مجوز و خطای پیش‌بینی‌نشده) در یک پاکت `{"error": {"code", "message", "details"}}` برگردانده می‌شوند؛ کدها و وضعیت HTTP هر کد در `backend/src/errors.py` ثبت و در `docs/ERROR_CODES.md` مستند است. خطاهای داخلی فقط پیام عمومی و `correlation_id` می‌دهند و traceback فقط در لاگ ثبت می‌شود.
- ثبت‌نام، ورود و `GET /api/v1/auth/me` با توکن دست‌نویس‌شده HMAC (`backend/src/auth.py`، `backend/src/auth_api.py`) و خطاهای `email_already_registered`، `invalid_credentials`، `token_expired` و `token_invalid`. کاربران و عضویت‌ها هنوز در حافظه‌ی فرایند هستند.

## گام بعد
ثبت دائمی سند، جایگزینی user directory درون‌حافظه‌ای با repository مبتنی بر PostgreSQL، و اتصال PostgreSQL.

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.
