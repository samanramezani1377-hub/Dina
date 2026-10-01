import '../../../../app/api/api_client.dart';
import '../../../../app/api/api_exception.dart';
import '../domain/organization.dart';

/// HTTP surface for the tenant list.
class OrganizationApi {
  const OrganizationApi(this._client);

  final ApiClient _client;

  /// Fetches the organizations the caller is a member of.
  ///
  /// Throws [ApiException] or [NetworkException]; it never returns an empty
  /// list to stand in for a failure. A caller that cannot prove entitlement
  /// must not be able to render anything as if it had.
  Future<List<Organization>> listMine() async {
    final JsonMap? body = await _client.get('/organizations');
    final Object? raw = body?['organizations'] ?? body?['items'] ?? body;
    if (raw is! List) {
      throw const ApiException(
        message: 'فهرست سازمان‌ها از سرور قابل خواندن نبود.',
        code: 'malformed_response',
      );
    }
    return raw.map((Object? entry) {
      if (entry is! Map<String, Object?>) {
        throw const ApiException(
          message: 'یکی از سازمان‌های دریافتی معتبر نیست.',
          code: 'malformed_response',
        );
      }
      try {
        return Organization.fromJson(entry);
      } on FormatException catch (error) {
        throw ApiException(message: error.message, code: 'malformed_response');
      }
    }).toList(growable: false);
  }
}
