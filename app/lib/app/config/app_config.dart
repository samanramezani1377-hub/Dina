/// Single source of truth for the Dina backend address.
///
/// Every Flutter API request is created from [apiRoot]. To point the entire
/// app at another backend, change only [apiBaseUrl] (or provide the
/// build-time `API_BASE_URL` define). No feature is allowed to own a server
/// URL of its own.
///
/// CI can therefore build the same app against a temporary E2E backend:
///
/// `flutter build apk --dart-define=API_BASE_URL=https://example.trycloudflare.com`
library;

abstract final class AppConfig {
  /// The backend origin only. Do not append `/api/v1` here.
  ///
  /// This is the only fallback server URL in the Flutter application.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://dina-api.onrender.com',
  );

  /// Root of every versioned API endpoint used by the application.
  static const String apiRoot = '$apiBaseUrl/api/v1';
}
