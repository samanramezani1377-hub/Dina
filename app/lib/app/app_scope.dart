import 'package:flutter/widgets.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/organizations/presentation/organization_controller.dart';
import 'api/api_client.dart';

class AppScope extends InheritedWidget {
  const AppScope({required this.authController, required this.organizationController, required this.api, required super.child, super.key});
  final AuthController authController;
  final OrganizationController organizationController;
  final ApiClient api;
  static AppScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope.of() was called outside an AppScope.');
    return scope!;
  }
  @override
  bool updateShouldNotify(AppScope oldWidget) =>
      oldWidget.authController != authController ||
      oldWidget.organizationController != organizationController ||
      oldWidget.api != api;
}
