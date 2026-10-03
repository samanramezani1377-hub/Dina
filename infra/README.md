# زیرساخت عملیاتی دینا

فایل backup_postgres.sh با pg_dump و فرمت custom نسخه timestamped تولید می‌کند.
فایل restore_postgres.sh فقط با تایید صریح --confirm دیتابیس مقصد را restore می‌کند.

## Production
- DATABASE_URL و SECRET_KEY فقط از environment یا secret manager.
- PostgreSQL خارج از process API نگهداری شود.
- Backup روزانه با retention تعریف شود.
- restore به‌صورت دوره‌ای روی محیط جداگانه آزمایش شود.
- کلاینت بدون API واقعی build release نشود.
