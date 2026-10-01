import 'package:flutter/foundation.dart';

import '../data/auth_repository.dart';
import '../domain/auth_status.dart';
import '../domain/session.dart';

/// Drives the root of the application.
///
/// The gate is the only thing that reads [status]; screens read the derived
/// getters. Transitioning to [AuthStatus.restoring] is always the first thing
/// that happens, so there is no frame in which a signed-in user could be shown
/// the login screen.
class AuthController extends ChangeNotifier {
  AuthController(this._repository);

  final AuthRepository _repository;

  AuthStatus _status = AuthStatus.restoring;
  AuthStatus get status => _status;

  AuthenticatedUser? _user;
  AuthenticatedUser? get user => _user;

  String? _selectedOrganizationId;
  String? get selectedOrganizationId => _selectedOrganizationId;

  String? _restoreFailure;
  String? get restoreFailure => _restoreFailure;

  /// Performs the cold-start resolution. Safe to call more than once; the retry
  /// button on the restore-failure screen calls it again.
  Future<void> restore() async {
    _set(
      status: AuthStatus.restoring,
      user: null,
      organizationId: null,
      restoreFailure: null,
    );
    final SessionRestore result = await _repository.restore();
    if (result.failureMessage != null) {
      _set(
        status: AuthStatus.restoring,
        user: null,
        organizationId: null,
        restoreFailure: result.failureMessage,
      );
      return;
    }
    _set(
      status: result.status,
      user: result.user,
      organizationId: result.organizationId,
      restoreFailure: null,
    );
  }

  Future<void> login({required String email, required String password}) async {
    final Session session = await _repository.login(
      email: email,
      password: password,
    );
    _set(
      status: AuthStatus.organizationSelectionRequired,
      user: session.user,
      organizationId: null,
      restoreFailure: null,
    );
  }

  Future<void> register({
    required String email,
    required String password,
    String? displayName,
  }) async {
    final Session session = await _repository.register(
      email: email,
      password: password,
      displayName: displayName,
    );
    _set(
      status: AuthStatus.organizationSelectionRequired,
      user: session.user,
      organizationId: null,
      restoreFailure: null,
    );
  }

  /// Records the tenant the user just picked and moves to the shell.
  void selectOrganization(String organizationId) {
    _set(
      status: AuthStatus.ready,
      user: _user,
      organizationId: organizationId,
      restoreFailure: null,
    );
  }

  /// Returns to the organization list without signing out — the way back after
  /// picking the wrong tenant.
  void changeOrganization() {
    _set(
      status: AuthStatus.organizationSelectionRequired,
      user: _user,
      organizationId: null,
      restoreFailure: null,
    );
  }

  Future<void> logout() async {
    await _repository.logout();
    _set(
      status: AuthStatus.signedOut,
      user: null,
      organizationId: null,
      restoreFailure: null,
    );
  }

  void _set({
    required AuthStatus status,
    required AuthenticatedUser? user,
    required String? organizationId,
    required String? restoreFailure,
  }) {
    _status = status;
    _user = user;
    _selectedOrganizationId = organizationId;
    _restoreFailure = restoreFailure;
    notifyListeners();
  }
}
