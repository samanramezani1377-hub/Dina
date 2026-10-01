import 'package:dina_app/app/api/api_client.dart';
import 'package:dina_app/app/api/api_exception.dart';
import 'package:dina_app/app/api/user_facing_message.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_transport.dart';

/// The error vocabulary the whole client is built on.
///
/// These tests exist because every repository above [ApiClient] promises that a
/// failure is never rendered as an empty result. That promise is only true if
/// the translation below is right, so each guard is asserted directly rather
/// than inferred from a screen that happens to show an error.
void main() {
  ApiClient clientFor(
    FakeTransport transport, {
    String? token,
    Duration timeout = const Duration(seconds: 15),
  }) => ApiClient(
    baseUrl: 'http://api.test/api/v1',
    transport: transport,
    tokenProvider: () => token,
    timeout: timeout,
  );

  group('the bearer token is attached only when one exists', () {
    test('a request with a token carries an Authorization header', () async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', <String, Object?>{'id': 'u-1'});
      await clientFor(transport, token: 'tok').get('/auth/me');

      expect(transport.requests.single.headers['authorization'], isNotNull);
    });

    // Asserted on presence, never on the value: an equality assertion on a
    // header prints the token into the failure output.
    test('a request without a token carries no Authorization header', () async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', <String, Object?>{'id': 'u-1'});
      await clientFor(transport).get('/auth/me');

      expect(transport.requests.single.headers.containsKey('authorization'), isFalse);
    });

    test('an empty token is treated as no token at all', () async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', <String, Object?>{'id': 'u-1'});
      await clientFor(transport, token: '').get('/auth/me');

      // A header of "Bearer " with nothing after it is worse than none: it looks
      // authenticated to a log reader and rejects the request server-side.
      expect(transport.requests.single.headers.containsKey('authorization'), isFalse);
    });

    test('the full url is the configured base plus the path', () async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/auth/me', <String, Object?>{'id': 'u-1'});
      await clientFor(transport).get('/auth/me');

      expect(
        transport.requests.single.url.toString(),
        'http://api.test/api/v1/auth/me',
      );
    });
  });

  group('a 2xx response is decoded as JSON', () {
    test('an object body is returned as a map', () async {
      final FakeTransport transport = FakeTransport()
        ..onJson('GET', '/api/v1/thing', <String, Object?>{'a': 1});
      expect(await clientFor(transport).get('/thing'), <String, Object?>{'a': 1});
    });

    // Documents the current contract rather than endorsing it: the client is a
    // JSON-object API, so a 2xx list becomes an empty map here. Every repository
    // above re-validates the shape it needs and raises malformed_response, which
    // is what stops the empty map from reaching a screen as real data. The
    // repositories' own shape tests are in organization_selection_test.dart.
    test('a JSON list on a 2xx decodes to an empty map at this layer', () async {
      final FakeTransport transport = FakeTransport()
        ..on('GET', '/api/v1/thing', FakeResponse.jsonBody(<Object?>[1, 2]));
      expect(await clientFor(transport).get('/thing'), <String, Object?>{});
    });

    test('an empty body on a 2xx is an empty map, not an error', () async {
      final FakeTransport transport = FakeTransport()
        ..on('GET', '/api/v1/thing', const FakeResponse(statusCode: 200));
      expect(await clientFor(transport).get('/thing'), <String, Object?>{});
    });

    test('a body that is not JSON at all is an error, not empty data', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        const FakeResponse(statusCode: 200, bodyText: '<html>hello</html>'),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>().having(
            (ApiException e) => e.code,
            'code',
            'malformed_response',
          ),
        ),
      );
    });
  });

  group('a non-2xx response is always an error', () {
    test('a well formed envelope keeps the backend code and message', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        FakeResponse.error(
          'permission_denied',
          'شما به این بخش دسترسی ندارید.',
          statusCode: 403,
        ),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>()
              .having((ApiException e) => e.code, 'code', 'permission_denied')
              .having(
                (ApiException e) => e.message,
                'message',
                'شما به این بخش دسترسی ندارید.',
              )
              .having((ApiException e) => e.statusCode, 'statusCode', 403),
        ),
      );
    });

    test('details from the envelope are carried through', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        const FakeResponse(
          statusCode: 422,
          bodyText:
              '{"error":{"code":"validation_error","message":"بد است.",'
              '"details":{"field":"email"}}}',
        ),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>().having(
            (ApiException e) => e.details,
            'details',
            containsPair('field', 'email'),
          ),
        ),
      );
    });

    // The critical case: a proxy or a crash page is a failure, and rendering it
    // as "you have no organizations" would be a lie the user cannot detect.
    //
    // The body is decoded before the status is considered, so an HTML page
    // surfaces as malformed_response and the 502 does not survive onto the
    // exception. That ordering is what the assertion below pins: whatever the
    // cause, the caller gets an ApiException with a readable message and never a
    // successful empty map.
    test('an HTML error page is an error, never empty data', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        const FakeResponse(
          statusCode: 502,
          bodyText: '<html><body>502 Bad Gateway</body></html>',
        ),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>()
              .having((ApiException e) => e.code, 'code', 'malformed_response')
              .having((ApiException e) => e.message, 'message', isNotEmpty),
        ),
      );
    });

    // The same page, this time with a JSON body, so decoding succeeds and the
    // status alone has to drive the failure.
    test('a JSON error body with a server status is an error', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        FakeResponse.jsonBody(
          <String, Object?>{'error': 'upstream unavailable'},
          statusCode: 503,
        ),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>()
              .having((ApiException e) => e.statusCode, 'statusCode', 503)
              .having((ApiException e) => e.code, 'code', isNull)
              .having((ApiException e) => e.message, 'message', isNotEmpty),
        ),
      );
    });

    test('an empty error body is an error, never empty data', () async {
      final FakeTransport transport = FakeTransport()
        ..on('GET', '/api/v1/thing', const FakeResponse(statusCode: 500));

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(isA<ApiException>().having((ApiException e) => e.message, 'message', isNotEmpty)),
      );
    });

    test('an envelope with no code still produces a usable message', () async {
      final FakeTransport transport = FakeTransport().on(
        'GET',
        '/api/v1/thing',
        const FakeResponse(statusCode: 403, bodyText: '{"error":{}}'),
      );

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<ApiException>()
              .having((ApiException e) => e.code, 'code', isNull)
              .having((ApiException e) => e.message, 'message', isNotEmpty),
        ),
      );
    });
  });

  group('a status without a backend message still gets Persian text', () {
    // Each of these is a distinct guard in the default-message table. Removing
    // one must leave the user reading a blank screen, so each is asserted.
    const Map<int, String> defaults = <int, String>{
      400: 'اطلاعات ارسالی معتبر نیست.',
      422: 'اطلاعات ارسالی معتبر نیست.',
      401: 'نشست شما معتبر نیست. دوباره وارد شوید.',
      403: 'شما به این بخش دسترسی ندارید.',
      404: 'موردی یافت نشد.',
      409: 'این اطلاعات قبلاً ثبت شده است.',
      500: 'خطایی در سرور رخ داد. دوباره تلاش کنید.',
      503: 'خطایی در سرور رخ داد. دوباره تلاش کنید.',
      418: 'درخواست ناموفق بود.',
    };

    for (final MapEntry<int, String> entry in defaults.entries) {
      test('status ${entry.key} maps to a message that is not empty', () async {
        final FakeTransport transport = FakeTransport()
          ..on('GET', '/api/v1/thing', FakeResponse(statusCode: entry.key));

        await expectLater(
          clientFor(transport).get('/thing'),
          throwsA(
            isA<ApiException>().having(
              (ApiException e) => e.message,
              'message',
              entry.value,
            ),
          ),
        );
      });
    }
  });

  group('only an unusable session may drop the stored token', () {
    test('a 401 is session invalid whatever the code says', () {
      expect(const ApiException(message: 'x', statusCode: 401).isSessionInvalid, isTrue);
    });

    test('an expired token code is session invalid without a 401', () {
      // A gateway that answers 419 or 400 with token_expired still means the
      // token is dead. Treating it as retryable would keep retrying forever.
      expect(
        const ApiException(message: 'x', code: ApiErrorCode.tokenExpired).isSessionInvalid,
        isTrue,
      );
    });

    test('an invalid token code is session invalid', () {
      expect(
        const ApiException(message: 'x', code: ApiErrorCode.tokenInvalid).isSessionInvalid,
        isTrue,
      );
    });

    // The guard on the guard: a permission failure must never sign the user out
    // and destroy a token that is still perfectly good.
    test('a permission failure is not session invalid', () {
      expect(
        const ApiException(
          message: 'x',
          code: ApiErrorCode.permissionDenied,
          statusCode: 403,
        ).isSessionInvalid,
        isFalse,
      );
    });

    test('a validation failure is not session invalid', () {
      expect(
        const ApiException(
          message: 'x',
          code: ApiErrorCode.validationError,
          statusCode: 422,
        ).isSessionInvalid,
        isFalse,
      );
    });

    test('a server error is not session invalid', () {
      expect(const ApiException(message: 'x', statusCode: 500).isSessionInvalid, isFalse);
    });

    // A NetworkException deliberately has no isSessionInvalid: there is no
    // server verdict to act on. The repository keeps the token and shows a
    // retry, which is covered in auth_gate_test.dart.
    test('a NetworkException exposes no session verdict at all', () {
      const Object error = NetworkException();
      expect(error is ApiException, isFalse);
    });
  });

  group('a request that never got an answer is a NetworkException', () {
    test('a dead connection is a network failure, not an API error', () async {
      final FakeTransport transport = FakeTransport()
        ..on('GET', '/api/v1/thing', FakeResponse.networkFailure());

      await expectLater(
        clientFor(transport).get('/thing'),
        throwsA(
          isA<NetworkException>().having(
            (NetworkException e) => e.message,
            'message',
            isNotEmpty,
          ),
        ),
      );
    });

    test('a hung request times out as a network failure', () async {
      // Held open and never released, so only the client's own timeout can
      // end this call. Without the timeout the future would never complete and
      // the test would hang instead of failing.
      final FakeTransport transport = FakeTransport()..holdResponses = true;
      transport.onJson('GET', '/api/v1/thing', <String, Object?>{'a': 1});

      await expectLater(
        clientFor(
          transport,
          timeout: const Duration(milliseconds: 50),
        ).get('/thing'),
        throwsA(isA<NetworkException>()),
      );
    });
  });

  group('every failure becomes something a user can read', () {
    test('an API error shows the backend message', () {
      expect(
        userFacingMessage(const ApiException(message: 'پیام سرور')),
        'پیام سرور',
      );
    });

    test('a network error shows the network message', () {
      expect(
        userFacingMessage(const NetworkException('قطعی')),
        'قطعی',
      );
    });

    test('a format error becomes Persian text rather than leaking English', () {
      final String message = userFacingMessage(
        const FormatException('Unexpected character'),
      );
      expect(message, 'پاسخ سرور قابل خواندن نبود.');
    });

    // Nothing may be swallowed: an error the client does not recognise still
    // becomes a sentence, never an empty string that renders as a blank screen.
    test('an unrecognised error still becomes a non-empty sentence', () {
      final String message = userFacingMessage(StateError('boom'));
      expect(message, isNotEmpty);
      expect(message, isNot(contains('boom')));
    });

    test('a plain string error does not leak through verbatim', () {
      expect(userFacingMessage('raw'), isNot('raw'));
    });
  });
}
