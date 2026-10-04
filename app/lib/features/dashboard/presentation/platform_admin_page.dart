import 'package:flutter/material.dart';
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
