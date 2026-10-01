# Migrationها

Migrationهای PostgreSQL اینجا قرار می‌گیرند. همه تغییرات schema باید قابل اجرای ترتیبی و قابل بررسی باشند.

- `001_accounting_core.sql` — سازمان‌ها، حساب‌ها، اسناد و خطوط سند.
- `002_audit_logs.sql` — جدول `audit_logs`. این جدول فقط append است؛ `UPDATE` و `DELETE` برای رول `dina_app` لغو می‌شود و trigger `trg_audit_logs_append_only` هر تغییر یا حذف را رد می‌کند. اگر نام رول application در استقرار شما چیز دیگری است، بخش `REVOKE` migration را با همان نام به‌روزرسانی کنید.
