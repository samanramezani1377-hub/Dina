# درگاه زرین‌پال

Dina درگاه پرداخت را پشت abstraction داخلی نگه می‌دارد و پیاده‌سازی فعلی آن **ZarinPal REST API v4** است.

## تنظیمات Production

مقادیر زیر فقط در Secret Manager یا محیط اجرای سرویس تنظیم شوند:

- `ZARINPAL_MERCHANT_ID`
- `ZARINPAL_CALLBACK_URL`
- `ZARINPAL_SANDBOX=false`
- `ZARINPAL_TIMEOUT_SECONDS=15`

آدرس callback باید HTTPS و عمومی باشد:

`https://<api-host>/api/v1/payments/zarinpal/callback`

برای هر پرداخت، Dina شناسه سازمان و شناسه تلاش پرداخت را به callback اضافه می‌کند. بنابراین callback بدون session کاربر هم می‌تواند پرداخت درست را پیدا کند، ولی مبلغ، ارز، سازمان و Authority را از دیتابیس خودش تطبیق می‌دهد.

## جریان پرداخت

1. کلاینت `POST /api/v1/organizations/{organization_id}/payments/attempts` را با `Idempotency-Key` صدا می‌زند و `provider=zarinpal` می‌فرستد.
2. Dina رکورد `payment_attempts` را ایجاد می‌کند.
3. Backend به `https://api.zarinpal.com/pg/v4/payment/request.json` درخواست می‌زند.
4. Authority در `provider_reference` ذخیره و وضعیت به `pending` تغییر می‌کند.
5. پاسخ شامل `payment_url` به `https://www.zarinpal.com/pg/StartPay/{Authority}` است.
6. پس از بازگشت کاربر با `Status=OK`، Backend مبلغ ذخیره‌شده را با `/pg/v4/payment/verify.json` اعتبارسنجی می‌کند.
7. کدهای موفق `100` و `101` هر دو موفق محسوب می‌شوند؛ `101` یعنی تراکنش قبلاً verify شده است.
8. سپس وضعیت تلاش پرداخت به `succeeded` می‌رسد و `ref_id` ذخیره می‌شود.
9. بازگشت چندباره به callback یا ارسال چندباره webhook نباید پرداخت را دوباره ثبت کند.

## واحد پول

ZarinPal در مرز gateway مبلغ را به Rial می‌فرستد:

- `IRR`: بدون تبدیل
- `IRT` / `TOMAN`: ضرب در ۱۰

واحد پول حسابداری Dina در دیتابیس تغییر نمی‌کند.

## Sandbox

برای تست، `ZARINPAL_SANDBOX=true` و endpointهای sandbox v4 فعال می‌شوند. قبل از انتشار، مقدار را `false` کنید.

نمونه رسمی ZarinPal از endpointهای REST v4 برای request و verify استفاده می‌کند. citeturn1search1turn3search3
