import 'package:flutter/foundation.dart';

import '../../../app/api/api_exception.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/organization_repository.dart';
import '../domain/organization.dart';

/// The states the organization screen can be in.
///
/// [error] is deliberately a separate state from [empty]. A caller who is not
/// entitled to see the list, or whose request failed, must be told so — the
/// client never turns "we could not confirm" into "you have nothing".
enum OrganizationListStatus { initial, loading, loaded, empty, error }

/// Loads the caller's organizations and records the chosen one.
class OrganizationController extends ChangeNotifier {
  OrganizationController({
    required OrganizationRepository repository,
    required AuthController authController,
  }) : _repository = repository,
       _authController = authController;

  final OrganizationRepository _repository;
  final AuthController _authController;

  OrganizationListStatus _status = OrganizationListStatus.initial;
  OrganizationListStatus get status => _status;

  List<Organization> _organizations = const <Organization>[];
  List<Organization> get organizations => _organizations;

  String? _errorMessage;
  String? get errorMessage => _errorMessage;

  /// Membership result of the most recent successful load, kept so the shell
  /// can confirm a persisted selection without a second round trip.
  bool _loadedOnce = false;
  bool get loadedOnce => _loadedOnce;

  bool contains(String organizationId) =>
      _organizations.any((Organization o) => o.id == organizationId);

  /// Fetches the membership list. Any failure ends in [OrganizationListStatus.error].
  Future<void> load() async {
    _status = OrganizationListStatus.loading;
    _errorMessage = null;
    notifyListeners();
    try {
      final List<Organization> result = await _repository.listMine();
      _organizations = result;
      _loadedOnce = true;
      _status = result.isEmpty
          ? OrganizationListStatus.empty
          : OrganizationListStatus.loaded;
    } on ApiException catch (error) {
      _fail(error.message);
    } on NetworkException catch (error) {
      _fail(error.message);
    } on FormatException {
      _fail('فهرست سازمان‌ها از سرور قابل خواندن نبود.');
    }
    notifyListeners();
  }

  void _fail(String message) {
    // The previously known list is dropped rather than kept on screen: showing
    // stale memberships after a failed refresh would imply the server
    // confirmed them.
    _organizations = const <Organization>[];
    _loadedOnce = false;
    _errorMessage = message;
    _status = OrganizationListStatus.error;
  }

  /// Persists the choice, then only then lets the shell in. The write happens
  /// first: a selection that is not on disk would not survive a restart, and
  /// opening the shell without it would claim a persistence that does not exist.
  Future<void> select(String organizationId) async {
    await _repository.saveSelection(organizationId);
    _authController.selectOrganization(organizationId);
  }

  /// Forgets the tenant choice so the shell cannot be reopened with it.
  Future<void> clearSelection() => _repository.clearSelection();
}