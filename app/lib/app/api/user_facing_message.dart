import 'api_exception.dart';

/// Turns any failure raised below the presentation layer into one Persian
/// sentence that is safe to show a user.
///
/// Nothing is ever swallowed: an unrecognised failure still becomes a message,
/// it just never becomes an empty result or a fake success.
String userFacingMessage(Object error) {
  if (error is ApiException) {
    return error.message;
  }
  if (error is NetworkException) {
    return error.message;
  }
  if (error is FormatException) {
    return 'پاسخ سرور قابل خواندن نبود.';
  }
  return 'خطای غیرمنتظره‌ای رخ داد. دوباره تلاش کنید.';
}