import 'package:flutter/material.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';

String _s(Object? v)=>v?.toString()??'';
String _m(Object? v)=>_s(v).isEmpty?'0':_s(v);
int? _i(Object? v)=>v is int?v:int.tryParse(_s(v));

class DashboardHomePage extends StatefulWidget {
 const DashboardHomePage({required this.organizationName,required this.userLabel,super.key});
 final String organizationName,userLabel;
 @override State<DashboardHomePage> createState()=>_DashboardHomePageState();
}
class _DashboardHomePageState extends State<DashboardHomePage>{
 Future<JsonMap?> load(){final s=AppScope.of(context);final o=s.authController.selectedOrganizationId!;return s.api.get('/organizations/${o}/trial-balance');}
 @override Widget build(BuildContext c)=>FutureBuilder<JsonMap?>(future:load(),builder:(c,s){
  if(s.connectionState!=ConnectionState.done)return const Center(child:CircularProgressIndicator());
  if(s.hasError)return _ErrorView(error:s.error.toString(),retry:()=>setState((){}));
  final d=s.data??{};final t=d['totals'] is JsonMap?d['totals'] as JsonMap:{};
  return ListView(padding:const EdgeInsets.all(20),children:[
   Text(widget.organizationName,style:Theme.of(c).textTheme.headlineSmall),Text('خوش آمدید، ${widget.userLabel}'),
   const SizedBox(height:20),Wrap(spacing:12,runSpacing:12,children:[
    _Metric('جمع بدهکار',_m(t['debit_total'])),_Metric('جمع بستانکار',_m(t['credit_total'])),_Metric('اختلاف',_m(t['difference'])),_Metric('وضعیت',d['is_balanced']==true?'متوازن':'نیازمند بررسی')]),
  ]);
 });
}
class _Metric extends StatelessWidget{const _Metric(this.title,this.value);final String title,value;@override Widget build(BuildContext c)=>SizedBox(width:220,child:Card(child:Padding(padding:const EdgeInsets.all(16),child:Column(crossAxisAlignment:CrossAxisAlignment.start,children:[Text(title),const SizedBox(height:6),Text(value,style:Theme.of(c).textTheme.titleLarge)]))));}

class AccountingWorkspace extends StatefulWidget{const AccountingWorkspace({required this.destinationId,super.key});final String destinationId;@override State<AccountingWorkspace> createState()=>_AccountingWorkspaceState();}
class _AccountingWorkspaceState extends State<AccountingWorkspace>{int tick=0;void reload()=>setState(()=>tick++);@override Widget build(BuildContext c){final s=AppScope.of(c);final o=s.authController.selectedOrganizationId!;return KeyedSubtree(key:ValueKey(tick),child:switch(widget.destinationId){
 'chart-of-accounts'=>AccountsPage(org:o,onChanged:reload),'journal-entry'=>JournalsPage(org:o,onChanged:reload),'ledger'=>ReportPage(org:o,path:'ledger',title:'دفتر کل'),'trial-balance'=>ReportPage(org:o,path:'trial-balance',title:'تراز آزمایشی'),'customers'=>CustomersPage(org:o),'invoices'=>InvoicesPage(org:o,onChanged:reload),'payments'=>PaymentsPage(org:o,onChanged:reload),'settings'=>SettingsPage(org:o),_=>const SizedBox.shrink()});}}

