/// The four roots the application shell can be in.
///
/// These are mutually exclusive and exhaustive: every frame the app renders,
/// the user is in exactly one of them. [restoring] exists so an already
/// authenticated user never sees the login screen flash on a cold start.
enum AuthStatus {
  /// Session state is not known yet — the app is reading persisted state and
  /// validating it against `/auth/me`. Nothing may be shown that assumes
  /// either answer.
  restoring,

  /// No usable session. The login tree is shown.
  signedOut,

  /// A valid session with no tenant chosen yet, or with a previously chosen
  /// tenant that is no longer selectable. The organization selection tree is
  /// shown.
  organizationSelectionRequired,

  /// A valid session with a chosen tenant. The dashboard shell is shown.
  ready,
}

extension AuthStatusX on AuthStatus {
  bool get isSignedIn =>
      this == AuthStatus.organizationSelectionRequired || this == AuthStatus.ready;

  bool get isResolving => this == AuthStatus.restoring;
}