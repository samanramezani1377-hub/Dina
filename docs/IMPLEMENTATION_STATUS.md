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

## گام بعد
ثبت دائمی سند، token authentication و اتصال PostgreSQL.

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.