class AccountsPage extends StatefulWidget{const AccountsPage({required this.org,required this.onChanged,super.key});final String org;final VoidCallback onChanged;@override State<AccountsPage> createState()=>_AccountsState();}
class _AccountsState extends State<AccountsPage>{final code=TextEditingController(),name=TextEditingController();String type='asset';
Future<JsonMap?> load()=>AppScope.of(context).api.get('/organizations/${widget.org}/accounts');
Future<void> add()async{try{await AppScope.of(context).api.post('/organizations/${widget.org}/accounts',body:{'code':code.text.trim(),'name':name.text.trim(),'account_type':type});code.clear();name.clear();widget.onChanged();}catch(e){if(mounted)_snack(context,e.toString());}}
@override Widget build(BuildContext c)=>_Frame(title:'سرفصل حساب‌ها',load:load,create:Wrap(spacing:10,runSpacing:10,children:[
 SizedBox(width:120,child:TextField(controller:code,decoration:const InputDecoration(labelText:'کد'))),SizedBox(width:220,child:TextField(controller:name,decoration:const InputDecoration(labelText:'نام'))),
 SizedBox(width:180,child:DropdownButtonFormField<String>(value:type,decoration:const InputDecoration(labelText:'نوع'),items:const[DropdownMenuItem(value:'asset',child:Text('دارایی')),DropdownMenuItem(value:'liability',child:Text('بدهی')),DropdownMenuItem(value:'equity',child:Text('حقوق مالکانه')),DropdownMenuItem(value:'revenue',child:Text('درآمد')),DropdownMenuItem(value:'expense',child:Text('هزینه'))],onChanged:(v)=>setState(()=>type=v??'asset'))),FilledButton(onPressed:add,child:const Text('افزودن'))]));}

