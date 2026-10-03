import 'dart:convert';
import 'package:http/http.dart' as http;
import 'api_exception.dart';
typedef JsonMap = Map<String, Object?>;
abstract interface class HttpTransport {
  Future<HttpTextResponse> send({required String method, required Uri url, Map<String,String> headers = const {}, String? body});
  void close();
}
class HttpTextResponse { const HttpTextResponse({required this.statusCode, required this.body}); final int statusCode; final String body; }
class ApiClient {
  ApiClient({required this.baseUrl, required HttpTransport transport, String? Function()? tokenProvider, Duration timeout = const Duration(seconds:15)})
      : _transport=transport, _tokenProvider=tokenProvider ?? (()=>null), _timeout=timeout;
  final String baseUrl; final HttpTransport _transport; final String? Function() _tokenProvider; final Duration _timeout;
  Future<JsonMap?> get(String path)=>_send('GET',path);
  Future<JsonMap?> post(String path,{JsonMap? body})=>_send('POST',path,body:body);
  Future<JsonMap?> put(String path,{JsonMap? body})=>_send('PUT',path,body:body);
  Future<JsonMap?> patch(String path,{JsonMap? body})=>_send('PATCH',path,body:body);
  Future<JsonMap?> delete(String path)=>_send('DELETE',path);
  Future<JsonMap?> _send(String method,String path,{JsonMap? body}) async {
    final headers=<String,String>{'accept':'application/json'}; final token=_tokenProvider();
    if(token!=null&&token.isNotEmpty) headers['authorization']='Bearer $token';
    if(body!=null) headers['content-type']='application/json';
    final response=await _transport.send(method:method,url:Uri.parse('$baseUrl$path'),headers:headers,body:body==null?null:jsonEncode(body)).timeout(_timeout);
    Object? decoded;
    if(response.body.trim().isNotEmpty){try{decoded=jsonDecode(response.body);}on FormatException{throw const ApiException(message:'پاسخ سرور قابل خواندن نبود.',code:'malformed_response');}}
    if(response.statusCode>=200&&response.statusCode<300)return decoded is JsonMap?decoded:<String,Object?>{};
    String? code,message; Map<String,Object?> details=const {};
    if(decoded is JsonMap&&decoded['error'] is JsonMap){final e=decoded['error'] as JsonMap;code=e['code'] as String?;message=e['message'] as String?;if(e['details'] is JsonMap)details=e['details'] as JsonMap;}
    throw ApiException(message:message??switch(response.statusCode){400||422=>'اطلاعات ارسالی معتبر نیست.',401=>'نشست شما معتبر نیست. دوباره وارد شوید.',403=>'شما دسترسی ندارید.',404=>'موردی یافت نشد.',409=>'این اطلاعات قبلاً ثبت شده است.',>=500=>'خطای سرور.',_=>'درخواست ناموفق بود.'},code:code,statusCode:response.statusCode,details:details);
  }
}
class PackageHttpTransport implements HttpTransport {
  PackageHttpTransport({http.Client? client}):_client=client??http.Client();
  final http.Client _client; bool _closed=false;
  @override Future<HttpTextResponse> send({required String method,required Uri url,Map<String,String> headers=const {},String? body}) async {
    if(_closed)throw const NetworkException('اتصال بسته شده است.');
    final request=http.Request(method,url)..headers.addAll(headers); if(body!=null)request.body=body;
    try{final r=await _client.send(request);final x=await http.Response.fromStream(r);return HttpTextResponse(statusCode:x.statusCode,body:x.body);}on http.ClientException{throw const NetworkException();}
  }
  @override void close(){_closed=true;_client.close();}
}
