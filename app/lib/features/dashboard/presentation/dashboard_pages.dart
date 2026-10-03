import 'package:flutter/material.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';
import 'error_center_page.dart';
import 'management_page.dart';

String valueOf(Object? value) => value?.toString() ?? '';
String pathFor(String org, String tail) => '/organizations/$org/$tail';

class DashboardHomePage extends StatefulWidget {
  const DashboardHomePage({required this.organizationName, required this.userLabel, super.key});
  final String organizationName;
  final String userLabel;
  @override State<DashboardHomePage> createState() => _DashboardHomePageState();
}
class _DashboardHomePageState extends State<DashboardHomePage> {
  Future<JsonMap?> load() {
    final scope = AppScope.of(context);
    return scope.api.get(pathFor(scope.authController.selectedOrganizationId!, 'trial-balance'));
  }
  @override Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(widget.organizationName, style: Theme.of(context).textTheme.headlineSmall),
        Text('خوش آمدید، $widget.userLabel'),
        const SizedBox(height: 20),
        FutureBuilder<JsonMap?>(
          future: load(),
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()));
            }
            if (snapshot.hasError) {
              return ErrorView(error: snapshot.error.toString(), onRetry: () => setState(() {}));
            }
            final data = snapshot.data ?? <String,Object?>{};
            final totals = data['totals'] is JsonMap ? data['totals']! as JsonMap : <String,Object?>{};
            return Wrap(spacing: 12, runSpacing: 12, children: [
              MetricCard(title: 'جمع بدهکار', value: valueOf(totals['debit_total'])),
              MetricCard(title: 'جمع بستانکار', value: valueOf(totals['credit_total'])),
              MetricCard(title: 'اختلاف', value: valueOf(totals['difference'])),
              MetricCard(title: 'وضعیت', value: data['is_balanced'] == true ? 'متوازن' : 'نیازمند بررسی'),
            ]);
          },
        ),
      ],
    );
  }
}
class MetricCard extends StatelessWidget {
  const MetricCard({required this.title, required this.value, super.key});
  final String title; final String value;
  @override Widget build(BuildContext context) => SizedBox(width: 220, child: Card(child: Padding(
    padding: const EdgeInsets.all(16),
    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title), const SizedBox(height: 6), Text(value, style: Theme.of(context).textTheme.titleLarge),
    ]),
  )));
}

class AccountingWorkspace extends StatefulWidget {
  const AccountingWorkspace({required this.destinationId, super.key});
  final String destinationId;
  @override State<AccountingWorkspace> createState() => _AccountingWorkspaceState();
}
class _AccountingWorkspaceState extends State<AccountingWorkspace> {
  int reloadKey = 0;
  void reload() => setState(() => reloadKey++);
  @override Widget build(BuildContext context) {
    final org = AppScope.of(context).authController.selectedOrganizationId!;
    final Widget page = switch (widget.destinationId) {
      'chart-of-accounts' => AccountsPage(org: org, onChanged: reload),
      'journal-entry' => JournalsPage(org: org, onChanged: reload),
      'ledger' => ReportPage(org: org, path: 'ledger', title: 'دفتر کل'),
      'trial-balance' => ReportPage(org: org, path: 'trial-balance', title: 'تراز آزمایشی'),
      'reports' => ReportsPage(org: org),
      'customers' => CustomersPage(org: org),
      'suppliers' => OperationalListPage(org: org, path: 'suppliers', title: 'تأمین‌کنندگان'),
      'products' => OperationalListPage(org: org, path: 'products', title: 'کالا و خدمات'),
      'warehouses' => OperationalListPage(org: org, path: 'warehouses', title: 'انبارها'),
      'inventory' => OperationalListPage(org: org, path: 'stock', title: 'موجودی کالا'),
      'cash-accounts' => OperationalListPage(org: org, path: 'cash-accounts', title: 'صندوق و بانک'),
      'checks' => OperationalListPage(org: org, path: 'checks', title: 'چک‌ها'),
      'sales' => OperationalListPage(org: org, path: 'sales', title: 'فروش'),
      'purchases' => OperationalListPage(org: org, path: 'purchases', title: 'خرید'),
      'fiscal-years' => OperationalListPage(org: org, path: 'fiscal-years', title: 'سال مالی'),
      'invoices' => InvoicesPage(org: org, onChanged: reload),
      'payments' => PaymentsPage(org: org, onChanged: reload),
      'settings' => SettingsPage(org: org),
      'error-center' => ErrorCenterPage(org: org),
      'management' => ManagementPage(org: org),
      _ => const SizedBox.shrink(),
    };
    return KeyedSubtree(key: ValueKey<int>(reloadKey), child: page);
  }
}

