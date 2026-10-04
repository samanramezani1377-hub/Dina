import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:forui/forui.dart';
import '../features/auth/data/auth_api.dart';
import '../features/auth/data/auth_repository.dart';
import '../features/auth/domain/session.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/organizations/data/organization_api.dart';
import '../features/organizations/data/organization_repository.dart';
import '../features/organizations/presentation/organization_controller.dart';
import 'api/api_client.dart';
import 'app_scope.dart';
import 'config/app_config.dart';
import 'routing/auth_gate.dart';
import 'storage/key_value_store.dart';
import 'theme/app_theme.dart';

DinaAppDependencies buildDinaAppDependencies({required KeyValueStore store, required HttpTransport transport, String baseUrl = AppConfig.apiRoot}) {
  final sessionStore = SessionStore(store);
  final api = ApiClient(baseUrl: baseUrl, transport: transport, tokenProvider: () => sessionStore.activeToken);
  final authController = AuthController(AuthRepository(api: AuthApi(api), sessionStore: sessionStore));
  return DinaAppDependencies(
    authController: authController,
    organizationController: OrganizationController(
      repository: OrganizationRepository(api: OrganizationApi(api), sessionStore: sessionStore),
      authController: authController,
    ),
    api: api,
    transport: transport,
  );
}
class DinaAppDependencies {
  DinaAppDependencies({required this.authController, required this.organizationController, required this.api, required HttpTransport transport}) : _transport = transport;
  final AuthController authController;
  final OrganizationController organizationController;
  final ApiClient api;
  final HttpTransport _transport;
  void dispose() { authController.dispose(); organizationController.dispose(); _transport.close(); }
}
class DinaApp extends StatefulWidget {
  const DinaApp({required this.dependencies, super.key});
  final DinaAppDependencies dependencies;
  @override State<DinaApp> createState() => _DinaAppState();
}
class _DinaAppState extends State<DinaApp> {
  @override void initState() { super.initState(); widget.dependencies.authController.restore(); }
  @override void didUpdateWidget(DinaApp oldWidget) { super.didUpdateWidget(oldWidget); if (!identical(oldWidget.dependencies, widget.dependencies)) widget.dependencies.authController.restore(); }
  @override Widget build(BuildContext context) => AppScope(
    authController: widget.dependencies.authController,
    organizationController: widget.dependencies.organizationController,
    api: widget.dependencies.api,
    child: MaterialApp(
      title: 'دینا', debugShowCheckedModeBanner: false,
      theme: AppTheme.light(), darkTheme: AppTheme.dark(), themeMode: ThemeMode.system,
      builder: (context, child) => Directionality(
        textDirection: TextDirection.rtl,
        child: FTheme(
          data: Theme.of(context).brightness == Brightness.dark ? AppTheme.foruiDark() : AppTheme.foruiLight(),
          child: child ?? const SizedBox.shrink(),
        ),
      ),
      locale: AppTheme.locale, supportedLocales: AppTheme.supportedLocales,
      localizationsDelegates: const <LocalizationsDelegate<Object?>>[
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        FLocalizations.delegate,
      ],
      home: const AuthGate(),
    ),
  );
}
