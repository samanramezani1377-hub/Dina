# تست دینا با GitHub Codespaces

این محیط برای تست واقعی اپ اندروید با Backend و PostgreSQL خود دینا ساخته شده است.

## ساخت Codespace

در GitHub وارد ریپو شوید و از مسیر Code سپس Codespaces یک Codespace روی main بسازید.

پس از ساخته‌شدن Codespace، پیکربندی dev container به‌صورت خودکار PostgreSQL و Backend را آماده می‌کند.

## پیدا کردن Backend

در پنل Ports پورت 8000 را پیدا کنید. برای اتصال گوشی، در صورت نیاز آن را Public کنید.

نشانی چیزی شبیه این خواهد بود:
https://<codespace>-8000.app.github.dev

همین نشانی مقدار API_BASE_URL است و نباید api/v1 به آن اضافه شود؛ اپ خودش آن مسیر را اضافه می‌کند.

## بررسی Backend

این نشانی را باز کنید:
<API_BASE_URL>/health/ready

باید پاسخ موفقیت‌آمیز سرویس و PostgreSQL را ببینید.

## ساخت APK تستی

در ریپو به Actions و سپس Deployed E2E smoke بروید و Run workflow را بزنید.

در base_url همان نشانی Backend را وارد کنید.

Workflow:
- health/live و health/ready را بررسی می‌کند.
- APK اندروید را با API_BASE_URL همان Codespace می‌سازد.
- APK را به عنوان Artifact در اجرای Workflow قرار می‌دهد.

بعد از موفقیت، APK را از Artifacts دانلود و روی گوشی نصب کنید.

## تست داخل اپ

ثبت‌نام، ورود، انتخاب یا ایجاد سازمان و سپس ماژول‌های حسابداری و عملیاتی موجود را تست کنید.

## نکته

Codespace محیط تست است، نه سرور تولیدی. داده‌های واقعی مشتری را داخل آن قرار ندهید.
URL پورت Codespaces ممکن است با توقف و شروع دوباره تغییر کند؛ بنابراین URL را در کد هاردکد نکنید.
