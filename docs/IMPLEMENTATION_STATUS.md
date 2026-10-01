# وضعیت پیاده‌سازی دینا

- Flutter پایه Android/Windows
- FastAPI با `/api/v1`
- Organization و Membership/Role
- password hashing/verification پایه
- tenant-scoped membership check
- Double-entry validation و API آن
- PostgreSQL schema پایه حسابداری
- تست API، امنیت، tenant isolation و تراز بدهکار/بستانکار
- CI واقعی Backend و Flutter
- Audit log: جدول append-only، سرویس `backend/src/audit.py` با redaction، tenant-scoped query

## گام بعد
ثبت دائمی سند، token authentication و اتصال PostgreSQL.

## Audit log

سرویس `backend/src/audit.py` و جدول `audit_logs` (migration `002_audit_logs.sql`) اضافه شده‌اند.

- جدول append-only است: `UPDATE` و `DELETE` برای رول application در سطح DB لغو شده و trigger هر دو را رد می‌کند. در اپلیکیشن هیچ مسیر update/delete وجود ندارد.
- `record(...)` هرگز exception پرتاب نمی‌کند؛ خطای نوشتن audit فقط log می‌شود و عملیات اصلی شکست نمی‌خورد.
- لایه redaction: کلیدهای حساس (password، hash، token، authorization و ...) و مقادیر با شکل secret (JWT، argon2، hex طولانی، `key=value`) پیش از ذخیره با `[REDACTED]` جایگزین می‌شوند. یک pass نهایی روی متن serialize‌شده به‌عنوان backstop وجود دارد؛ اگر چیزی از آن رد شود کل metadata دور ریخته می‌شود.
- `query_for_organization(store, organization_id, caller_organization_id, role=...)` فقط به `owner` و `manager` اجازه خواندن می‌دهد. `organization_id` از context مجوز می‌آید، نه از ورودی کاربر. پارامتر `caller_organization_id` الزامی است و باید با `organization_id` هم‌خوانی داشته باشد؛ در غیر این صورت `AuditError` پرتاب می‌شود — یک cross-tenant read بنابراین impossible است، نه تنها empty. نقش به‌تنهایی هیچ چیزی را به `organization_id` وصل نمی‌کند.
- سقف metadata **پیش از** serialize شدن اعمال می‌شود، نه روی متن serialize‌شده: هر مقدار رشته‌ای به `MAX_METADATA_STRING_CHARS` محدود و در صورت نیاز کلیدها از انتها حذف می‌شوند تا مجموع از `MAX_METADATA_CHARS` بگذرد تا payload همچنان parse‌شدنی بماند (`metadata_truncated: true`). بریدنِ JSONِ serialize‌شده payload را غیرقابل‌بازگردانی می‌کرد.

### کجاها هنوز ناقص است

- **Store پیش‌فرض durable نیست.** `DEFAULT_STORE` یک `InMemoryAuditStore` است: dev-only، با سقف `DEFAULT_STORE_MAX_ROWS` (۱۰٬۰۰۰ ردیف) و از بین‌رفتنی با restart. سقف ردیف‌های موجود را حذف نمی‌کند (حذف، مسیر delete است)؛ پس از رسیدن به سقف append بعدی خطا می‌دهد و `record` آن را log می‌کند. `PostgresAuditStore` پیاده‌سازی و تست شده اما **هنوز در هیچ جایی instantiate نشده**؛ پس از در دسترس قرار گرفتن `DATABASE_URL` و لایه persistence (bead `d7c3ddf6`) باید `set_default_store(PostgresAuditStore(...))` صدا زده شود. تا آن زمان audit row‌ها بین restartها از بین می‌روند.
- **call site بدون احراز هویت.** `POST /api/v1/accounting/journals/validate` هنوز auth ندارد، پس tenant از بدنهٔ درخواست قابل اعتماد نیست. به همین دلیل row با `organization_id = NULL` ثبت می‌شود و شناسهٔ ادعاشده فقط با کلید `claimed_organization_id` در metadata می‌آید (کلید tenant نیست). پس از landing شدن JWT/RBAC باید از membership dependency خوانده شود.
- helperها `store`، `correlation_id`، `ip_address` و `metadata` را به‌صورت keyword-only صریح می‌گیرند؛ `**kwargs` حذف شده تا یک تایپ اشتباه به‌جای سکوت، `TypeError` بدهد.
- `InMemoryAuditStore.clear()` حذف شده است؛ fixtureها هر بار یک store تازه می‌سازند.

### وضعیت wiring

| عملیات | وضعیت |
| --- | --- |
| login موفق / ناموفق | helper آماده (`record_login_succeeded` / `record_login_failed`)، call site وجود ندارد — با JWT auth باید وصل شود |
| logout | helper آماده، call site وجود ندارد |
| ساخت organization | helper آماده، call site وجود ندارد |
| افزودن/حذف membership | helper آماده، call site وجود ندارد |
| ساخت account | helper آماده، call site وجود ندارد |
| journal | helper آماده؛ `POST /api/v1/accounting/journals/validate` به `journal.created` با `outcome` و `reason_code` وصل شده است. `organization_id` در audit row به صورت `None` ثبت می‌شود و `claimed_organization_id` در metadata ذخیره می‌شود (چون endpoint هنوز authentication ندارد). |
| posting، reversal، correction | helper آماده، endpoint هنوز وجود ندارد |
| payment | helper آماده، endpoint هنوز وجود ندارد |
| subscription | helper آماده، endpoint هنوز وجود ندارد |

