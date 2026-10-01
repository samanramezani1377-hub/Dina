import '../../../../app/api/api_exception.dart';
import '../domain/auth_status.dart';
import '../domain/session.dart';
import 'auth_api.dart';

/// Outcome of restoring a persisted session.
class SessionRestore {
  const SessionRestore({
    required this.status,
    this.user,
    this.organizationId,
    this.failureMessage,
  });

  final AuthStatus status;
  final AuthenticatedUser? user;
  final String? organizationId;

  /// Set when the restore attempt itself failed for a reason the user can act
  /// on. The shell shows a retry instead of guessing a state.
  final String? failureMessage;

  static SessionRestore resolved({
    required AuthStatus status,
    AuthenticatedUser? user,
    String? organizationId,
  }) => SessionRestore(
    status: status,
    user: user,
    organizationId: organizationId,
  );

  static SessionRestore failed(String message) =>
      SessionRestore(status: AuthStatus.restoring, failureMessage: message);
}

/// Coordinates identity state and its persistence.
class AuthRepository {
  AuthRepository({required AuthApi api, required SessionStore sessionStore})
    : _api = api,
      _sessionStore = sessionStore;

  final AuthApi _api;
  final SessionStore _sessionStore;

  /// Called once at start-up, before any screen is chosen.
  ///
  /// With no stored token the answer is immediate. With a stored token the
  /// token is validated against `/auth/me` so a revoked or expired session
  /// never reaches the dashboard, and the user is never shown a shell they
  /// are not entitled to.
  Future<SessionRestore> restore() async {
    final String? token = await _sessionStore.readAccessToken();
    // Adopting the token before the first call is what puts the Authorization
    // header on `/auth/me`; restoring it only after the call would send the
    // request unauthenticated and throw away a perfectly good session.
    _sessionStore.setActiveToken(token);
    if (token == null || token.isEmpty) {
      return SessionRestore.resolved(status: AuthStatus.signedOut);
    }
    try {
      final AuthenticatedUser user = await _api.me();
      final String? organizationId =
          await _sessionStore.readSelectedOrganizationId();
      await _sessionStore.saveSession(
        Session(accessToken: token, user: user),
      );
      return SessionRestore.resolved(
        status: organizationId == null || organizationId.isEmpty
            ? AuthStatus.organizationSelectionRequired
            : AuthStatus.ready,
        user: user,
        organizationId: organizationId,
      );
    } on ApiException catch (error) {
      if (error.isSessionInvalid) {
        // The server rejected the token: the stored credentials are worthless
        // and must be removed rather than retried forever.
        await _sessionStore.clearAll();
        return SessionRestore.resolved(status: AuthStatus.signedOut);
      }
      return SessionRestore.failed(error.message);
    } on NetworkException catch (error) {
      return SessionRestore.failed(error.message);
    }
  }

  Future<Session> login({required String email, required String password}) async {
    final AuthResult result = await _api.login(email: email, password: password);
    await _persistAfterAuthentication(result.session);
    return result.session;
  }

  Future<Session> register({
    required String email,
    required String password,
    String? displayName,
  }) async {
    final AuthResult result = await _api.register(
      email: email,
      password: password,
      displayName: displayName,
    );
    await _persistAfterAuthentication(result.session);
    return result.session;
  }

  /// A fresh sign-in must not inherit a tenant chosen before it: the new
  /// credentials could belong to a different set of organizations. The
  /// selection is re-made from the current membership list.
  Future<void> _persistAfterAuthentication(Session session) async {
    await _sessionStore.clearSelectedOrganization();
    await _sessionStore.saveSession(session);
  }

  /// Forgets every trace of the session, tenant selection included.
  Future<void> logout() => _sessionStore.clearAll();
}
