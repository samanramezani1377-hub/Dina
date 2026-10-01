/// Build-time configuration for the Dina client.
///
/// The API base url is injected at build time so the same source tree can be
/// pointed at a local backend, staging or production without code edits:
///
/// ```
/// flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
/// ```
library;

abstract final class AppConfig {
  /// Default points at the loopback alias an Android emulator uses to reach a
  /// backend running on the developer machine.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Root of every versioned endpoint the client talks to.
  static const String apiRoot = '$apiBaseUrl/api/v1';
}