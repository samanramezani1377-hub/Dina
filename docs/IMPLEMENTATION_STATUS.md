# وضعیت پیاده‌سازی دینا

این فایل وضعیت واقعی شاخه main را ثبت می‌کند. دینا از prototype عبور کرده و هسته حسابداری، persistence، عملیات فروش/خرید، انبار، خزانه، گزارش‌ها و سخت‌سازی API روی main قرار دارد.

## تکمیل‌شده

### زیرساخت و persistence
- PostgreSQL در production مرجع اصلی داده است و InMemoryStore فقط برای test است.
- کاربران، سازمان‌ها، عضویت‌ها، حساب‌ها، اسناد و داده‌های عملیاتی روی PostgreSQL ذخیره می‌شوند.
- migrationها به ترتیب شماره اجرا می‌شوند.
- tenant isolation و RBAC در Backend enforce می‌شوند.
- audit trail و مرکز خطا به persistence متصل‌اند.
- journalها از نظر بدهکار/بستانکار validate می‌شوند و posted/reversed قابل حذف یا ویرایش مخرب نیستند.

### هسته حسابداری
- Chart of Accounts
- Journal draft/post
- Reversal/Correction
- Ledger
- Trial Balance
- Profit & Loss
- Balance Sheet
- Account Statement
- Decimal/NUMERIC برای مقادیر مالی
- کنترل سال مالی و جلوگیری از overlap

### عملیات
- مشتریان و تأمین‌کنندگان
- کالا/خدمات
- انبار و گردش موجودی
- انتقال اتمیک بین انبارها
- فروش و خرید
- Posting فروش/خرید به دفتر روزنامه
- COGS و inventory accounting برای کالاهای tracked
- صندوق و بانک
- دریافت/پرداخت و اتصال به حساب‌های دفتر کل
- چک‌ها و state machine
- گزارش موجودی، فروش و خرید
- مدیریت و مرکز خطا

### SaaS و پرداخت
- subscription lifecycle پایه
- payment attempt با Idempotency-Key
- webhook با secret و state transition معتبر
- payment webhook/event deduplication
- مرز مستقل PaymentProvider برای اتصال درگاه واقعی
- عدم نگهداری secret در repository
- rate limiting احراز هویت در PostgreSQL برای deployment چندپردازه
- readiness probe وابسته به PostgreSQL

### خروجی
- CSV با UTF-8 BOM برای تراز آزمایشی، دفتر کل، فروش، خرید و موجودی
- همه خروجی‌های مالی tenant-scoped و RBAC-protected هستند.

### کلاینت
- Android و Windows
- navigation واکنش‌گرا
- navigation گسترده و overflow قابل اسکرول
- صفحات عملیاتی اصلی و گزارش‌ها
- تست Flutter برای navigation

### CI
CI واقعی شامل:
- PostgreSQL 16 واقعی + migration + تمام backend/tests
- Flutter analyze
- Flutter tests
- Android release APK و بررسی وجود artifact
- Windows release build و بررسی وجود binary

## موارد باقی‌مانده برای انتشار نهایی

این‌ها دیگر «هسته حسابداری» نیستند و برای production واقعی باید قبل از عرضه عمومی انجام شوند:

1. اتصال یک درگاه پرداخت واقعی و پیاده‌سازی signature verification مخصوص همان provider.
2. Rate limiting توزیع‌شده برای auth و endpointهای حساس؛ برای deployment چندپردازه Redis یا gateway مناسب‌تر از limiter درون‌پردازه‌ای است.
3. Backup خارج از سرور اصلی، retention policy و restore drill دوره‌ای روی محیط staging.
4. E2E واقعی Android/Windows در برابر Backend deployed.
5. monitoring/metrics/alerting و health check وابسته به PostgreSQL.
6. تولید PDF/Excel رسمی با قالب‌های قابل چاپ در صورت نیاز کسب‌وکار.
7. انتشار signed Android artifact و Windows installer/signing.
8. تکمیل shortcutهای عملیاتی UI مطابق ماتریس میانبرهای پروژه و اتصال هر میانبر به action واقعی صفحه مربوطه.
9. تست concurrency و performance با حجم داده واقعی.
10. الزامات مالیاتی/قوانین محلی و شماره‌گذاری نهایی اسناد، پس از مشخص‌شدن مقررات کسب‌وکار.

## اصل صداقت CI

سبز بودن CI فقط بعد از اجرای GitHub Actions روی آخرین commit قابل اعلام است. «پیاده‌سازی‌شده» و «تأییدشده با CI» دو وضعیت جدا هستند.
