# راهنمای انتشار دینا

## قبل از انتشار
- آخرین CI روی `main` باید سبز باشد.
- `DATABASE_URL` محیط production بررسی شود.
- Backup خارج از سرور اصلی فعال و restore drill انجام شده باشد.
- `PAYMENT_WEBHOOK_SECRET` و credential درگاه در Secret Store باشند.
- برای Android، چهار secret امضای release تنظیم شوند.
- برای E2E، `E2E_TOKEN` و URL سرویس مستقر تنظیم شوند.

## Backup
Workflow زمان‌بندی‌شده `PostgreSQL backup` فایل dump را می‌سازد و با `pg_restore --list` صحت ساختاری آن را بررسی می‌کند. نگهداری خارج از runner باید توسط storage امن سازمان انجام شود؛ GitHub Actions محل نگهداری دائمی backup نیست.

## مالیات
دینا مدل صورتحساب مالیاتی، outbox/idempotency و وضعیت ارسال را دارد. اتصال نهایی به سامانه مؤدیان باید با مشخصات فنی معتبر و credential واقعی محیط production انجام شود؛ کد نباید credential را در repository نگه دارد. الزامات صورتحساب الکترونیکی توسط سازمان امور مالیاتی تعیین و به‌روزرسانی می‌شوند. citeturn0search12turn0search2

## Release
- tag با الگوی `vX.Y.Z` منتشر شود.
- workflow امضای Android فقط با secretهای واقعی اجرا می‌شود.
- Windows فعلاً به‌صورت ZIP قابل انتشار است؛ signing certificate در صورت عرضه رسمی باید به workflow اضافه شود.
