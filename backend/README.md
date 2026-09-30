# Backend دینا

Backend مسئول احراز هویت، مجوزها، tenant isolation، قوانین حسابداری، تراکنش‌های مالی، اشتراک و API است.

پیاده‌سازی فریم‌ورک Backend در این مرحله عمداً باز گذاشته شده تا انتخاب نهایی در مستندات معماری ثبت شود.

## نصب و اجرا

```bash
pip install -r backend/requirements.txt
cp .env.example .env   # سپس مقادیر واقعی را وارد کنید
uvicorn src.main:app --app-dir backend
```

متغیرهای محیطی از `.env.example` خوانده می‌شوند: `ENVIRONMENT`، `SECRET_KEY`، `JWT_ALGORITHM`،
`JWT_EXPIRE_MINUTES` و `DATABASE_URL`. خارج از محیط `test`، نبودن یا خالی بودن `SECRET_KEY` باعث
بالا نیامدن سرویس نمی‌شود (هیچ secret پیش‌فرضی در کد وجود ندارد).

## رمز عبور

`src/security.py` از Argon2id (`argon2-cffi`) استفاده می‌کند و hash را به صورت PHC string ذخیره
می‌کند تا پارامترهای هزینه همراه hash جابه‌جا شوند. برای ارتقای hashهای قدیمی‌تر، پس از ورود
موفق از `needs_rehash` استفاده کنید و hash جدید را ذخیره کنید. هیچ رمز یا tokenی لاگ نمی‌شود.

## تست

```bash
pytest -q backend/tests tests/accounting   # ENVIRONMENT=test
```
