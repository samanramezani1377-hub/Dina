import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../../features/auth/domain/auth_status.dart';
import '../../features/auth/presentation/auth_controller.dart';
import '../../features/auth/presentation/auth_screen.dart';
import '../../features/dashboard/presentation/dashboard_shell.dart';
import '../../features/organizations/presentation/organization_controller.dart';
import '../../features/organizations/presentation/organization_selection_screen.dart';

/// Decides which tree the application shows.
///
/// The four [AuthStatus] values map one-to-one onto the four possible roots:
/// a restoring screen while the answer is unknown, the login tree, the
/// organization selection tree, or the dashboard shell. Nothing is decided
/// optimistically, so a signed-in user is never shown the login screen while
/// their session is being validated.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final AuthController auth = AppScope.of(context).authController;
    return ListenableBuilder(
      listenable: auth,
      builder: (BuildContext context, Widget? child) => switch (auth.status) {
        AuthStatus.restoring => _RestoringScreen(
          failureMessage: auth.restoreFailure,
          onRetry: auth.restore,
        ),
        AuthStatus.signedOut => const AuthScreen(),
        AuthStatus.organizationSelectionRequired =>
          const OrganizationSelectionScreen(),
        AuthStatus.ready => const _TenantEntitlementGate(),
      },
    );
  }
}

/// Confirms that a restored tenant selection is still one the server will hand
/// this user.
///
/// The stored id is a claim from a previous run, not an authorization. Before
/// the shell opens, the live membership list is fetched and the id checked
/// against it. A selection that is no longer present is discarded and the user
/// is sent back to pick again, and a failed check does not open the shell at
/// all.
class _TenantEntitlementGate extends StatefulWidget {
  const _TenantEntitlementGate();

  @override
  State<_TenantEntitlementGate> createState() => _TenantEntitlementGateState();
}

class _TenantEntitlementGateState extends State<_TenantEntitlementGate> {
  bool _requested = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _verifyOnce();
  }

  @override
  void dispose() {
    _requested = false;
    super.dispose();
  }

  void _verifyOnce() {
    if (_requested) {
      return;
    }
    _requested = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      AppScope.of(context).organizationController.load();
    });
  }

  @override
  Widget build(BuildContext context) {
    final AppScope scope = AppScope.of(context);
    final AuthController auth = scope.authController;
    final OrganizationController organizations = scope.organizationController;
    final String? selectedId = auth.selectedOrganizationId;

    return ListenableBuilder(
      listenable: organizations,
      builder: (BuildContext context, Widget? child) => switch (organizations.status) {
        OrganizationListStatus.initial || OrganizationListStatus.loading =>
          const _RestoringScreen(onRetry: _noop),
        OrganizationListStatus.error => _RestoringScreen(
          failureMessage:
              organizations.errorMessage ?? 'تأیید دسترسی سازمان ناموفق بود.',
          onRetry: organizations.load,
        ),
        OrganizationListStatus.empty => _SelectionRejected(
          onProceed: () => _reject(scope),
        ),
        OrganizationListStatus.loaded =>
          selectedId != null && organizations.contains(selectedId)
              ? const DashboardShell()
              : _SelectionRejected(onProceed: () => _reject(scope)),
      },
    );
  }

  void _reject(AppScope scope) {
    scope.organizationController.clearSelection();
    scope.authController.changeOrganization();
  }
}

Future<void> _noop() async {}

class _SelectionRejected extends StatelessWidget {
  const _SelectionRejected({required this.onProceed});

  final VoidCallback onProceed;

  @override
  Widget build(BuildContext context) {
    WidgetsBinding.instance.addPostFrameCallback((_) => onProceed());
    return const _RestoringScreen(onRetry: _noop);
  }
}

/// Shown whenever the app does not yet know which tree is correct.
class _RestoringScreen extends StatelessWidget {
  const _RestoringScreen({this.failureMessage, this.onRetry});

  /// Non-null when restoring failed for a reason the user can retry.
  final String? failureMessage;

  final Future<void> Function()? onRetry;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: failureMessage == null
              ? const CircularProgressIndicator()
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(Icons.cloud_off, size: 48, color: scheme.outline),
                    const SizedBox(height: 16),
                    Text(
                      'ادامه کار ممکن نشد',
                      style: Theme.of(context).textTheme.titleLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      failureMessage!,
                      style: Theme.of(context).textTheme.bodyMedium,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: onRetry,
                      icon: const Icon(Icons.refresh),
                      label: const Text('تلاش دوباره'),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}