import 'dart:async';
import 'dart:convert';

import 'package:dina_app/app/api/api_client.dart';

/// A scripted HTTP transport: it answers from a routing table instead of a
/// socket, so tests exercise the real client, the real repositories and the real
/// widgets while never touching the network.
class FakeTransport implements HttpTransport {
  FakeTransport();

  /// Every request the client made, in order.
  final List<RecordedRequest> requests = <RecordedRequest>[];

  /// Responses keyed by `"<METHOD> <path>"`.
  final Map<String, FakeResponse> _responses = <String, FakeResponse>{};

  /// Fallback for any path with no scripted response.
  FakeResponse fallback = const FakeResponse(
    statusCode: 404,
    bodyText: '{"error":{"code":"not_found","message":"یافت نشد."}}',
  );

  /// When true, requests are held open until [releaseHeldResponses] is called.
  /// This is how a test observes the app while an answer is genuinely in
  /// flight, rather than faking the absence of an answer.
  bool holdResponses = false;

  final List<_HeldRequest> _held = <_HeldRequest>[];

  /// Lets every held request finish with the response that was scripted for it.
  void releaseHeldResponses() {
    final List<_HeldRequest> pending = List<_HeldRequest>.of(_held);
    _held.clear();
    for (final _HeldRequest held in pending) {
      if (!held.completer.isCompleted) {
        held.completer.complete(
          HttpTextResponse(
            statusCode: held.response.statusCode,
            body: held.response.bodyText,
          ),
        );
      }
    }
  }

  bool closed = false;

  FakeTransport on(
    String method,
    String path,
    FakeResponse response,
  ) {
    _responses['$method $path'] = response;
    return this;
  }

  FakeTransport onJson(
    String method,
    String path,
    Object body, {
    int statusCode = 200,
  }) {
    return on(
      method,
      path,
      FakeResponse.jsonBody(body, statusCode: statusCode),
    );
  }

  RecordedRequest requestFor(String method, String path) => requests.firstWhere(
    (RecordedRequest r) => r.method == method && r.path == path,
    orElse: () => throw StateError('No $method $path request was made.'),
  );

  bool hasRequest(String method, String path) => requests.any(
    (RecordedRequest r) => r.method == method && r.path == path,
  );

  @override
  Future<HttpTextResponse> send({
    required String method,
    required Uri url,
    Map<String, String> headers = const <String, String>{},
    String? body,
  }) async {
    final String path = url.path;
    requests.add(
      RecordedRequest(
        method: method,
        url: url,
        path: path,
        headers: Map<String, String>.of(headers),
        body: body,
      ),
    );
    final FakeResponse? scripted = _responses['$method $path'];
    final FakeResponse response = scripted ?? fallback;
    if (holdResponses) {
      final _HeldRequest held = _HeldRequest(response: response);
      _held.add(held);
      return held.completer.future;
    }
    if (response.throws) {
      throw response.exception!;
    }
    return HttpTextResponse(
      statusCode: response.statusCode,
      body: response.bodyText,
    );
  }

  @override
  void close() {
    closed = true;
  }
}

class RecordedRequest {
  RecordedRequest({
    required this.method,
    required this.url,
    required this.path,
    required this.headers,
    required this.body,
  });

  final String method;
  final Uri url;
  final String path;
  final Map<String, String> headers;
  final String? body;

  String? get authorization => headers['authorization'];

  /// Whether this request presented exactly `Bearer <expected>`.
  ///
  /// Returns a bool rather than the header so a failing `expect` cannot print
  /// the credential into the test output.
  bool carriesBearerToken(String expected) =>
      headers['authorization'] == 'Bearer $expected';

  Map<String, Object?> get jsonBody =>
      (body == null || body!.isEmpty) ? <String, Object?>{} : jsonDecode(body!) as Map<String, Object?>;
}

/// A scripted response, including the ability to fail below the HTTP layer.
class FakeResponse {
  const FakeResponse({
    required this.statusCode,
    this.bodyText = '',
    this.throws = false,
    this.exception,
  });

  final int statusCode;
  final String bodyText;

  /// When true the transport throws instead of answering, modelling a dead
  /// connection.
  final bool throws;
  final Object? exception;

  factory FakeResponse.jsonBody(Object value, {int statusCode = 200}) =>
      FakeResponse(statusCode: statusCode, bodyText: jsonEncode(value));

  factory FakeResponse.networkFailure() => const FakeResponse(
    statusCode: 0,
    bodyText: '',
    throws: true,
    exception: _FakeSocketException(),
  );

  factory FakeResponse.error(
    String code,
    String message, {
    int statusCode = 400,
  }) => FakeResponse.jsonBody(<String, Object?>{
    'error': <String, Object?>{'code': code, 'message': message},
  }, statusCode: statusCode);
}

class _FakeSocketException implements Exception {
  const _FakeSocketException();
}

class _HeldRequest {
  _HeldRequest({required this.response});

  final Completer<HttpTextResponse> completer = Completer<HttpTextResponse>();
  final FakeResponse response;
}
