import 'dart:convert';

import '../../../app/storage/key_value_store.dart';

/// The signed-in user as the client needs it.
class AuthenticatedUser {
  const AuthenticatedUser({
    required this.id,
    required this.email,
    this.displayName,
  });

  final String id;
  final String email;
  final String? displayName;

  String get label => (displayName != null && displayName!.trim().isNotEmpty)
      ? displayName!
      : email;

  Map<String, Object?> toJson() => <String, Object?>{
    'id': id,
    'email': email,
    if (displayName != null) 'display_name': displayName,
  };

  static AuthenticatedUser fromJson(Map<String, Object?> json) {
    final Object? id = json['id'];
    final Object? email = json['email'];
    if (id is! String || id.isEmpty || email is! String || email.isEmpty) {
      throw const FormatException('پاسخ سرور برای کاربر معتبر نیست.');
    }
    return AuthenticatedUser(
      id: id,
      email: email,
      displayName: json['display_name'] as String?,
    );
  }
}

/// An access token plus the user it belongs to.
class Session {
  const Session({required this.accessToken, required this.user});

  final String accessToken;
  final AuthenticatedUser user;
}

/// Owns every persisted credential fragment and the one selected organization.
///
/// Persistence is deliberately split in two: the token says *who* the user is,
/// the selected organization says *which tenant* the shell is scoped to. Logging
/// out must drop both, otherwise a restart would silently re-enter a tenant the
/// user never re-authorised.
class SessionStore {
  SessionStore(this._store);

  static const String accessTokenKey = 'dina.session.access_token';
  static const String userKey = 'dina.session.user';
  static const String organizationIdKey = 'dina.session.organization_id';

  final KeyValueStore _store;

  /// The token the HTTP layer must present, held synchronously because building
  /// a request header cannot await the disk.
  ///
  /// It is set the moment a token is read or written, which is what makes the
  /// very first authenticated request — `/auth/me` on a cold start — carry the
  /// token that was restored. A header that could be stale or empty is worse
  /// than no abstraction at all.
  String? _activeToken;
  String? get activeToken => _activeToken;

  void setActiveToken(String? token) {
    _activeToken = (token == null || token.isEmpty) ? null : token;
  }

  Future<void> saveSession(Session session) async {
    setActiveToken(session.accessToken);
    await _store.write(accessTokenKey, session.accessToken);
    await _store.write(userKey, jsonEncode(session.user.toJson()));
  }

  Future<String?> readAccessToken() => _store.read(accessTokenKey);

  Future<AuthenticatedUser?> readUser() async {
    final String? raw = await _store.read(userKey);
    if (raw == null) {
      return null;
    }
    try {
      final Object? decoded = jsonDecode(raw);
      if (decoded is Map<String, Object?>) {
        return AuthenticatedUser.fromJson(decoded);
      }
    } on FormatException {
      // A corrupt record is treated as "no session" rather than crashing the
      // boot path; the caller falls back to the signed-out tree.
      return null;
    }
    return null;
  }

  Future<void> saveSelectedOrganization(String organizationId) =>
      _store.write(organizationIdKey, organizationId);

  Future<String?> readSelectedOrganizationId() =>
      _store.read(organizationIdKey);

  /// Drops only the tenant selection, keeping the user signed in so the
  /// organization screen can re-pick without a fresh login.
  Future<void> clearSelectedOrganization() =>
      _store.delete(organizationIdKey);

  /// Drops every credential fragment. Nothing about the previous session may
  /// survive a logout.
  Future<void> clearAll() async {
    setActiveToken(null);
    await _store.delete(accessTokenKey);
    await _store.delete(userKey);
    await _store.delete(organizationIdKey);
  }
}