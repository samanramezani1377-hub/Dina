import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';

class PlatformAdminPage extends StatefulWidget {
  const PlatformAdminPage({super.key});
  @override
  State<PlatformAdminPage> createState() => _PlatformAdminPageState();
}

class _PlatformAdminPageState extends State<PlatformAdminPage> {
  late Future<JsonMap?> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<JsonMap?> _load() =>
      AppScope.of(context).api.get('/platform/dashboard');

  void retry() => setState(() => _future = _load());

  String v(Object? x) => x?.toString() ?? '—';

  static const _settings = <(String, String, bool)>[
    ('zarinpal_merchant_id', 'زرین‌پال — شناسه پذیرنده', false),
    ('zarinpal_callback_url', 'زرین‌پال — نشانی بازگشت', false),
    ('zarinpal_webhook_secret', 'زرین‌پال — کلید امنیتی اعلان', true),
    ('taxpayer_system_username', 'سامانه مؤدیان — نام کاربری', false),
    ('taxpayer_system_password', 'سامانه مؤدیان — رمز عبور', true),
    ('taxpayer_system_client_id', 'سامانه مؤدیان — شناسه کاربری برنامه', false),
    ('taxpayer_system_client_secret', 'سامانه مؤدیان — کلید محرمانه برنامه', true),
    ('taxpayer_system_fiscal_id', 'سامانه مؤدیان — شناسه حافظه مالیاتی', false),
    ('taxpayer_system_api_url', 'سامانه مؤدیان — نشانی برخط', false),
    ('backup_database_url', 'پشتیبان‌گیری — نشانی پایگاه داده', true),
    ('backup_storage_url', 'پشتیبان‌گیری — نشانی فضای ذخیره‌سازی', false),
    ('backup_access_key', 'پشتیبان‌گیری — کلید دسترسی', true),
    ('backup_secret_key', 'پشتیبان‌گیری — کلید محرمانه', true),
    ('monitoring_dsn', 'پایش — شناسه اتصال', true),
    ('monitoring_alert_webhook', 'پایش — نشانی اعلان', true),
    ('e2e_base_url', 'آزمون نهایی — نشانی محیط عملیاتی', false),
    ('e2e_token', 'آزمون نهایی — کلید دسترسی', true),
    ('android_keystore_b64', 'اندروید — مخزن امضای برنامه', true),
    ('android_key_alias', 'اندروید — نام کلید', false),
    ('android_key_password', 'اندروید — رمز کلید', true),
    ('android_store_password', 'اندروید — رمز مخزن امضا', true),
    ('windows_signing_certificate_b64', 'ویندوز — گواهی امضا', true),
    ('windows_signing_password', 'ویندوز — رمز گواهی امضا', true),
  ];

  Future<void> _saveSetting(String key, String value) async {
    await AppScope.of(context).api.put('/platform/settings/$key', body: {'value': value});
  }

  Future<void> _openPlatformSettings() async {
    final controllers = <String, TextEditingController>{
      for (final item in _settings) item.$1: TextEditingController(),
    };
    final configured = <String, bool>{};
    try {
      final list = await AppScope.of(context).api.get('/platform/settings');
      if (list?['items'] is List) {
        for (final raw in list!['items'] as List) {
          if (raw is JsonMap && raw['key'] != null) configured[raw['key'].toString()] = raw['configured'] == true;
        }
      }
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (dialogContext) => AlertDialog(
        title: const Text('تنظیمات مالک پلتفرم'),
        content: SizedBox(width: 620, child: SingleChildScrollView(child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('مقادیر حساس در سرور به‌صورت رمزنگاری‌شده نگهداری می‌شوند و مقدار قبلی هرگز نمایش داده نمی‌شود. برای جایگزینی، مقدار جدید را وارد کنید.'),
            const SizedBox(height: 16),
            for (final item in _settings)
              Padding(padding: const EdgeInsets.only(bottom: 10), child: TextField(
                controller: controllers[item.$1],
                obscureText: item.$3,
                decoration: InputDecoration(labelText: item.$2, helperText: configured[item.$1] == true ? 'تنظیم شده — برای جایگزینی مقدار جدید وارد کنید' : 'تنظیم نشده', border: const OutlineInputBorder(), suffixIcon: IconButton(icon: const Icon(Icons.paste), onPressed: () async {
                  final data = await Clipboard.getData(Clipboard.kTextPlain); if (data?.text != null) controllers[item.$1]!.text = data!.text!;
                })),
              )),
          ],
        ))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('انصراف')),
          FilledButton(onPressed: () async {
            try {
              for (final item in _settings) {
                final String value = controllers[item.$1]!.text.trim();
                if (value.isNotEmpty) await _saveSetting(item.$1, value);
              }
              if (dialogContext.mounted) Navigator.pop(dialogContext);
              if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تنظیمات ذخیره شد')));
            } catch (e) { if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(SnackBar(content: Text('ذخیره تنظیمات ناموفق بود: $e'))); }
          }, child: const Text('ذخیره همه')),
        ],
      ));
    } finally {
      for (final c in controllers.values) {
        c.dispose();
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('مدیریت پلتفرم')),
        body: FutureBuilder<JsonMap?>(
          future: _future,
          builder: (context, s) {
            if (s.connectionState != ConnectionState.done) {
              return const Center(child: CircularProgressIndicator());
            }
            if (s.hasError) {
              return Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('دسترسی یا بارگذاری ناموفق بود'),
                    const SizedBox(height: 10),
                    Text(s.error.toString(), textAlign: TextAlign.center),
                    const SizedBox(height: 10),
                    FilledButton(
                      onPressed: retry,
                      child: const Text('تلاش دوباره'),
                    ),
                  ],
                ),
              );
            }
            final d = s.data ?? <String, Object?>{};
            final cards = <(String, String)>[
              ('کاربران', v(d['users'])),
              ('سازمان‌ها', v(d['organizations'])),
              ('اشتراک فعال', v(d['active_subscriptions'])),
              ('پرداخت‌ها', v(d['payment_attempts'])),
              ('پرداخت موفق', v(d['successful_payments'])),
              ('درآمد ثبت‌شده', v(d['revenue'])),
            ];
            return ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Text(
                  'داشبورد پلتفرم',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    for (final x in cards)
                      SizedBox(
                        width: 220,
                        child: Card(
                          child: ListTile(
                            title: Text(x.$1),
                            subtitle: Text(
                              x.$2,
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 20),
                Card(child: ListTile(leading: const Icon(Icons.admin_panel_settings_outlined), title: const Text('تنظیمات مالک پلتفرم'), subtitle: const Text('درگاه، سامانه مؤدیان، Backup، Monitoring، E2E و کلیدهای Release'), trailing: const Icon(Icons.chevron_left), onTap: _openPlatformSettings)),
                const SizedBox(height: 12),
                const Card(
                  child: ListTile(
                    leading: Icon(Icons.security_outlined),
                    title: Text('دسترسی امن'),
                    subtitle: Text(
                      'تمام عملیات مدیریتی در Backend با مجوز platform_admin کنترل می‌شوند.',
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                const Card(
                  child: ListTile(
                    leading: Icon(Icons.info_outline),
                    title: Text('کنترل‌های تکمیلی'),
                    subtitle: Text(
                      'کاربران، سازمان‌ها، پلن‌ها، پرداخت‌ها، صورتحساب‌ها، سهمیه‌ها و رخدادهای امنیتی از API مدیریتی قابل مدیریت‌اند.',
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      );
}
