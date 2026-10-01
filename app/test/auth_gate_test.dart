import 'package:dina_app/app/app.dart';
import 'package:dina_app/app/storage/key_value_store.dart';
import 'package:dina_app/features/auth/domain/auth_status.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_transport.dart';
import 'support/fixtures.dart';

void main() {
  group('auth gate routing', () {
    testWidgets('while the session is being restored the login form is never shown', (
      WidgetTester tester,
    ) async {
      // The answer is genuinely in flight, which is the only way to observe the
      // unknown state. A test that simply started signed-out could not tell a
      // correct gate from one that flashes the login form and then corrects
      // itself.
      final FakeTransport transport = FakeTransport()..holdResponses = true;
      final InMemoryKeyValueStore store = InMemoryKeyValueStore(
        <String, String>{
          'dina.session.access_token': 'persisted-token',
          'dina.session.user':
              '{"id":"u-1","email":"a@b.co","display_name":"کاربر"}',
          'dina.session.organization_id': 'org-1',
        },
      );
      transport
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      final DinaAppDependencies dependencies = buildDinaAppDependencies(
        store: store,
        transport: transport,
        baseUrl: 'http://api.test/api/v1',
      );
      await tester.binding.setSurfaceSize(const Size(420, 900));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(DinaApp(dependencies: dependencies));
      await tester.pump();

      // The stored session exists, so the app is mid-restore: no login form, no
      // organization list, no shell — just the unknown state.
      expect(dependencies.authController.status.isResolving, isTrue);
      expect(find.byType(TextFormField), findsNothing);
      expect(find.text('انتخاب سازمان'), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      transport
        ..holdResponses = false
        ..releaseHeldResponses();
      await tester.pumpAndSettle();

      // The restore succeeded, so the shell opens without the login form ever
      // having been on screen.
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
      expect(find.byType(TextFormField), findsNothing);
    });

    testWidgets('signed out shows the login form and neither navigation surface', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport();
      await tester.pumpDina(transport: transport);

      expect(find.text('برای ورود به حساب کاربری، اطلاعات زیر را وارد کنید.'), findsOneWidget);
      expect(find.byType(TextFormField), findsNWidgets(2));
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
      expect(find.byKey(const ValueKey<String>('wide-navigation')), findsNothing);
    });

    testWidgets('a session with no organization choice routes to organization selection', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      expect(find.text('انتخاب سازمان'), findsOneWidget);
      expect(find.text('شرکت الف'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
    });

    testWidgets('a session with a valid organization choice routes to the shell', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
          'dina.session.organization_id': 'org-1',
        }),
      );

      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
      expect(find.text('شرکت الف'), findsWidgets);
    });

    testWidgets('a stored organization the user is no longer a member of is rejected', (
      WidgetTester tester,
    ) async {
      // The stored id is a claim from a previous run, not an authorization. The
      // shell must not open on it.
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsWithIds(<String, String>{'org-7': 'شرکت الف'}),
        );

      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
        'dina.session.organization_id': 'org-1',
      });
      await tester.pumpDina(transport: transport, store: store);

      expect(find.text('انتخاب سازمان'), findsOneWidget);
      expect(find.text('شرکت الف'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
      expect(await store.read('dina.session.organization_id'), isNull);
    });

    testWidgets('a failed entitlement check does not open the shell', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        .on('GET', '/api/v1/organizations', FakeResponse.networkFailure());

      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
        'dina.session.organization_id': 'org-1',
      });
      await tester.pumpDina(transport: transport, store: store);

      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
      expect(find.text('ادامه کار ممکن نشد'), findsOneWidget);
      // The claim is not discarded on a transient failure; the user retries.
      expect(await store.read('dina.session.organization_id'), 'org-1');
    });

    testWidgets('the restored token is presented on the very first request', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      await tester.pumpDina(
        transport: transport,
        store: InMemoryKeyValueStore(<String, String>{
          'dina.session.access_token': 'persisted-token',
        }),
      );

      // Cold start resolves the session before it can build a request, so the
      // first request must already carry the token. A header that is empty here
      // would look like a signed-out user to the server.
      //
      // Compared through a helper that reports only whether it matched: an
      // equality assertion on the header prints the token into the failure
      // output of a CI log.
      expect(
        transport.requestFor('GET', '/api/v1/auth/me').carriesBearerToken(
          'persisted-token',
        ),
        isTrue,
        reason: 'the very first /auth/me request must present the restored token',
      );
      expect(
        transport.requestFor(
          'GET',
          '/api/v1/organizations',
        ).carriesBearerToken('persisted-token'),
        isTrue,
        reason: 'every request after the first must keep presenting the token',
      );
    });

    testWidgets('a rejected token is discarded and the user is signed out', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/auth/me',
        FakeResponse.error('token_expired', 'نشست منقضی شده است.', statusCode: 401),
      );

      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'stale-token',
        'dina.session.organization_id': 'org-1',
      });
      await tester.pumpDina(transport: transport, store: store);

      expect(find.byType(TextFormField), findsNWidgets(2));
      expect(await store.read('dina.session.access_token'), isNull);
      expect(await store.read('dina.session.organization_id'), isNull);
    });

    testWidgets('a rejected sign-in stays on the login form and shows the backend message', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport().on(
        'POST',
        '/api/v1/auth/login',
        FakeResponse.error(
          'invalid_credentials',
          'ایمیل یا گذرواژه نادرست است.',
          statusCode: 401,
        ),
      );

      await tester.pumpDina(transport: transport);
      await signIn(tester, password: 'wrong');

      expect(find.text('ایمیل یا گذرواژه نادرست است.'), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
    });

    testWidgets('logging out clears the token, the tenant and returns to login', (
      WidgetTester tester,
    ) async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', userJson())
        ..onJson(
          'GET',
          '/api/v1/organizations',
          organizationsJson(<String>['شرکت الف']),
        );

      final InMemoryKeyValueStore store = InMemoryKeyValueStore(<String, String>{
        'dina.session.access_token': 'persisted-token',
        'dina.session.organization_id': 'org-1',
      });
      await tester.pumpDina(transport: transport, store: store);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );

      await tester.tap(find.byTooltip('خروج از حساب'));
      await tester.pumpAndSettle();

      expect(find.byType(TextFormField), findsNWidgets(2));
      expect(await store.read('dina.session.access_token'), isNull);
      expect(await store.read('dina.session.organization_id'), isNull);
    });
  });
}
