import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';

class ErrorCenterPage extends StatefulWidget {
  const ErrorCenterPage({required this.org, super.key});
  final String org;
  @override State<ErrorCenterPage> createState() => _ErrorCenterPageState();
}
class _ErrorCenterPageState extends State<ErrorCenterPage> {
  bool unresolvedOnly = false;
  String? code;
  late Future<JsonMap?> future;
  @override void initState() { super.initState(); future = load(); }
  Future<JsonMap?> load() => AppScope.of(context).api.get(
    '/organizations/${widget.org}/errors',
    query: {'limit': '200', 'unresolved_only': unresolvedOnly.toString(), if (code != null && code!.isNotEmpty) 'code': code!},
  );
  void reload() => setState(() => future = load());
  String v(Object? x) => x?.toString() ?? '—';
  String fullLog(JsonMap item) => [
    'DINA ERROR LOG',
    'ID: ${v(item['id'])}',
    'Correlation ID: ${v(item['correlation_id'])}',
    'Time: ${v(item['occurred_at'])}',
    'Level: ${v(item['level'])}',
    'Code: ${v(item['code'])}',
    'HTTP: ${v(item['http_status'])}',
    'Method: ${v(item['method'])}',
    'Path: ${v(item['path'])}',
    'User ID: ${v(item['user_id'])}',
    'Organization ID: ${v(item['organization_id'])}',
    'IP: ${v(item['ip_address'])}',
    'User Agent: ${v(item['user_agent'])}',
    'Details: ${v(item['details'])}',
    '',
    'Traceback:',
    v(item['traceback']),
  ].join('\n');
  Future<void> copy(JsonMap item) async {
    await Clipboard.setData(ClipboardData(text: fullLog(item)));
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('لاگ کامل کپی شد.')));
  }
  Future<void> resolve(JsonMap item) async {
    try {
      await AppScope.of(context).api.post('/organizations/${widget.org}/errors/${v(item['id'])}/resolve');
      reload();
    } catch (e) { if (mounted) showError(context, e); }
  }
  @override Widget build(BuildContext context) => FutureBuilder<JsonMap?>(
    future: future,
    builder: (context, snapshot) {
      if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
      if (snapshot.hasError) return _ErrorView(error: snapshot.error.toString(), onRetry: reload);
      final raw = snapshot.data?['items'];
      final items = raw is List ? raw.whereType<JsonMap>().toList() : <JsonMap>[];
      return ListView(padding: const EdgeInsets.all(20), children: [
        Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('مرکز خطا', style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4), const Text('خطاهای سرور با شناسه پیگیری، جزئیات و traceback امن.'),
          ])),
          IconButton(onPressed: reload, icon: const Icon(Icons.refresh), tooltip: 'به‌روزرسانی'),
        ]),
        const SizedBox(height: 16),
        Card(child: Padding(padding: const EdgeInsets.all(14), child: Wrap(spacing: 12, runSpacing: 12, children: [
          FilterChip(label: const Text('فقط حل‌نشده'), selected: unresolvedOnly, onSelected: (value) { unresolvedOnly = value; reload(); }),
          SizedBox(width: 240, child: TextField(
            decoration: const InputDecoration(labelText: 'کد خطا', prefixIcon: Icon(Icons.search)),
            onChanged: (value) => code = value.trim().isEmpty ? null : value.trim(),
            onSubmitted: (_) => reload(),
          )),
          FilledButton.icon(onPressed: reload, icon: const Icon(Icons.filter_alt_outlined), label: const Text('اعمال فیلتر')),
        ]))),
        const SizedBox(height: 12),
        if (items.isEmpty) const Card(child: Padding(padding: EdgeInsets.all(28), child: Center(child: Text('خطایی برای نمایش وجود ندارد.')))),
        for (final item in items) _ErrorCard(item: item, onCopy: () => copy(item), onResolve: item['resolved_at'] == null ? () => resolve(item) : null),
      ]);
    },
  );
}
class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.item, required this.onCopy, required this.onResolve});
  final JsonMap item; final VoidCallback onCopy; final VoidCallback? onResolve;
  String v(Object? x) => x?.toString() ?? '—';
  @override Widget build(BuildContext context) {
    final critical = v(item['level']) == 'critical';
    return Card(margin: const EdgeInsets.only(bottom: 10), child: ExpansionTile(
      leading: CircleAvatar(child: Icon(critical ? Icons.priority_high : Icons.error_outline)),
      title: Text('${v(item['code'])}  •  HTTP ${v(item['http_status'])}'),
      subtitle: Text('${v(item['occurred_at'])}  •  ${v(item['correlation_id'])}', maxLines: 2),
      childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      children: [
        SelectableText(v(item['message'])), const SizedBox(height: 8),
        _kv('مسیر', '${v(item['method'])} ${v(item['path'])}'),
        _kv('کاربر', v(item['user_id'])), _kv('سازمان', v(item['organization_id'])),
        _kv('IP', v(item['ip_address'])), _kv('جزئیات', v(item['details'])),
        if (v(item['traceback']) != '—') Container(width: double.infinity, constraints: const BoxConstraints(maxHeight: 360),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(12)),
          child: SingleChildScrollView(child: SelectableText(v(item['traceback']), style: const TextStyle(fontFamily: 'monospace')))),
        const SizedBox(height: 12),
        Wrap(spacing: 8, children: [
          OutlinedButton.icon(onPressed: onCopy, icon: const Icon(Icons.copy), label: const Text('کپی کامل لاگ')),
          if (onResolve != null) FilledButton.icon(onPressed: onResolve, icon: const Icon(Icons.check), label: const Text('حل‌شده')),
        ]),
      ],
    ));
  }
  Widget _kv(String key, String value) => Padding(padding: const EdgeInsets.symmetric(vertical: 3), child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
    SizedBox(width: 100, child: Text(key, style: const TextStyle(fontWeight: FontWeight.bold))),
    Expanded(child: SelectableText(value)),
  ]));
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
void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.toString())));
}