## اصول
Backend منبع نهایی قواعد مالی است؛ مبالغ Decimal/NUMERIC هستند؛ اصلاح اسناد ثبت‌شده با reversal/correction انجام می‌شود؛ عملیات مالی transaction-based و tenant-scoped است.

## کلاینت Flutter

### پیاده‌سازی‌شده

- معماری لایه‌ای با یک مسیر برای هر feature (`data` / `domain` / `presentation`) و یک ریشه ترکیب در `app/lib/app/app.dart`؛ هیچ صفحه‌ای مستقیم به `shared_preferences` یا `package:http` وابسته نیست.
- `AuthGate` با چهار وضعیت mutually exclusive و exhaustive. یک کاربر وارد‌شده در cold start هرگز فرم ورود را نمی‌بیند، چون `restoring` همیشه اولین وضعیت است.
- توکن ذخیره‌شده **پیش از** نخستین درخواست فعال می‌شود، بنابراین `/auth/me` در شروع سرد با هدر درست ارسال می‌شود. تست `auth_gate_test.dart` این را مستقیماً روی هدر ثبت‌شده بررسی می‌کند.
- تأیید مستأجر: شناسه ذخیره‌شده یک ادعا از اجرای قبلی است، نه مجوز. پیش از باز شدن پوسته، فهرست عضویت زنده خوانده و شناسه بررسی می‌شود. انتخاب نامعتبر دور ریخته می‌شود و شکست بررسی پوسته را باز نمی‌کند.
- تفکیک توکن از مستأجر در persistence: خروج هر دو را پاک می‌کند، ولی تغییر سازمان فقط انتخاب را پاک می‌کند تا کاربر دوباره login نکند. ورود تازه انتخاب قبلی را به ارث نمی‌برد.
- ترجمه خطا در یک واژگان واحد (`ApiClient` → `ApiException` / `NetworkException`). هیچ شکستی به‌صورت نتیجه خالی رندر نمی‌شود: صفحه HTML پروکسی، بدنه خالی و پاسخ با شکل اشتباه همگی خطا هستند.
- UI فارسی RTL با فونت Material 3 و پوسته واکنش‌گرا (نوار پایین در عرض کم، پنل کناری در عرض زیاد).

### Placeholder عمدی

هشت مقصد ناوبری (`implemented: false`) هر کدام یک placeholder صریح «هنوز پیاده‌سازی نشده است» نشان می‌دهند و هیچ عدد نمونه‌ای نمی‌سازند. یک تست، نبودِ هر رقم را روی متن صفحه داشبورد بررسی می‌کند، چون جایی که عدد ساختگی قرار بگیرد از عدد واقعی قابل تشخیص نیست.

### هنوز ناقص

- **هیچ قابلیت حسابداری ساخته نشده است.** سرفصل حساب‌ها، سند حسابداری، دفتر کل و تراز آزمایشی هنوز navigation entry بدون صفحه‌اند. داشبورد فقط نام کاربر و سازمان را نشان می‌دهد.
- **بدون رمزگذاری ذخیره‌سازی.** توکن دسترسی در `shared_preferences` به‌صورت متن ساده نوشته می‌شود. برای Android این یعنی `encryptedSharedPreferences` (یا `flutter_secure_storage`)، و برای Windows یک جایگزین معادل لازم است. تا وقتی این کار نشده، توکن روی دستگاه قابل استخراج است.
- **بدون refresh token.** فقط `access_token` ذخیره می‌شود و `token_expired` کاربر را به فرم ورود برمی‌گرداند؛ نشست طولانی بدون ورود دوباره کار نمی‌کند.
- **بدون حالت آفلاین و بدون صف خطای سراسری.** هر خطا فقط در صفحه‌ای که رخ داده دیده می‌شود.
- **بدون تست widget برای فرم ورود.** اعتبار ایمیل، قفل بودن دکمه submit هنگام درخواست، و toggle ثبت‌نام پوشش تست ندارند.
- **`SessionStore.readUser()` استفاده نمی‌شود.** کد هست و تست ندارد؛ بازیابی نشست کاربر را از `/auth/me` می‌گیرد و رکورد ذخیره‌شده را نمی‌خواند. یا باید استفاده شود یا حذف شود.
- **پوشه‌های پلتفرم در git نیستند.** `android/` و `windows/` با `flutter create .` در CI ساخته می‌شوند. مانفست تولیدشده در `android/app/src/main/AndroidManifest.xml` مجوز `INTERNET` ندارد (فقط مانفست‌های debug و profile دارند)، پس یک build از نوع release تا وقتی پلتفرم‌ها commit نشوند هیچ درخواست شبکه‌ای نمی‌تواند بفرستد. build مورد تأیید CI از نوع `--debug` است و این محدودیت را پنهان می‌کند.