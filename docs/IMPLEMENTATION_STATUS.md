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

## گام بعد
ثبت دائمی سند، token authentication و اتصال PostgreSQL.

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.
