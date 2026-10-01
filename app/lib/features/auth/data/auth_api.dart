import '../../../../app/api/api_client.dart';
import '../../../../app/api/api_exception.dart';
import '../domain/session.dart';

/// Result of an authentication call that may or may not have created a session.
class AuthResult {
  const AuthResult({required this.session, required this.createdAccount});

  final Session session;

  /// True when this call registered a brand new account rather than signing an
  /// existing one in. The UI uses it only for a confirmation message.
  final bool createdAccount;
}

/// HTTP surface for identity. Contains no persistence and no state.
class AuthApi {
  const AuthApi(this._client);

  final ApiClient _client;

  Future<AuthResult> login({required String email, required String password}) async {
    final JsonMap? body = await _client.post(
      '/auth/login',
      body: <String, Object?>{'email': email, 'password': password},
    );
    return AuthResult(
      session: _sessionFrom(body, 'ورود با موفقیت انجام نشد.'),
      createdAccount: false,
    );
  }

  Future<AuthResult> register({
    required String email,
    required String password,
    String? displayName,
  }) async {
    final JsonMap? body = await _client.post(
      '/auth/register',
      body: <String, Object?>{
        'email': email,
        'password': password,
        if (displayName != null && displayName.isNotEmpty)
          'display_name': displayName,
      },
    );
    return AuthResult(
      session: _sessionFrom(body, 'ثبت‌نام با موفقیت انجام نشد.'),
      createdAccount: true,
    );
  }

  /// Resolves the signed-in user from a bearer token, or throws an
  /// [ApiException] whose `isSessionInvalid` is true when the token is no
  /// longer usable.
  Future<AuthenticatedUser> me() async {
    final JsonMap? body = await _client.get('/auth/me');
    if (body == null) {
      throw const ApiException(
        message: 'پاسخ سرور برای کاربر جاری معتبر نیست.',
        code: 'malformed_response',
      );
    }
    return _userFrom(body);
  }

  Session _sessionFrom(JsonMap? body, String failureMessage) {
    if (body == null) {
      throw ApiException(message: failureMessage, code: 'malformed_response');
    }
    final Object? rawToken = body['access_token'] ?? body['token'];
    if (rawToken is! String || rawToken.isEmpty) {
      throw ApiException(message: failureMessage, code: 'malformed_response');
    }
    return Session(
      accessToken: rawToken,
      user: _userFrom(body),
    );
  }

  AuthenticatedUser _userFrom(JsonMap body) {
    final Object rawUser = body['user'] ?? body;
    if (rawUser is! Map<String, Object?>) {
      throw const ApiException(
        message: 'اطلاعات کاربر در پاسخ سرور معتبر نیست.',
        code: 'malformed_response',
      );
    }
    try {
      return AuthenticatedUser.fromJson(rawUser);
    } on FormatException catch (error) {
      throw ApiException(message: error.message, code: 'malformed_response');
    }
  }
}