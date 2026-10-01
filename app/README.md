# اپلیکیشن دینا

کلاینت Flutter برای Android و Windows.

این پوشه محل کلاینت اصلی دینا است. ارتباط با Backend از طریق HTTPS انجام می‌شود و کلاینت منبع نهایی داده‌های مالی نیست.

## اجرا

### Android

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`10.0.2.2` آدرس loopback از دید شبیه‌ساز Android است؛ برای دستگاه فیزیکی باید IP همان شبکه را بدهید. برای خروجی نصبی:

```bash
flutter build apk --debug --dart-define=API_BASE_URL=https://api.example.com
```

### Windows

```bash
flutter pub get
flutter run -d windows --dart-define=API_BASE_URL=http://localhost:8000
```

پیش‌نیازها: Visual Studio 2022 با کامپوننت «Desktop development with C++» و Windows SDK. خروجی در `build/windows/x64/runner/Debug/` ساخته می‌شود.

### تنظیم آدرس Backend

آدرس پایه در زمان build تزریق می‌شود، بنابراین یک درخت سورس بدون ویرایش کد به هر backend قابل اشاره است:

```bash
flutter run --dart-define=API_BASE_URL=https://api.example.com
```

مقدار پیش‌فرض `http://10.0.2.2:8000` است. کلاینت مسیر `/api/v1` را خودش اضافه می‌کند، پس `API_BASE_URL` را بدون `/api/v1` بدهید:

| مقدار | نتیجه |
| --- | --- |
| `http://10.0.2.2:8000` | `http://10.0.2.2:8000/api/v1` |
| `https://api.example.com` | `https://api.example.com/api/v1` |

## پوشه‌های پلتفرم

پوشه‌های `android/` و `windows/` در git commit نشده‌اند. CI آن‌ها را با `flutter create .` می‌سازد (بدون `--overwrite`، پس فقط فایل‌های غایب را بازسازی می‌کند و به سورس دست نمی‌زند). برای اجرای محلی، اگر این پوشه‌ها را ندارید:

```bash
flutter create . --platforms=android,windows --project-name dina_app
```

## تست و تحلیل

```bash
flutter analyze --fatal-infos --fatal-warnings
flutter test
```

`--fatal-infos` یعنی هر info هم باید رفع شود؛ CI دقیقاً همین دو دستور را اجرا می‌کند.

## ساختار لایه‌ها

هر feature همان سه لایه را دارد و وابستگی همواره رو به پایین است: `presentation` به `domain` وابسته است، `data` به `domain`، و `domain` به هیچ‌کدام از این دو وابسته نیست.

| مسیر | یک خط توضیح |
| --- | --- |
| `lib/main.dart` | نقطه ورود؛ storage و transport واقعی را می‌سازد و `DinaApp` را اجرا می‌کند. |
| `lib/app/app.dart` | ریشه ترکیب (composition root)؛ کل گراف وابستگی در یک تابع خالص ساخته می‌شود. |
| `lib/app/app_scope.dart` | `InheritedWidget` برای توزیع controllerها؛ هیچ صفحه‌ای به singleton نمی‌رسد. |
| `lib/app/config/` | تنظیمات زمان build، از جمله `API_BASE_URL` از طریق `--dart-define`. |
| `lib/app/api/` | تنها نقطه‌ای که HTTP می‌داند؛ ترجمه پاسخ و خطا به واژگان یکسان `ApiException` / `NetworkException`. |
| `lib/app/routing/` | `AuthGate`: تصمیم می‌گیرد کدام درخت نمایش داده شود (در حال بازیابی، ورود، انتخاب سازمان، پوسته). |
| `lib/app/storage/` | قرارداد `KeyValueStore` و پیاده‌سازی `shared_preferences` به‌علاوه نسخه درون‌حافظه‌ای برای تست. |
| `lib/app/theme/` | تم Material 3، تایپوگرافی فارسی، RTL و breakpoint های چیدمان. |
| `lib/features/auth/domain/` | مدل‌های `Session` و `AuthenticatedUser` و enum چهارحالته `AuthStatus`، به‌همراه `SessionStore`. |
| `lib/features/auth/data/` | سطح HTTP احراز هویت و مخزنی که وضعیت نشست را هماهنگ می‌کند. |
| `lib/features/auth/presentation/` | `AuthController` و فرم ورود/ثبت‌نام؛ این لایه هیچ‌وقت اجازه ورود را خودش تصمیم نمی‌گیرد. |
| `lib/features/organizations/domain/` | مدل `Organization`. |
| `lib/features/organizations/data/` | دریافت فهرست سازمان‌های کاربر و ذخیره انتخاب مستأجر. |
| `lib/features/organizations/presentation/` | `OrganizationController` و صفحه انتخاب سازمان با چهار وضعیت متمایز. |
| `lib/features/dashboard/domain/` | نقشه ناوبری `ShellDestinations`؛ هر مقصد اعلام می‌کند ساخته شده یا نه. |
| `lib/features/dashboard/presentation/` | پوسته واکنش‌گرا (نوار پایین در عرض کم، پنل کناری در عرض زیاد) و صفحه خالی صادقانه داشبورد. |
| `test/support/` | `FakeTransport` اسکریپت‌شده و fixtureها؛ تست‌ها کلاینت واقعی را اجرا می‌کنند، بدون دست زدن به شبکه. |

## وضعیت پیاده‌سازی

پیاده‌سازی‌شده: بازیابی نشست، ورود و ثبت‌نام، انتخاب و تأیید سازمان، پوسته واکنش‌گرا، و ترجمه خطا.

عمداً ناتمام: هر مقصدی که در `ShellDestinations` مقدار `implemented: false` دارد (سرفصل حساب‌ها، سند حسابداری، دفتر کل، تراز آزمایشی، مشتریان، فاکتورها، پرداخت‌ها، تنظیمات) یک placeholder صریح «هنوز پیاده‌سازی نشده است» نشان می‌دهد و هیچ عددی نمی‌سازد.

جزئیات کامل در `docs/IMPLEMENTATION_STATUS.md`.
