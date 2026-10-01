import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

/// Decoded JSON payload. The client speaks JSON only, so this is the one
/// shape every repository receives from the API layer.
typedef JsonMap = Map<String, Object?>;

/// A single HTTP exchange, expressed so the transport can be swapped out.
/// Implementations must throw [NetworkException] when no response arrived and
/// let [ApiClient] turn a non-2xx response into an [ApiException].
abstract interface class HttpTransport {
  Future<HttpTextResponse> send({
    required String method,
    required Uri url,
    Map<String, String> headers = const <String, String>{},
    String? body,
  });

  void close();
}

/// A raw response body plus its status code.
class HttpTextResponse {
  const HttpTextResponse({required this.statusCode, required this.body});

  final int statusCode;
  final String body;
}

/// The only place in the client that knows how to talk HTTP.
///
/// Responsibilities: attach the bearer token, decode JSON, and translate every
/// failure into the [ApiException] / [NetworkException] vocabulary. Repositories
/// above it deal exclusively in data and typed errors.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    required HttpTransport transport,
    String? Function()? tokenProvider,
    Duration timeout = const Duration(seconds: 15),
  }) : _transport = transport,
       _tokenProvider = tokenProvider ?? (() => null),
       _timeout = timeout;

  final String baseUrl;
  final HttpTransport _transport;
  final String? Function() _tokenProvider;
  final Duration _timeout;

  Future<JsonMap?> get(String path) => _send('GET', path);

  Future<JsonMap?> post(String path, {JsonMap? body}) =>
      _send('POST', path, body: body);

  Future<JsonMap?> _send(String method, String path, {JsonMap? body}) async {
    final headers = <String, String>{'accept': 'application/json'};
    final token = _tokenProvider();
    if (token != null && token.isNotEmpty) {
      headers['authorization'] = 'Bearer $token';
    }
    if (body != null) {
      headers['content-type'] = 'application/json';
    }

    final HttpTextResponse response;
    try {
      response = await _transport
          .send(
            method: method,
            url: Uri.parse('$baseUrl$path'),
            headers: headers,
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(_timeout);
    } on ApiException {
      rethrow;
    } catch (_) {
      throw const NetworkException();
    }

    final decoded = _decode(response.body);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded is JsonMap ? decoded : <String, Object?>{};
    }
    throw _errorFor(response.statusCode, decoded);
  }

  Object? _decode(String body) {
    if (body.trim().isEmpty) {
      return null;
    }
    try {
      return jsonDecode(body);
    } on FormatException {
      throw const ApiException(
        message: 'پاسخ سرور قابل خواندن نبود.',
        code: 'malformed_response',
      );
    }
  }

  ApiException _errorFor(int statusCode, Object? decoded) {
    // The backend contract is {"error": {"code", "message", "details"}}.
    // Anything else (a bare string, an HTML proxy page, an empty body) is
    // still surfaced as an error — never silently converted into empty data.
    String? code;
    String? message;
    Map<String, Object?> details = const <String, Object?>{};
    if (decoded is JsonMap) {
      final error = decoded['error'];
      if (error is JsonMap) {
        code = error['code'] as String?;
        message = error['message'] as String?;
        final rawDetails = error['details'];
        if (rawDetails is JsonMap) {
          details = rawDetails;
        }
      }
    }
    return ApiException(
      message: message ?? _defaultMessageFor(statusCode),
      code: code,
      statusCode: statusCode,
      details: details,
    );
  }

  String _defaultMessageFor(int statusCode) => switch (statusCode) {
    400 || 422 => 'اطلاعات ارسالی معتبر نیست.',
    401 => 'نشست شما معتبر نیست. دوباره وارد شوید.',
    403 => 'شما به این بخش دسترسی ندارید.',
    404 => 'موردی یافت نشد.',
    409 => 'این اطلاعات قبلاً ثبت شده است.',
    >= 500 => 'خطایی در سرور رخ داد. دوباره تلاش کنید.',
    _ => 'درخواست ناموفق بود.',
  };
}

/// Production transport backed by `package:http`.
class PackageHttpTransport implements HttpTransport {
  PackageHttpTransport({http.Client? client})
    : _client = client ?? http.Client();

  final http.Client _client;
  bool _closed = false;

  @override
  Future<HttpTextResponse> send({
    required String method,
    required Uri url,
    Map<String, String> headers = const <String, String>{},
    String? body,
  }) async {
    if (_closed) {
      throw const NetworkException('اتصال بسته شده است.');
    }
    final http.Request request = http.Request(method, url)
      ..headers.addAll(headers);
    if (body != null) {
      request.body = body;
    }
    try {
      final http.StreamedResponse streamed = await _client.send(request);
      final http.Response response = await http.Response.fromStream(streamed);
      return HttpTextResponse(
        statusCode: response.statusCode,
        body: response.body,
      );
    } on http.ClientException {
      throw const NetworkException();
    }
  }

  @override
  void close() {
    _closed = true;
    _client.close();
  }
}