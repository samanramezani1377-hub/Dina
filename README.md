# Dina

دینا — دستیار نوین اداری.

پروژه دو بخش دارد: `app/` یک اپ Flutter، و `backend/` یک سرویس FastAPI با `/api/v1`.
مستند کامل قواعد مالی در [`docs/ACCOUNTING_PROJECT_SPEC.md`](docs/ACCOUNTING_PROJECT_SPEC.md) است و
آنچه واقعاً پیاده‌سازی شده (و آنچه نشده) در
[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md).

## راه‌اندازی backend

پیش‌نیاز: Python 3.12 و (برای دیتابیس) PostgreSQL 16.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env    # مقدارها را پر کنید؛ SECRET_KEY واقعی لازم است
```

`.env.example` فقط placeholder دارد و هیچ secret واقعی در آن نیست. بیرون از محیط `test`، نبودن یا
خالی بودن `SECRET_KEY` باعث می‌شود سرویس اصلاً بالا نیاید — این عمدی است.

برای ساختن یک `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### اعمال migrationها

به ترتیب نام فایل اجرا کنید؛ `002_audit_logs.sql` کلیدهای خارجی‌اش را به‌صورت شرطی به جدول‌هایی که
`001` می‌سازد وصل می‌کند، پس ترتیب مهم است.

```bash
createdb dina
for f in database/migrations/*.sql; do
  psql -v ON_ERROR_STOP=1 -d dina -f "$f"
done
```

### اجرا

```bash
uvicorn src.main:app --app-dir backend
```

- API docs: <http://127.0.0.1:8000/docs>
- سلامت سرویس: `GET /health`

## متغیرهای محیطی

| متغیر | پیش‌فرض | توضیح |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | `production` / `staging` / `development` / `test`. فقط `test` نبودن `SECRET_KEY` را تحمل می‌کند. |
| `SECRET_KEY` | — | کلید امضای توکن. بیرون از `test` اجباری است؛ کمتر از ۳۲ کاراکتر یا برابر placeholder پذیرفته نمی‌شود. |
| `JWT_ALGORITHM` | `HS256` | فقط `HS256`، `HS384` یا `HS512`. |
| `JWT_EXPIRE_MINUTES` | `60` | عمر توکن. |
| `DATABASE_URL` | `postgresql+psycopg://dina@localhost:5432/dina` | رشته اتصال. |

**وضعیت فعلی:** محیط production از PostgreSQL برای state اصلی استفاده می‌کند؛ migrationهای حسابداری، هویت، SaaS، idempotency، error log و ماژول‌های عملیاتی در CI روی PostgreSQL واقعی اعمال می‌شوند. جزئیات وضعیت واقعی در `docs/IMPLEMENTATION_STATUS.md` نگهداری می‌شود.

## اجرای تست‌ها

```bash
pytest -q backend/tests
```

این فرمان بدون هیچ تنظیم اضافه‌ای کار می‌کند و `ENVIRONMENT=test` را خودش می‌گذارد
(`backend/tests/conftest.py`).

تست‌های audit روی PostgreSQL واقعی در `backend/tests/test_audit_postgres.py` هستند. برای اجرای آن‌ها
جدا از CI باید یک دیتابیس بالا باشد:

```bash
createdb dina_test
for f in database/migrations/*.sql; do psql -v ON_ERROR_STOP=1 -d dina_test -f "$f"; done
DATABASE_URL=postgresql://localhost:5432/dina_test pytest -q backend/tests
```

اگر `DATABASE_URL` نباشد این تست‌ها **skip** می‌شوند (بیرون از CI) — نه اینکه بی‌صدا سبز شوند.

## CI

سه job وجود دارد:

| Job | چه می‌کند |
| --- | --- |
| `Backend tests` | تست‌ها روی یک سرویس `postgres:16` واقعی؛ migrationها اعمال و `pytest -q backend/tests` اجرا می‌شود. |
| `Flutter lint, test and Android APK` | `flutter analyze --fatal-infos --fatal-warnings`، `flutter test`، ساخت APK و بررسی وجود فایل. |
| `Flutter Windows build` | ساخت دسکتاپ ویندوز روی runner ویندوزی و بررسی وجود باینری. |

فرمان‌های دقیق backend: نصب با `pip install -r backend/requirements.txt`، اعمال
`database/migrations/*.sql` با `psql -v ON_ERROR_STOP=1`، بررسی وجود جدول `audit_logs`، سپس
`pytest -q backend/tests`.

## اپ Flutter

```bash
cd app
flutter pub get
flutter run          # Android یا Windows
flutter test
```

در CI فایل‌های platform با `flutter create . --platforms=<platform>` ساخته می‌شوند (فقط فایل‌های
گمشده ساخته می‌شوند و `lib/` و `test/` دست‌نخورده می‌مانند) و سپس build و بررسی آرتیفکت انجام می‌شود.