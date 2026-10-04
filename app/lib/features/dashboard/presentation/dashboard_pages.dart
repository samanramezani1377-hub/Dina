import 'package:flutter/material.dart';
import '../../../app/app_scope.dart';
import '../../../app/api/api_client.dart';
import 'error_center_page.dart';
import 'management_page.dart';
import 'platform_admin_page.dart';

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