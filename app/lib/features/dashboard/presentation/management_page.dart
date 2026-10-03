import 'package:flutter/material.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';
import 'error_center_page.dart';

class ManagementPage extends StatefulWidget {
  const ManagementPage({required this.org, super.key});
  final String org;
  @override State<ManagementPage> createState()=>_ManagementPageState();
}
class _ManagementPageState extends State<ManagementPage> {
  Future<JsonMap?> subscription()=>AppScope.of(context).api.get('/organizations/'+widget.org+'/subscription');
  Future<JsonMap?> audit()=>AppScope.of(context).api.get('/organizations/'+widget.org+'/audit');
  String v(Object? x)=>x?.toString()??'—';
  @override Widget build(BuildContext context)=>ListView(padding:const EdgeInsets.all(20),children:[
    Text('مدیریت سازمان',style:Theme.of(context).textTheme.headlineSmall),
    const SizedBox(height:6),
    const Text('این بخش برای مالک و مدیر سازمان است؛ مجوز نهایی همیشه در Backend بررسی می‌شود.'),
    const SizedBox(height:16),
    FutureBuilder<JsonMap?>(future:subscription(),builder:(context,s){
      if(s.hasError)return _ErrorView(error:s.error.toString(),onRetry:()=>setState((){}));
      final x=s.data?['subscription'];
      final m=x is JsonMap?x:<String,Object?>{};
      return Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[
        Text('اشتراک',style:Theme.of(context).textTheme.titleLarge),const SizedBox(height:8),
        Wrap(spacing:20,runSpacing:8,children:[_kv('پلن',v(m['plan'])),_kv('وضعیت',v(m['status'])),_kv('شروع',v(m['starts_at'])),_kv('پایان',v(m['ends_at']))]),
      ])));
    }),
    const SizedBox(height:12),
    Card(child:ListTile(
      leading:const Icon(Icons.history),title:const Text('رویدادهای حسابرسی'),
      subtitle:const Text('ثبت‌های تغییر سازمان، سند، پرداخت و اشتراک.'),
      trailing:const Icon(Icons.arrow_forward_ios),
      onTap:()=>showDialog<void>(context:context,builder:(ctx)=>_AuditDialog(future:audit())),
    )),
    Card(child:ListTile(
      leading:const Icon(Icons.bug_report_outlined),title:const Text('مرکز خطا'),
      subtitle:const Text('خطاهای فنی، شناسه پیگیری و traceback امن.'),
      trailing:const Icon(Icons.arrow_forward_ios),
      onTap:()=>Navigator.push(context,MaterialPageRoute(builder:(_)=>ErrorCenterPage(org:widget.org))),
    )),
  ]);
  Widget _kv(String k,String val)=>SizedBox(width:190,child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(k,style:const TextStyle(fontWeight:FontWeight.bold)),Text(val)]));
}
class _AuditDialog extends StatelessWidget{
  const _AuditDialog({required this.future});final Future<JsonMap?> future;
  String v(Object? x)=>x?.toString()??'—';
  @override Widget build(BuildContext context)=>AlertDialog(title:const Text('رویدادهای حسابرسی'),content:SizedBox(width:700,height:500,child:FutureBuilder<JsonMap?>(future:future,builder:(context,s){
    if(s.connectionState!=ConnectionState.done)return const Center(child:CircularProgressIndicator());
    if(s.hasError)return Text(s.error.toString());
    final raw=s.data?['items'];final items=raw is List?raw.whereType<JsonMap>().toList():<JsonMap>[];
    return ListView(children:[for(final x in items.reversed)ListTile(
      leading:const Icon(Icons.event_note),title:Text(v(x['action'])),subtitle:Text(v(x['occurred_at'])+' • '+v(x['entity'])+' #'+v(x['entity_id'])),
    )]);
  })),actions:[TextButton(onPressed:()=>Navigator.pop(context),child:const Text('بستن'))]);
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.error, required this.onRetry});
  final String error; final VoidCallback onRetry;
  @override Widget build(BuildContext context) => Center(child: Padding(
    padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
      const Icon(Icons.error_outline, size: 48), const SizedBox(height: 12),
      const Text('بارگذاری ناموفق بود'), Text(error, textAlign: TextAlign.center),
      const SizedBox(height: 12), FilledButton(onPressed: onRetry, child: const Text('تلاش دوباره')),
    ],
  )));
}