class AccountsPage extends StatefulWidget {
  const AccountsPage({required this.org, required this.onChanged, super.key});
  final String org; final VoidCallback onChanged;
  @override State<AccountsPage> createState() => _AccountsPageState();
}
class _AccountsPageState extends State<AccountsPage> {
  final code = TextEditingController(); final name = TextEditingController(); String type = 'asset';
  Future<JsonMap?> load() => AppScope.of(context).api.get(pathFor(widget.org, 'accounts'));
  Future<void> add() async {
    if (code.text.trim().isEmpty || name.text.trim().isEmpty) return;
    try {
      await AppScope.of(context).api.post(pathFor(widget.org, 'accounts'), body: {
        'code': code.text.trim(), 'name': name.text.trim(), 'account_type': type,
      });
      if (!mounted) return;
      code.clear(); name.clear(); widget.onChanged();
    } catch (error) { if (mounted) showError(context, error); }
  }
  @override void dispose() { code.dispose(); name.dispose(); super.dispose(); }
  @override Widget build(BuildContext context) => DataFrame(
    title: 'سرفصل حساب‌ها', load: load,
    create: Wrap(spacing: 10, runSpacing: 10, children: [
      SizedBox(width: 120, child: TextField(controller: code, decoration: const InputDecoration(labelText: 'کد'))),
      SizedBox(width: 220, child: TextField(controller: name, decoration: const InputDecoration(labelText: 'نام'))),
      SizedBox(width: 180, child: DropdownButtonFormField<String>(
        value: type, decoration: const InputDecoration(labelText: 'نوع'),
        items: const [
          DropdownMenuItem(value: 'asset', child: Text('دارایی')),
          DropdownMenuItem(value: 'liability', child: Text('بدهی')),
          DropdownMenuItem(value: 'equity', child: Text('حقوق مالکانه')),
          DropdownMenuItem(value: 'revenue', child: Text('درآمد')),
          DropdownMenuItem(value: 'expense', child: Text('هزینه')),
        ],
        onChanged: (v) => setState(() => type = v ?? 'asset'),
      )),
      FilledButton(onPressed: add, child: const Text('افزودن')),
    ]),
  );
}

class JournalsPage extends StatefulWidget {
  const JournalsPage({required this.org, required this.onChanged, super.key});
  final String org; final VoidCallback onChanged;
  @override State<JournalsPage> createState() => _JournalsPageState();
}
class _JournalsPageState extends State<JournalsPage> {
  final no = TextEditingController();
  final desc = TextEditingController();
  final date = TextEditingController(text: DateTime.now().toIso8601String().substring(0, 10));
  final account = TextEditingController(); final debit = TextEditingController(); final credit = TextEditingController();
  Future<void> save() async {
    final accountId = int.tryParse(account.text.trim());
    if (accountId == null || no.text.trim().isEmpty) { showError(context, 'شماره سند و شناسه حساب را وارد کنید.'); return; }
    try {
      await AppScope.of(context).api.post(pathFor(widget.org, 'journals'), body: {
        'document_no': no.text.trim(), 'description': desc.text.trim(), 'entry_date': date.text.trim(),
        'lines': [{'account_id': accountId, 'debit': debit.text.trim().isEmpty ? '0' : debit.text.trim(), 'credit': credit.text.trim().isEmpty ? '0' : credit.text.trim()}],
      });
      if (!mounted) return; widget.onChanged();
    } catch (error) { if (mounted) showError(context, error); }
  }
  @override void dispose() { no.dispose(); desc.dispose(); date.dispose(); account.dispose(); debit.dispose(); credit.dispose(); super.dispose(); }
  @override Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(20), children: [
    Text('ثبت سند حسابداری', style: Theme.of(context).textTheme.headlineSmall),
    Card(child: Padding(padding: const EdgeInsets.all(14), child: Wrap(spacing: 10, runSpacing: 10, children: [
      SizedBox(width: 140, child: TextField(controller: no, decoration: const InputDecoration(labelText: 'شماره سند'))),
      SizedBox(width: 240, child: TextField(controller: desc, decoration: const InputDecoration(labelText: 'شرح'))),
      SizedBox(width: 140, child: TextField(controller: date, decoration: const InputDecoration(labelText: 'تاریخ'))),
      SizedBox(width: 140, child: TextField(controller: account, decoration: const InputDecoration(labelText: 'شناسه حساب'))),
      SizedBox(width: 140, child: TextField(controller: debit, decoration: const InputDecoration(labelText: 'بدهکار'))),
      SizedBox(width: 140, child: TextField(controller: credit, decoration: const InputDecoration(labelText: 'بستانکار'))),
      FilledButton(onPressed: save, child: const Text('ذخیره')),
    ]))),
  ]);
}

