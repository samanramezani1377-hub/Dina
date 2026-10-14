import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

typedef JsonMap = Map<String, Object?>;

abstract interface class HttpTransport {
  Future<HttpTextResponse> send({
    required String method,
    required Uri url,
    Map<String, String> headers = const {},
    String? body,
  });

  void close();
}

class HttpTextResponse {
  const HttpTextResponse({required this.statusCode, required this.body});

  final int statusCode;
  final String body;
}

class ApiClient {
  ApiClient({
    required String baseUrl,
    required HttpTransport transport,
    String? Function()? tokenProvider,
    Duration timeout = const Duration(seconds: 15),
  })  : baseUrl = _normalizeBaseUrl(baseUrl),
        _transport = transport,
        _tokenProvider = tokenProvider ?? (() => null),
        _timeout = timeout;

  final String baseUrl;
  final HttpTransport _transport;
  final String? Function() _tokenProvider;
  final Duration _timeout;

  /// Feature repositories pass endpoint paths; this client owns URL joining.
  static String _normalizeBaseUrl(String value) {
    final normalized = value.trim().replaceFirst(RegExp(r'/+$'), '');
    if (normalized.isEmpty) {
      throw ArgumentError.value(value, 'baseUrl', 'Backend URL cannot be empty.');
    }
    final uri = Uri.tryParse(normalized);
    if (uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty ||
        (uri.scheme != 'http' && uri.scheme != 'https')) {
      throw ArgumentError.value(
        value,
        'baseUrl',
        'Backend URL must be an absolute HTTP(S) URL.',
      );
    }
    return normalized;
  }

  Future<JsonMap?> get(String path, {Map<String, String>? query}) =>
      _send('GET', _withQuery(path, query));

  Future<JsonMap?> post(
    String path, {
    JsonMap? body,
    Map<String, String>? extraHeaders,
  }) =>
      _send('POST', path, body: body, extraHeaders: extraHeaders);

  Future<JsonMap?> put(String path, {JsonMap? body}) =>
      _send('PUT', path, body: body);

  Future<JsonMap?> patch(String path, {JsonMap? body}) =>
      _send('PATCH', path, body: body);

  Future<JsonMap?> delete(String path) => _send('DELETE', path);

  String _withQuery(String path, Map<String, String>? query) {
    if (query == null || query.isEmpty) return path;
    final uri = Uri.parse(path);
    return uri
        .replace(queryParameters: {...uri.queryParameters, ...query})
        .toString();
  }

  Uri _endpointUri(String path) {
    final endpoint = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$endpoint');
  }

  Future<JsonMap?> _send(
    String method,
    String path, {
    JsonMap? body,
    Map<String, String>? extraHeaders,
  }) async {
    final headers = <String, String>{'accept': 'application/json'};
    final token = _tokenProvider();
    if (token != null && token.isNotEmpty) {
      headers['authorization'] = 'Bearer $token';
    }
    if (body != null) headers['content-type'] = 'application/json';
    if (extraHeaders != null) headers.addAll(extraHeaders);

    late HttpTextResponse response;
    try {
      response = await _transport
          .send(
            method: method,
            url: _endpointUri(path),
            headers: headers,
            body: body == null ? null : jsonEncode(body),
          )
          .timeout(_timeout);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const NetworkException('درخواست بیش از حد طول کشید.');
    } catch (_) {
      throw const NetworkException();
    }

    Object? decoded;
    if (response.body.trim().isNotEmpty) {
      try {
        decoded = jsonDecode(response.body);
      } on FormatException {
        throw const ApiException(
          message: 'پاسخ سرور قابل خواندن نبود.',
          code: 'malformed_response',
        );
      }
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded is JsonMap ? decoded : <String, Object?>{};
    }

    String? code;
    String? message;
    Map<String, Object?> details = const {};
    if (decoded is JsonMap && decoded['error'] is JsonMap) {
      final error = decoded['error'] as JsonMap;
      code = error['code'] as String?;
      message = error['message'] as String?;
      if (error['details'] is JsonMap) {
        details = error['details'] as JsonMap;
      }
    }

    throw ApiException(
      message: message ??
          switch (response.statusCode) {
            400 || 422 => 'اطلاعات ارسالی معتبر نیست.',
            401 => 'نشست شما معتبر نیست. دوباره وارد شوید.',
            403 => 'شما به این بخش دسترسی ندارید.',
            404 => 'موردی یافت نشد.',
            409 => 'این اطلاعات قبلاً ثبت شده است.',
            >= 500 => 'خطایی در سرور رخ داد. دوباره تلاش کنید.',
            _ => 'درخواست ناموفق بود.',
          },
      code: code,
      statusCode: response.statusCode,
      details: details,
    );
  }
}

class PackageHttpTransport implements HttpTransport {
  PackageHttpTransport({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  bool _closed = false;

  @override
  Future<HttpTextResponse> send({
    required String method,
    required Uri url,
    Map<String, String> headers = const {},
    String? body,
  }) async {
    if (_closed) throw const NetworkException('اتصال بسته شده است.');
    final request = http.Request(method, url)..headers.addAll(headers);
    if (body != null) request.body = body;
    try {
      final streamed = await _client.send(request);
      final response = await http.Response.fromStream(streamed);
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
