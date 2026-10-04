# وضعیت پیاده‌سازی دینا

## تکمیل‌شده روی main
- هسته حسابداری، PostgreSQL persistence، RBAC و tenant isolation.
- فروش، خرید، انبار، صندوق، بانک، دریافت/پرداخت و چک.
- گزارش‌های مالی و exportهای CSV.
- مدیریت سازمان، Platform Admin، subscription و payment attempts.
- ZarinPal adapter و callback امن.
- مرکز خطا و audit trail.
- CSV + Excel + PDF برای تراز آزمایشی، دفتر کل، فروش و خرید.
- migration 018 برای tax submission outbox، استهلاک و reconciliation.
- backup verification workflow، deployed smoke workflow و release artifact workflow.
- میانبرهای کلیدی ناوبری حسابداری در shell.
- CI واقعی Backend + PostgreSQL migrations + Flutter analyze/test + Android + Windows.

## موارد وابسته به محیط production
1. credential واقعی درگاه و اجرای تراکنش واقعی.
2. credential و مشخصات فنی معتبر سامانه مؤدیان/شرکت معتمد؛ قوانین و قالب‌های مالیاتی باید با نسخه معتبر روز تطبیق داده شوند. citeturn0search12turn0search2
3. مقصد واقعی backup خارج از GitHub runner و restore drill.
4. URL و token واقعی برای E2E deployed.
5. secretهای signing برای APK و certificate امضای Windows.
6. monitoring/alert destination واقعی (Prometheus/Grafana/Sentry یا سرویس سازمان).

این موارد «کد ناقص» نیستند؛ به credential، سرویس یا زیرساخت واقعی بیرون از repository وابسته‌اند.

## اصل صداقت CI
سبز بودن CI فقط بعد از اجرای GitHub Actions روی آخرین commit قابل اعلام است.