class ReportPage extends StatelessWidget {
  const ReportPage({required this.org, required this.path, required this.title, super.key});
  final String org; final String path; final String title;
  @override Widget build(BuildContext context) => DataFrame(
    title: title,
    load: () => AppScope.of(context).api.get(pathFor(org, path)),
    formatter: (data) {
      final raw = data['accounts'];
      final accounts = raw is List ? raw.whereType<JsonMap>() : <JsonMap>[];
      return [
        Card(child: ListTile(
          title: Text(data['is_balanced'] == true ? 'متوازن' : 'نیازمند بررسی'),
          subtitle: Text(data['totals'] is JsonMap ? valueOf(data['totals']) : 'گزارش حساب‌ها'),
        )),
        for (final account in accounts)
          ListTile(
            title: Text('${valueOf(account['account_code'])} - ${valueOf(account['account_name'])}'),
            subtitle: Text('مانده: ${valueOf(account['closing_balance'] ?? account['balance'])}'),
          ),
      ];
    },
  );
}

class OperationalListPage extends StatelessWidget {
  const OperationalListPage({required this.org,required this.path,required this.title,super.key});
  final String org,path,title;
  @override Widget build(BuildContext context)=>DataFrame(title:title,load:()=>AppScope.of(context).api.get(pathFor(org,path)));
}
class CustomersPage extends StatefulWidget {
  const CustomersPage({required this.org, super.key}); final String org;
  @override State<CustomersPage> createState() => _CustomersPageState();
}
class _CustomersPageState extends State<CustomersPage> {
  final name = TextEditingController(); final email = TextEditingController(); final phone = TextEditingController();
  Future<void> add() async {
    try {
      await AppScope.of(context).api.post(pathFor(widget.org, 'customers'), body: {
        'name': name.text.trim(), 'email': email.text.trim().isEmpty ? null : email.text.trim(), 'phone': phone.text.trim().isEmpty ? null : phone.text.trim(),
      });
      if (!mounted) return; name.clear(); email.clear(); phone.clear(); setState(() {});
    } catch (error) { if (mounted) showError(context, error); }
  }
  @override void dispose() { name.dispose(); email.dispose(); phone.dispose(); super.dispose(); }
  @override Widget build(BuildContext context) => DataFrame(
    title: 'مشتریان', load: () => AppScope.of(context).api.get(pathFor(widget.org, 'customers')),
    create: Wrap(spacing: 10, children: [
      SizedBox(width: 220, child: TextField(controller: name, decoration: const InputDecoration(labelText: 'نام'))),
      SizedBox(width: 200, child: TextField(controller: email, decoration: const InputDecoration(labelText: 'ایمیل'))),
      SizedBox(width: 150, child: TextField(controller: phone, decoration: const InputDecoration(labelText: 'تلفن'))),
      FilledButton(onPressed: add, child: const Text('افزودن')),
    ]),
  );
}