class JournalsPage extends StatefulWidget{const JournalsPage({required this.org,required this.onChanged,super.key});final String org;final VoidCallback onChanged;@override State<JournalsPage> createState()=>_JournalsState();}
class _JournalsState extends State<JournalsPage>{final no=TextEditingController(),desc=TextEditingController(),date=TextEditingController(text:DateTime.now().toIso8601String().substring(0,10));final account=TextEditingController(),debit=TextEditingController(),credit=TextEditingController();
Future<void> save()async{try{await AppScope.of(context).api.post('/organizations/${widget.org}/journals',body:{'document_no':no.text,'description':desc.text,'entry_date':date.text,'lines':[{'account_id':int.parse(account.text),'debit':debit.text.isEmpty?'0':debit.text,'credit':credit.text.isEmpty?'0':credit.text}]});widget.onChanged();_snack(context,'سند ذخیره شد.');}catch(e){if(mounted)_snack(context,e.toString());}}
@override Widget build(BuildContext c)=>ListView(padding:const EdgeInsets.all(20),children:[Text('ثبت سند حسابداری',style:Theme.of(c).textTheme.headlineSmall),Card(child:Padding(padding:const EdgeInsets.all(14),child:Wrap(spacing:10,runSpacing:10,children:[
 SizedBox(width:140,child:TextField(controller:no,decoration:const InputDecoration(labelText:'شماره سند'))),SizedBox(width:240,child:TextField(controller:desc,decoration:const InputDecoration(labelText:'شرح'))),SizedBox(width:140,child:TextField(controller:date,decoration:const InputDecoration(labelText:'تاریخ'))),SizedBox(width:140,child:TextField(controller:account,decoration:const InputDecoration(labelText:'شناسه حساب'))),SizedBox(width:140,child:TextField(controller:debit,decoration:const InputDecoration(labelText:'بدهکار'))),SizedBox(width:140,child:TextField(controller:credit,decoration:const InputDecoration(labelText:'بستانکار'))),FilledButton(onPressed:save,child:const Text('ذخیره'))]))]);}

class ReportPage extends StatelessWidget{const ReportPage({required this.org,required this.path,required this.title,super.key});final String org,path,title;
@override Widget build(BuildContext c)=>_Frame(title:title,load:()=>AppScope.of(c).api.get('/organizations/${org}/${path}'),formatter:(d)=>[Card(child:ListTile(title:Text(d['is_balanced']==true?'متوازن':'وضعیت گزارش'),subtitle:Text(d['totals'] is JsonMap?d['totals'].toString():'بدهکار: ${_m(d['period_debit_total'])} | بستانکار: ${_m(d['period_credit_total'])}'))),for(final a in ((d['accounts'] as List?)?.whereType<JsonMap>()??[]))ListTile(title:Text('${_s(a['account_code'])} - ${_s(a['account_name'])}'),subtitle:Text('مانده: ${_m(a['closing_balance']??a['balance'])}'))]);}

class CustomersPage extends StatefulWidget{const CustomersPage({required this.org,super.key});final String org;@override State<CustomersPage> createState()=>_CustomersState();}
class _CustomersState extends State<CustomersPage>{final name=TextEditingController(),email=TextEditingController(),phone=TextEditingController();
Future<void> add()async{try{await AppScope.of(context).api.post('/organizations/${widget.org}/customers',body:{'name':name.text,'email':email.text.isEmpty?null:email.text,'phone':phone.text.isEmpty?null:phone.text});name.clear();email.clear();phone.clear();setState((){});}catch(e){if(mounted)_snack(context,e.toString());}}
@override Widget build(BuildContext c)=>_Frame(title:'مشتریان',load:()=>AppScope.of(c).api.get('/organizations/${widget.org}/customers'),create:Wrap(spacing:10,children:[SizedBox(width:220,child:TextField(controller:name,decoration:const InputDecoration(labelText:'نام'))),SizedBox(width:200,child:TextField(controller:email,decoration:const InputDecoration(labelText:'ایمیل'))),SizedBox(width:150,child:TextField(controller:phone,decoration:const InputDecoration(labelText:'تلفن'))),FilledButton(onPressed:add,child:const Text('افزودن'))]));}

class InvoicesPage extends StatefulWidget{const InvoicesPage({required this.org,required this.onChanged,super.key});final String org;final VoidCallback onChanged;@override State<InvoicesPage> createState()=>_InvoicesState();}
class _InvoicesState extends State<InvoicesPage>{final customer=TextEditingController(),no=TextEditingController(),total=TextEditingController(),date=TextEditingController(text:DateTime.now().toIso8601String().substring(0,10));
Future<void> add()async{try{await AppScope.of(context).api.post('/organizations/${widget.org}/invoices',body:{'customer_id':int.parse(customer.text),'invoice_no':no.text,'total':total.text,'issue_date':date.text});widget.onChanged();}catch(e){if(mounted)_snack(context,e.toString());}}
@override Widget build(BuildContext c)=>_Frame(title:'فاکتورها',load:()=>AppScope.of(c).api.get('/organizations/${widget.org}/invoices'),create:Wrap(spacing:10,children:[SizedBox(width:130,child:TextField(controller:customer,decoration:const InputDecoration(labelText:'شناسه مشتری'))),SizedBox(width:150,child:TextField(controller:no,decoration:const InputDecoration(labelText:'شماره'))),SizedBox(width:150,child:TextField(controller:total,decoration:const InputDecoration(labelText:'مبلغ'))),SizedBox(width:150,child:TextField(controller:date,decoration:const InputDecoration(labelText:'تاریخ'))),FilledButton(onPressed:add,child:const Text('ثبت'))]));}

class PaymentsPage extends StatefulWidget{const PaymentsPage({required this.org,required this.onChanged,super.key});final String org;final VoidCallback onChanged;@override State<PaymentsPage> createState()=>_PaymentsState();}
class _PaymentsState extends State<PaymentsPage>{final invoice=TextEditingController(),amount=TextEditingController(),method=TextEditingController(text:'other'),reference=TextEditingController();
Future<void> pay()async{try{await AppScope.of(context).api.post('/organizations/${widget.org}/invoices/${int.parse(invoice.text)}/payments',body:{'amount':amount.text,'method':method.text,'reference':reference.text.isEmpty?null:reference.text});widget.onChanged();}catch(e){if(mounted)_snack(context,e.toString());}}
@override Widget build(BuildContext c)=>ListView(padding:const EdgeInsets.all(20),children:[Text('ثبت پرداخت',style:Theme.of(c).textTheme.headlineSmall),Card(child:Padding(padding:const EdgeInsets.all(14),child:Wrap(spacing:10,children:[SizedBox(width:130,child:TextField(controller:invoice,decoration:const InputDecoration(labelText:'شناسه فاکتور'))),SizedBox(width:150,child:TextField(controller:amount,decoration:const InputDecoration(labelText:'مبلغ'))),SizedBox(width:140,child:TextField(controller:method,decoration:const InputDecoration(labelText:'روش'))),SizedBox(width:180,child:TextField(controller:reference,decoration:const InputDecoration(labelText:'مرجع'))),FilledButton(onPressed:pay,child:const Text('ثبت پرداخت'))]))]);}

class SettingsPage extends StatelessWidget{const SettingsPage({required this.org,super.key});final String org;
@override Widget build(BuildContext c)=>ListView(padding:const EdgeInsets.all(20),children:[Card(child:ListTile(title:const Text('سازمان فعال'),subtitle:Text(org))),Card(child:ListTile(title:const Text('اشتراک'),onTap:()async{final d=await AppScope.of(c).api.get('/organizations/${org}/subscription');if(c.mounted)showDialog(context:c,builder:(_)=>AlertDialog(title:const Text('اشتراک'),content:Text(_s(d?['subscription'])),actions:[TextButton(onPressed:()=>Navigator.pop(c),child:const Text('بستن'))]));}))]);}

class _Frame extends StatefulWidget{
 const _Frame({required this.title,required this.load,this.create,this.formatter});
 final String title; final Future<JsonMap?> Function() load; final Widget? create; final List<Widget> Function(JsonMap)? formatter;
 @override State<_Frame> createState()=>_FrameState();
}
class _FrameState extends State<_Frame>{
 Future<JsonMap?>? future;
 @override void initState(){super.initState();future=widget.load();}
 void retry()=>setState(()=>future=widget.load());
 @override Widget build(BuildContext c)=>FutureBuilder<JsonMap?>(future:future,builder:(c,s){
  if(s.connectionState!=ConnectionState.done)return const Center(child:CircularProgressIndicator());
  if(s.hasError)return _ErrorView(error:s.error.toString(),retry:retry);
  final d=s.data??{};final rows=widget.formatter?.call(d)??_rows(d);
  return ListView(padding:const EdgeInsets.all(20),children:[Text(widget.title,style:Theme.of(c).textTheme.headlineSmall),const SizedBox(height:12),if(widget.create!=null)Card(child:Padding(padding:const EdgeInsets.all(14),child:widget.create!)),const SizedBox(height:12),...rows]);
 });
 List<Widget> _rows(JsonMap d){final raw=d['items']??d['accounts'];final items=raw is List?raw.whereType<JsonMap>().toList():<JsonMap>[];if(items.isEmpty)return[const Card(child:ListTile(title:Text('داده‌ای ثبت نشده است.')))];return[for(final x in items)Card(child:ListTile(title:Text(_s(x['name']??x['invoice_no']??x['id'])),subtitle:Text(x.entries.take(5).map((e)=>e.key + ': ' + _s(e.value)).join(' | ')))];}
}

class _ErrorView extends StatelessWidget{const _ErrorView({required this.error,required this.retry});final String error;final VoidCallback retry;@override Widget build(BuildContext c)=>Center(child:Padding(padding:const EdgeInsets.all(24),child:Column(mainAxisSize:MainAxisSize.min,children:[const Icon(Icons.error_outline,size:48),Text('بارگذاری ناموفق بود'),Text(error,textAlign:TextAlign.center),FilledButton(onPressed:retry,child:const Text('تلاش دوباره'))])));}
void _snack(BuildContext c,String m)=>ScaffoldMessenger.of(c).showSnackBar(SnackBar(content:Text(m)));
