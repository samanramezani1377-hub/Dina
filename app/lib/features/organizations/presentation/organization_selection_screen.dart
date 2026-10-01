import 'package:flutter/material.dart';

import '../../../app/app_scope.dart';
import '../domain/organization.dart';
import 'organization_controller.dart';

/// Lets the signed-in user choose the tenant the whole app is scoped to.
///
/// Four visibly different outcomes, never collapsed into one: loading, error,
/// empty membership, and the list.
class OrganizationSelectionScreen extends StatefulWidget {
  const OrganizationSelectionScreen({super.key});

  @override
  State<OrganizationSelectionScreen> createState() =>
      _OrganizationSelectionScreenState();
}

class _OrganizationSelectionScreenState
    extends State<OrganizationSelectionScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        AppScope.of(context).organizationController.load();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final OrganizationController controller = AppScope.of(
      context,
    ).organizationController;
    return Scaffold(
      appBar: AppBar(
        title: const Text('انتخاب سازمان'),
        actions: <Widget>[
          IconButton(
            onPressed: () => AppScope.of(context).authController.logout(),
            icon: const Icon(Icons.logout),
            tooltip: 'خروج از حساب',
          ),
        ],
      ),
      body: ListenableBuilder(
        listenable: controller,
        builder: (BuildContext context, Widget? child) => switch (controller.status) {
          OrganizationListStatus.initial || OrganizationListStatus.loading =>
            const _CenteredMessage(
              key: ValueKey<String>('organizations-loading'),
              icon: Icons.hourglass_empty,
              title: 'در حال دریافت سازمان‌ها',
              detail: 'لطفاً کمی صبر کنید.',
            ),
          OrganizationListStatus.error => _ErrorState(
            key: const ValueKey<String>('organizations-error'),
            message: controller.errorMessage ?? 'دریافت فهرست سازمان‌ها ناموفق بود.',
            onRetry: controller.load,
            onSignOut: () =>
                AppScope.of(context).authController.logout(),
          ),
          OrganizationListStatus.empty => const _CenteredMessage(
            key: ValueKey<String>('organizations-empty'),
            icon: Icons.domain_disabled_outlined,
            title: 'سازمانی در دسترس نیست',
            detail:
                'شما عضو هیچ سازمانی نیستید. برای دسترسی به امکانات حسابداری باید سازمانی که به شما تعلق دارد انتخاب کنید.',
          ),
          OrganizationListStatus.loaded => _OrganizationList(
            organizations: controller.organizations,
          ),
        },
      ),
    );
  }
}

class _OrganizationList extends StatelessWidget {
  const _OrganizationList({required this.organizations});

  final List<Organization> organizations;

  @override
  Widget build(BuildContext context) {
    final AppScope scope = AppScope.of(context);
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      itemCount: organizations.length + 1,
      separatorBuilder: (BuildContext context, int index) =>
          const SizedBox(height: 8),
      itemBuilder: (BuildContext context, int index) {
        if (index == 0) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              'سازمان‌هایی که در آن‌ها عضو هستید:',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          );
        }
        final Organization organization = organizations[index - 1];
        return Card(
          key: ValueKey<String>('organization-${organization.id}'),
          child: ListTile(
            leading: CircleAvatar(backgroundColor: scheme.secondaryContainer),
            title: Text(organization.name),
            subtitle: Text('شناسه: ${organization.id}'),
            trailing: const Icon(Icons.chevron_left),
            onTap: () => scope.organizationController.select(organization.id),
          ),
        );
      },
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({
    required this.message,
    required this.onRetry,
    required this.onSignOut,
    super.key,
  });

  final String message;
  final Future<void> Function() onRetry;
  final Future<void> Function() onSignOut;

  @override
  Widget build(BuildContext context) {
    return _CenteredMessage(
      icon: Icons.cloud_off,
      title: 'دریافت سازمان‌ها ناموفق بود',
      detail: message,
      actions: <Widget>[
        FilledButton.icon(
          onPressed: onRetry,
          icon: const Icon(Icons.refresh),
          label: const Text('تلاش دوباره'),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: onSignOut,
          child: const Text('خروج از حساب'),
        ),
      ],
    );
  }
}

class _CenteredMessage extends StatelessWidget {
  const _CenteredMessage({
    required this.icon,
    required this.title,
    required this.detail,
    this.actions = const <Widget>[],
    super.key,
  });

  final IconData icon;
  final String title;
  final String detail;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: 48, color: scheme.outline),
            const SizedBox(height: 16),
            Text(
              title,
              style: Theme.of(context).textTheme.titleLarge,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              detail,
              style: Theme.of(context).textTheme.bodyMedium,
              textAlign: TextAlign.center,
            ),
            if (actions.isNotEmpty) ...<Widget>[
              const SizedBox(height: 24),
              ...actions,
            ],
          ],
        ),
      ),
    );
  }
}