class InvoicesPage extends StatefulWidget {
  const InvoicesPage({required this.org, required this.onChanged, super.key});
  final String org; final VoidCallback onChanged;
  @override State<InvoicesPage> createState() => _InvoicesPageState();
}
class _InvoicesPageState extends State<InvoicesPage> {
  final customer = TextEditingController(); final no = TextEditingController(); final total = TextEditingController();
  final date = TextEditingController(text: DateTime.now().toIso8601String().substring(0, 10));
  Future<void> add() async {
    final customerId = int.tryParse(customer.text.trim());
    if (customerId == null) { showError(context, 'شناسه مشتری معتبر نیست.'); return; }
    try {
      await AppScope.of(context).api.post(pathFor(widget.org, 'invoices'), body: {
        'customer_id': customerId, 'invoice_no': no.text.trim(), 'total': total.text.trim(), 'issue_date': date.text.trim(),
      });
      if (!mounted) return; widget.onChanged();
    } catch (error) { if (mounted) showError(context, error); }
  }
  @override void dispose() { customer.dispose(); no.dispose(); total.dispose(); date.dispose(); super.dispose(); }
  @override Widget build(BuildContext context) => DataFrame(
    title: 'فاکتورها', load: () => AppScope.of(context).api.get(pathFor(widget.org, 'invoices')),
    create: Wrap(spacing: 10, runSpacing: 10, children: [
      SizedBox(width: 130, child: TextField(controller: customer, decoration: const InputDecoration(labelText: 'شناسه مشتری'))),
      SizedBox(width: 150, child: TextField(controller: no, decoration: const InputDecoration(labelText: 'شماره'))),
      SizedBox(width: 150, child: TextField(controller: total, decoration: const InputDecoration(labelText: 'مبلغ'))),
      SizedBox(width: 150, child: TextField(controller: date, decoration: const InputDecoration(labelText: 'تاریخ'))),
      FilledButton(onPressed: add, child: const Text('ثبت')),
    ]),
  );
}

class PaymentsPage extends StatefulWidget {
  const PaymentsPage({required this.org, required this.onChanged, super.key});
  final String org; final VoidCallback onChanged;
  @override State<PaymentsPage> createState() => _PaymentsPageState();
}
class _PaymentsPageState extends State<PaymentsPage> {
  final invoice = TextEditingController(); final amount = TextEditingController(); final method = TextEditingController(text: 'other'); final reference = TextEditingController();
  Future<void> pay() async {
    final invoiceId = int.tryParse(invoice.text.trim());
    if (invoiceId == null) { showError(context, 'شناسه فاکتور معتبر نیست.'); return; }
    try {
      await AppScope.of(context).api.post(pathFor(widget.org, 'invoices/$invoiceId/payments'), body: {
        'amount': amount.text.trim(), 'method': method.text.trim(), 'reference': reference.text.trim().isEmpty ? null : reference.text.trim(),
      }, extraHeaders: {'Idempotency-Key': 'dina-${DateTime.now().microsecondsSinceEpoch}'});
      if (!mounted) return; widget.onChanged();
    } catch (error) { if (mounted) showError(context, error); }
  }
  @override void dispose() { invoice.dispose(); amount.dispose(); method.dispose(); reference.dispose(); super.dispose(); }
  @override Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(20), children: [
    Text('ثبت پرداخت', style: Theme.of(context).textTheme.headlineSmall),
    Card(child: Padding(padding: const EdgeInsets.all(14), child: Wrap(spacing: 10, children: [
      SizedBox(width: 130, child: TextField(controller: invoice, decoration: const InputDecoration(labelText: 'شناسه فاکتور'))),
      SizedBox(width: 150, child: TextField(controller: amount, decoration: const InputDecoration(labelText: 'مبلغ'))),
      SizedBox(width: 140, child: TextField(controller: method, decoration: const InputDecoration(labelText: 'روش'))),
      SizedBox(width: 180, child: TextField(controller: reference, decoration: const InputDecoration(labelText: 'مرجع'))),
      FilledButton(onPressed: pay, child: const Text('ثبت پرداخت')),
    ]))),
  ]);
}


