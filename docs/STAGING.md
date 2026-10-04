# محیط تست پایدار دینا

این محیط دیگر وابسته به GitHub Actions و Quick Tunnel نیست.

## معماری
- Backend: FastAPI
- Database: PostgreSQL دائمی Render
- URL پیش‌فرض: https://dina-api.onrender.com
- Health: /health
- Readiness: /health/ready
- Seed: قبل از هر deploy در staging و به‌صورت idempotent اجرا می‌شود.
- E2E: .github/workflows/e2e-staging.yml
- APK: با همان API_BASE_URL staging ساخته می‌شود.

## حساب تست
- Email: dina.test@example.com
- Password: Dina-Test-2026!
- سازمان: «دینا - سازمان تست»

این حساب فقط برای staging است و نباید برای production استفاده شود.

## راه‌اندازی
1. فایل render.yaml را به‌عنوان Render Blueprint متصل و deploy کنید.
2. Render یک Web Service و PostgreSQL دائمی می‌سازد.
3. readiness باید روی /health/ready سبز شود.
4. workflow «Dina persistent staging E2E» را دستی اجرا کنید.
5. آرتیفکت dina-staging-apk همان APK متصل به backend پایدار است.

## مسیر E2E
health → readiness → login → me → organizations → accounts → dashboard/trial-balance → create journal → post journal → ledger

هر مرحله در صورت شکست workflow را قرمز می‌کند.
