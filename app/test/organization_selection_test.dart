import 'package:dina_app/app/app.dart';
import 'package:dina_app/app/storage/key_value_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_transport.dart';
import 'support/fixtures.dart';

/// Signs in through the real UI and returns a transport already authenticated
/// and past the organization choice.
Future<DinaAppDependencies> pumpSignedIn(
  WidgetTester tester, {
  required FakeTransport transport,
  InMemoryKeyValueStore? store,
  Size surfaceSize = const Size(420, 900),
}) async {
  final InMemoryKeyValueStore resolvedStore =
      store ??
      InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
        'dina.session.organization_id': 'org-1',
      });
  transport
    ..onJson('GET', '/api/v1/auth/me', userJson())
    ..onJson(
      'GET',
      '/api/v1/organizations',
      organizationsJson(<String>['شرکت الف', 'شرکت ب']),
    );
  return tester.pumpDina(
    transport: transport,
    store: resolvedStore,
    surfaceSize: surfaceSize,
  );
}

void main() {
  group('organization selection', () {
    testWidgets('renders one row per organization the server returned', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport();
      await pumpSignedIn(tester, transport: transport, store: InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
      }));

      expect(find.text('انتخاب سازمان'), findsOneWidget);
      expect(find.text('شرکت الف'), findsOneWidget);
      expect(find.text('شرکت ب'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('organization-org-1')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('organization-org-2')),
        findsOneWidget,
      );
      expect(transport.hasRequest('GET', '/api/v1/organizations'), isTrue);
    });

    testWidgets('shows an empty state, not an error, when membership is empty', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson('GET', '/api/v1/organizations', organizationsJson(<String>[]));

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      expect(find.text('سازمانی در دسترس نیست'), findsOneWidget);
      expect(find.text('دریافت سازمان‌ها ناموفق بود'), findsNothing);
      expect(find.byType(ListTile), findsNothing);
    });

    testWidgets('a forbidden list is an error state, never an empty state', (
      WidgetTester tester,
    ) async {
      // This is the case the spec calls out: a response the user is not
      // entitled to must not be rendered as if it were an empty membership.
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        .on(
          'GET',
          '/api/v1/organizations',
          FakeResponse.error(
            'permission_denied',
            'شما به فهرست سازمان‌ها دسترسی ندارید.',
            statusCode: 403,
          ),
        );

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      expect(find.text('دریافت سازمان‌ها ناموفق بود'), findsOneWidget);
      expect(find.text('شما به فهرست سازمان‌ها دسترسی ندارید.'), findsOneWidget);
      expect(find.text('سازمانی در دسترس نیست'), findsNothing);
      expect(find.byType(ListTile), findsNothing);
    });

    testWidgets('a network failure is an error state with a working retry', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        .on('GET', '/api/v1/organizations', FakeResponse.networkFailure());

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      expect(find.text('دریافت سازمان‌ها ناموفق بود'), findsOneWidget);
      expect(find.text('سازمانی در دسترس نیست'), findsNothing);

      transport.onJson(
        'GET',
        '/api/v1/organizations',
        organizationsJson(<String>['شرکت ج']),
      );
      await tester.tap(find.text('تلاش دوباره'));
      await tester.pumpAndSettle();

      expect(find.text('شرکت ج'), findsOneWidget);
      expect(find.text('دریافت سازمان‌ها ناموفق بود'), findsNothing);
    });

    testWidgets('a list that is not shaped like a list is an error, not an empty state', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        .onJson('GET', '/api/v1/organizations', <String, Object?>{'nope': 1});

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      expect(find.text('دریافت سازمان‌ها ناموفق بود'), findsOneWidget);
      expect(find.text('سازمانی در دسترس نیست'), findsNothing);
    });
  });

  group('selection persistence', () {
    testWidgets('a chosen organization survives a restart without re-picking', (
      WidgetTester tester,
    ) async {
      final InMemoryKeyValueStore store = InMemoryKeyValueStore();
      final FakeTransport transport = FakeTransport()
        ..onJson('POST', '/api/v1/auth/login', authJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف', 'شرکت ب']),
        );

      await tester.pumpDina(
        transport: transport,
        store: store,
        appKey: const ValueKey<String>('first-app'),
      );
      await signIn(tester);
      await tester.tap(find.text('شرکت ب'));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );

      // Restart: a brand new controller graph over the same storage, as a fresh
      // process would build. Nothing is carried over in memory.
      final FakeTransport restarted = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف', 'شرکت ب']),
        );
      await tester.pumpDina(
        transport: restarted,
        store: store,
        appKey: const ValueKey<String>('restarted-app'),
      );

      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
      expect(find.text('انتخاب سازمان'), findsNothing);
      expect(find.text('شرکت ب'), findsWidgets);
      // The persisted choice is the one that was made, not merely any choice.
      expect(await store.read('dina.session.organization_id'), 'org-2');
    });

    testWidgets('a fresh sign-in does not inherit the previous tenant selection', (
      WidgetTester tester,
    ) async {
      // A tenant id left behind by a previous session, with no token: the app
      // opens signed out, and the next sign-in must not inherit that pick.
      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.organization_id': 'org-9',
      });
      final FakeTransport transport = FakeTransport()
        ..onJson('POST', '/api/v1/auth/login', authJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      await tester.pumpDina(transport: transport, store: store);
      await signIn(tester);

      // The new credentials get their own tenant choice.
      expect(find.text('انتخاب سازمان'), findsOneWidget);
      expect(await store.read('dina.session.organization_id'), isNull);
      expect(await store.read('dina.session.access_token'), 'token-1');
    });

    testWidgets('changing organization returns to selection and clears the pick', (
      WidgetTester tester,
    ) async {
      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
        'dina.session.organization_id': 'org-1',
      });
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف', 'شرکت ب']),
        );

      await tester.pumpDina(transport: transport, store: store);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );

      await tester.tap(find.byTooltip('تغییر سازمان'));
      await tester.pumpAndSettle();

      expect(find.text('انتخاب سازمان'), findsOneWidget);
      expect(await store.read('dina.session.organization_id'), 'org-1');
    });
  });
}