class ReportsPage extends StatelessWidget {
  const ReportsPage({required this.org, super.key});
  final String org;
  @override Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.all(20),
    children: [
      Text('گزارش‌های مالی', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 6),
      const Text('گزارش‌ها از داده‌های ثبت‌شده سرور ساخته می‌شوند و مقدار مالی قابل ویرایش در کلاینت ندارند.'),
      const SizedBox(height: 16),
      Wrap(spacing: 12, runSpacing: 12, children: [
        _ReportAction(title: 'دفتر کل', icon: Icons.menu_book_outlined, onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportPage(org: org, path: 'ledger', title: 'دفتر کل')))),
        _ReportAction(title: 'تراز آزمایشی', icon: Icons.balance_outlined, onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportPage(org: org, path: 'trial-balance', title: 'تراز آزمایشی')))),
      ]),
    ],
  );
}
class _ReportAction extends StatelessWidget {
  const _ReportAction({required this.title, required this.icon, required this.onTap});
  final String title; final IconData icon; final VoidCallback onTap;
  @override Widget build(BuildContext context) => SizedBox(width: 260, child: Card(
    child: InkWell(onTap: onTap, borderRadius: BorderRadius.circular(12), child: Padding(
      padding: const EdgeInsets.all(18), child: Row(children: [
        Icon(icon, size: 30), const SizedBox(width: 14), Expanded(child: Text(title, style: Theme.of(context).textTheme.titleMedium)), const Icon(Icons.arrow_forward_ios, size: 16),
      ]),
    )),
  ));
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({required this.org, super.key}); final String org;
  Future<void> showSubscription(BuildContext context) async {
    try {
      final data = await AppScope.of(context).api.get(pathFor(org, 'subscription'));
      if (!context.mounted) return;
      showDialog<void>(context: context, builder: (dialogContext) => AlertDialog(
        title: const Text('اشتراک'), content: Text(valueOf(data?['subscription'])),
        actions: [TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('بستن'))],
      ));
    } catch (error) { if (context.mounted) showError(context, error); }
  }
  @override Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(20), children: [
    Card(child: ListTile(title: const Text('سازمان فعال'), subtitle: Text(org))),
    Card(child: ListTile(title: const Text('اشتراک'), subtitle: const Text('وضعیت اشتراک از سرور خوانده می‌شود.'), onTap: () => showSubscription(context))),
    const Card(child: ListTile(title: Text('امنیت'), subtitle: Text('احراز هویت و tenant isolation در Backend اعمال می‌شوند.'))),
  ]);
}

class DataFrame extends StatefulWidget {
  const DataFrame({required this.title, required this.load, this.create, this.formatter, super.key});
  final String title; final Future<JsonMap?> Function() load; final Widget? create; final List<Widget> Function(JsonMap)? formatter;
  @override State<DataFrame> createState() => _DataFrameState();
}
class _DataFrameState extends State<DataFrame> {
  late Future<JsonMap?> future;
  @override void initState() { super.initState(); future = widget.load(); }
  void retry() => setState(() => future = widget.load());
  @override Widget build(BuildContext context) => FutureBuilder<JsonMap?>(
    future: future,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
      if (snapshot.hasError) return ErrorView(error: snapshot.error.toString(), onRetry: retry);
      final data = snapshot.data ?? <String,Object?>{};
      final rows = widget.formatter?.call(data) ?? defaultRows(data);
      return ListView(padding: const EdgeInsets.all(20), children: [
        Text(widget.title, style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 12),
        if (widget.create != null) Card(child: Padding(padding: const EdgeInsets.all(14), child: widget.create!)),
        const SizedBox(height: 12),
        ...rows,
      ]);
    },
  );
  List<Widget> defaultRows(JsonMap data) {
    final raw = data['items'] ?? data['accounts'];
    final items = raw is List ? raw.whereType<JsonMap>() : <JsonMap>[];
    if (items.isEmpty) return const [Card(child: ListTile(title: Text('داده‌ای ثبت نشده است.')))];
    return [for (final item in items) Card(child: ListTile(
      title: Text(valueOf(item['name'] ?? item['invoice_no'] ?? item['id'])),
      subtitle: Text(item.entries.take(5).map((e) => '${e.key}: ${valueOf(e.value)}').join(' | ')),
    ))];
  }
}
class ErrorView extends StatelessWidget {
  const ErrorView({required this.error, required this.onRetry, super.key});
  final String error; final VoidCallback onRetry;
  @override Widget build(BuildContext context) => Center(child: Padding(padding: const EdgeInsets.all(24), child: Column(mainAxisSize: MainAxisSize.min, children: [
    const Icon(Icons.error_outline, size: 48), const SizedBox(height: 12), const Text('بارگذاری ناموفق بود'),
    Text(error, textAlign: TextAlign.center), const SizedBox(height: 12), FilledButton(onPressed: onRetry, child: const Text('تلاش دوباره')),
  ])));
}
void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
}
