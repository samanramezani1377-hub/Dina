import 'package:dina_app/app/app.dart';
import 'package:dina_app/app/storage/key_value_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_transport.dart';

Map<String, Object?> userJson({String id = 'u-1', String email = 'a@b.co'}) =>
    <String, Object?>{
      'id': id,
      'email': email,
      'display_name': 'کاربر آزمایشی',
    };

Map<String, Object?> authJson({String token = 'token-1'}) => <String, Object?>{
  'access_token': token,
  'user': userJson(),
};

/// `organizationsJson` produces what the backend returns for
/// `GET /api/v1/organizations`: only the caller's memberships.
Map<String, Object?> organizationsJson(List<String> names) =>
    <String, Object?>{
      'organizations': <Object?>[
        for (int i = 0; i < names.length; i++)
          <String, Object?>{'id': 'org-${i + 1}', 'name': names[i]},
      ],
    };

/// Same, with explicit ids, for the cases where the id matters.
Map<String, Object?> trialBalanceJson() => <String, Object?>{
  'organization_id': 1,
  'is_balanced': true,
  'totals': <String, Object?>{
    'debit_total': '0.00',
    'credit_total': '0.00',
    'difference': '0.00',
  },
  'accounts': <Object?>[],
};

Map<String, Object?> organizationsWithIds(Map<String, String> byId) =>
    <String, Object?>{
      'organizations': <Object?>[
        for (final MapEntry<String, String> entry in byId.entries)
          <String, Object?>{'id': entry.key, 'name': entry.value},
      ],
    };

InMemoryKeyValueStore signedInStore({
  String token = 'persisted-token',
  String? organizationId = 'org-1',
}) => InMemoryKeyValueStore(<String, String>{
  'dina.session.access_token': token,
  if (organizationId != null) 'dina.session.organization_id': organizationId,
});

/// A transport that answers the two calls a restored, already-chosen session
/// makes.
FakeTransport authenticatedTransport({
  List<String> organizations = const <String>['شرکت الف', 'شرکت ب'],
}) => (FakeTransport()
      ..onJson('GET', '/api/v1/auth/me', userJson()))
    ..onJson('GET', '/api/v1/organizations', organizationsJson(organizations))
    ..onJson('GET', '/api/v1/organizations/org-1/trial-balance', <String,Object?>{
      'organization_id': 1, 'is_balanced': true,
      'totals': <String,Object?>{'debit_total':'0.00','credit_total':'0.00','difference':'0.00'},
      'accounts': <Object?>[],
    });

extension PumpDina on WidgetTester {
  /// Builds the real application over fakes and settles the cold start.
  ///
  /// [appKey] makes each pump a distinct element. Simulating a restart needs
  /// that: pumping the same widget type again would reuse the existing State and
  /// skip start-up, which is not what a restart does.
  Future<DinaAppDependencies> pumpDina({
    required FakeTransport transport,
    InMemoryKeyValueStore? store,
    Size surfaceSize = const Size(420, 900),
    Key? appKey,
  }) async {
    final InMemoryKeyValueStore resolvedStore = store ?? InMemoryKeyValueStore();
    final DinaAppDependencies dependencies = buildDinaAppDependencies(
      store: resolvedStore,
      transport: transport,
      baseUrl: 'http://api.test/api/v1',
    );
    await binding.setSurfaceSize(surfaceSize);
    addTearDown(() => binding.setSurfaceSize(null));
    await pumpWidget(DinaApp(key: appKey, dependencies: dependencies));
    await pumpAndSettle();
    return dependencies;
  }

  Finder get emailField => find.byKey(const ValueKey<String>('auth-email'));
  Finder get passwordField => find.byKey(const ValueKey<String>('auth-password'));
  Finder get submitButton => find.byKey(const ValueKey<String>('auth-submit'));
}

/// Types credentials and presses the primary action of the login form.
Future<void> signIn(WidgetTester tester, {String password = 'secret'}) async {
  await tester.enterText(tester.emailField, 'a@b.co');
  await tester.enterText(tester.passwordField, password);
  await tester.tap(tester.submitButton);
  await tester.pumpAndSettle();
}