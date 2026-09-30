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
- CI واقعی Backend و Flutter

## گام بعد
ثبت دائمی سند، token authentication و اتصال PostgreSQL.

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.
