import '../../auth/domain/session.dart';
import '../domain/organization.dart';
import 'organization_api.dart';

/// Reads the caller's memberships and records the chosen tenant.
class OrganizationRepository {
  OrganizationRepository({
    required OrganizationApi api,
    required SessionStore sessionStore,
  }) : _api = api,
       _sessionStore = sessionStore;

  final OrganizationApi _api;
  final SessionStore _sessionStore;

  Future<List<Organization>> listMine() => _api.listMine();

  /// Persists the pick before the shell is allowed to appear, so the choice
  /// survives a restart rather than a process crash.
  Future<void> saveSelection(String organizationId) =>
      _sessionStore.saveSelectedOrganization(organizationId);

  Future<void> clearSelection() => _sessionStore.clearSelectedOrganization();

  Future<String?> readSelection() =>
      _sessionStore.readSelectedOrganizationId();
}