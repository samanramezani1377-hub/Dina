import 'package:flutter/material.dart';

/// Honest placeholder for a destination that is wired into the navigation but
/// not built yet.
///
/// It states what the screen will do. It never shows sample or invented data,
/// because a placeholder with made-up numbers is indistinguishable from a real
/// balance to anyone reading the app.
class NotImplementedPlaceholder extends StatelessWidget {
  const NotImplementedPlaceholder({
    required this.title,
    required this.description,
    super.key,
  });

  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.construction_outlined, size: 48, color: scheme.outline),
            const SizedBox(height: 16),
            Text(
              title,
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Chip(
              avatar: Icon(Icons.pending_outlined, size: 18, color: scheme.onSurfaceVariant),
              label: const Text('هنوز پیاده‌سازی نشده است'),
            ),
            const SizedBox(height: 16),
            Text(
              description,
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'هیچ داده‌ای برای این بخش بارگذاری نشده است.',
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

/// The dashboard landing page.
///
/// It shows what is genuinely known — the signed-in user, the selected
/// organization — and an explicit empty state for everything else. There is no
/// summary of balances here because no balance has been fetched.
class DashboardHomePage extends StatelessWidget {
  const DashboardHomePage({
    required this.organizationName,
    required this.userLabel,
    super.key,
  });

  final String organizationName;
  final String userLabel;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: <Widget>[
        Text(
          organizationName,
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 4),
        Text(
          'خوش آمدید، $userLabel',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 24),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(Icons.inbox_outlined, color: scheme.outline),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'هنوز داده‌ای برای نمایش وجود ندارد',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'تا زمانی که اسناد حسابداری و حساب‌ها ثبت نشده باشند، هیچ مانده یا گردشی برای نمایش وجود ندارد. این صفحه هیچ عددی را حدس نمی‌زند.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        Text(
          'میان‌برها',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        const _NoDataNote(),
      ],
    );
  }
}

class _NoDataNote extends StatelessWidget {
  const _NoDataNote();

  @override
  Widget build(BuildContext context) {
    return Text(
      'برای شروع، سرفصل حساب‌ها و سند حسابداری را از نوار کناری باز کنید. هر دو بخش در این نسخه هنوز پیاده‌سازی نشده‌اند.',
      style: Theme.of(context).textTheme.bodySmall,
    );
  }
}