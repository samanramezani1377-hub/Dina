/// The single error vocabulary shared by every layer of the client.
///
/// Every failure — transport, HTTP status, malformed payload — reaches the
/// presentation layer as one of these. Screens never see a raw exception and,
/// critically, never see a failure disguised as an empty result.
library;

/// Stable error codes produced by the backend error envelope.
abstract final class ApiErrorCode {
  static const String invalidCredentials = 'invalid_credentials';
  static const String tokenExpired = 'token_expired';
  static const String tokenInvalid = 'token_invalid';
  static const String emailAlreadyRegistered = 'email_already_registered';
  static const String notAMember = 'not_a_member';
  static const String permissionDenied = 'permission_denied';
  static const String organizationNotFound = 'organization_not_found';
  static const String validationError = 'validation_error';
}

/// Raised when the backend answered but the answer is not usable.
class ApiException implements Exception {
  const ApiException({
    required this.message,
    this.code,
    this.statusCode,
    this.details = const <String, Object?>{},
  });

  /// Stable machine code from the error envelope, when the backend sent one.
  final String? code;

  /// Human readable Persian-safe message suitable for display.
  final String message;

  /// HTTP status, absent for transport level failures.
  final int? statusCode;

  /// Extra context from the backend error envelope.
  final Map<String, Object?> details;

  /// True when the backend said the session is no longer usable, which is the
  /// only condition that may silently drop the stored token.
  bool get isSessionInvalid =>
      statusCode == 401 ||
      code == ApiErrorCode.tokenExpired ||
      code == ApiErrorCode.tokenInvalid;

  @override
  String toString() => 'ApiException($statusCode, $code): $message';
}

/// Raised when the request never produced a response: offline, DNS failure,
/// TLS failure, timeout. Distinct from [ApiException] because there is no
/// server verdict to act on and the request is safe to retry.
class NetworkException implements Exception {
  const NetworkException([this.message = 'ارتباط با سرور برقرار نشد.']);

  final String message;

  @override
  String toString() => 'NetworkException: $message';
}