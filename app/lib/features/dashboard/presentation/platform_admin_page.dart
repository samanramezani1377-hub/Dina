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
    ('zarinpal_merchant_id', 'زرین‌پال — Merchant ID', false),
    ('zarinpal_callback_url', 'زرین‌پال — Callback URL', false),
    ('zarinpal_webhook_secret', 'زرین‌پال — Webhook Secret', true),
    ('taxpayer_system_username', 'سامانه مؤدیان — نام کاربری', false),
    ('taxpayer_system_password', 'سامانه مؤدیان — رمز عبور', true),
    ('taxpayer_system_client_id', 'سامانه مؤدیان — Client ID', false),
    ('taxpayer_system_client_secret', 'سامانه مؤدیان — Client Secret', true),
    ('taxpayer_system_fiscal_id', 'سامانه مؤدیان — شناسه حافظه مالیاتی', false),
    ('taxpayer_system_api_url', 'سامانه مؤدیان — API URL', false),
    ('backup_database_url', 'Backup — Database URL', true),
    ('backup_storage_url', 'Backup — Storage URL', false),
    ('backup_access_key', 'Backup — Access Key', true),
    ('backup_secret_key', 'Backup — Secret Key', true),
    ('monitoring_dsn', 'Monitoring — DSN', true),
    ('monitoring_alert_webhook', 'Monitoring — Alert Webhook', true),
    ('e2e_base_url', 'E2E — Production URL', false),
    ('e2e_token', 'E2E — Token', true),
    ('android_keystore_b64', 'Android — Keystore (Base64)', true),
    ('android_key_alias', 'Android — Key Alias', false),
    ('android_key_password', 'Android — Key Password', true),
    ('android_store_password', 'Android — Store Password', true),
    ('windows_signing_certificate_b64', 'Windows — Certificate (Base64)', true),
    ('windows_signing_password', 'Windows — Certificate Password', true),
  ];

  Future<void> _saveSetting(String key, String value) async {
    await AppScope.of(context).api.put('/platform/settings/$key', body: {'value': value});
  }

  Future<void> _openPlatformSettings() async {
    final controllers = <String, TextEditingController>{
      for (final item in _settings) item.$1: TextEditingController(),
    };
    try {
      if (!mounted) return;
      await showDialog<void>(context: context, builder: (dialogContext) => AlertDialog(
        title: const Text('تنظیمات مالک پلتفرم'),
        content: SizedBox(width: 620, child: SingleChildScrollView(child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('مقادیر حساس در Backend به‌صورت رمزنگاری‌شده ذخیره می‌شوند. برای تغییر هر مقدار، مقدار جدید را وارد کنید.'),
            const SizedBox(height: 16),
            for (final item in _settings)
              Padding(padding: const EdgeInsets.only(bottom: 10), child: TextField(
                controller: controllers[item.$1],
                obscureText: item.$3,
                decoration: InputDecoration(labelText: item.$2, border: const OutlineInputBorder(), suffixIcon: IconButton(icon: const Icon(Icons.paste), onPressed: () async {
                  final data = await Clipboard.getData(Clipboard.kTextPlain); if (data?.text != null) controllers[item.$1]!.text = data!.text!;
                })),
              )),
          ],
        ))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('انصراف')),
          FilledButton(onPressed: () async {
            try {
              for (final item in _settings) { final value = controllers[item.$1]!.text.trim(); if (value.isNotEmpty) await _saveSetting(item.$1, value); }
              if (dialogContext.mounted) Navigator.pop(dialogContext);
              if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تنظیمات ذخیره شد')));
            } catch (e) { if (dialogContext.mounted) ScaffoldMessenger.of(dialogContext).showSnackBar(SnackBar(content: Text('ذخیره تنظیمات ناموفق بود: $e'))); }
          }, child: const Text('ذخیره همه')),
        ],
      ));
    } finally { for (final c in controllers.values) c.dispose(); }
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
