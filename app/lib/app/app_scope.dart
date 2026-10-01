import 'package:flutter/widgets.dart';

import '../features/auth/presentation/auth_controller.dart';
import '../features/organizations/presentation/organization_controller.dart';

/// Dependency scope for the widget tree.
///
/// The whole app is constructed with its controllers already wired, so no
/// screen reaches for a global singleton and every test can substitute fakes
/// for the network and the store.
class AppScope extends InheritedWidget {
  const AppScope({
    required this.authController,
    required this.organizationController,
    required super.child,
    super.key,
  });

  final AuthController authController;
  final OrganizationController organizationController;

  static AppScope of(BuildContext context) {
    final AppScope? scope = context
        .dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope.of() was called outside an AppScope.');
    return scope!;
  }

  @override
  bool updateShouldNotify(AppScope oldWidget) =>
      oldWidget.authController != authController ||
      oldWidget.organizationController != organizationController;
}