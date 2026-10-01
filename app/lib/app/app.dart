import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

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

/// Composition root of the client.
///
/// Everything the app depends on is constructed here and injected downwards. The
/// wiring is a pure function of its arguments, so a test hands it a fake
/// transport and an in-memory store and gets the real application, not a
/// parallel one built for testing.
DinaAppDependencies buildDinaAppDependencies({
  required KeyValueStore store,
  required HttpTransport transport,
  String baseUrl = AppConfig.apiRoot,
}) {
  final SessionStore sessionStore = SessionStore(store);
  final ApiClient api = ApiClient(
    baseUrl: baseUrl,
    transport: transport,
    tokenProvider: () => sessionStore.activeToken,
  );
  final AuthController authController = AuthController(
    AuthRepository(api: AuthApi(api), sessionStore: sessionStore),
  );
  return DinaAppDependencies(
    authController: authController,
    organizationController: OrganizationController(
      repository: OrganizationRepository(
        api: OrganizationApi(api),
        sessionStore: sessionStore,
      ),
      authController: authController,
    ),
    transport: transport,
  );
}

class DinaAppDependencies {
  DinaAppDependencies({
    required this.authController,
    required this.organizationController,
    required HttpTransport transport,
  }) : _transport = transport;

  final AuthController authController;
  final OrganizationController organizationController;

  final HttpTransport _transport;

  void dispose() {
    authController.dispose();
    organizationController.dispose();
    _transport.close();
  }
}

/// The application widget.
class DinaApp extends StatefulWidget {
  const DinaApp({required this.dependencies, super.key});

  final DinaAppDependencies dependencies;

  @override
  State<DinaApp> createState() => _DinaAppState();
}

class _DinaAppState extends State<DinaApp> {
  @override
  void initState() {
    super.initState();
    _resolveSession();
  }

  @override
  void didUpdateWidget(DinaApp oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A new dependency graph means a new session store and a new API client;
    // carrying the old answer over would be exactly the stale state the gate
    // exists to prevent.
    if (!identical(oldWidget.dependencies, widget.dependencies)) {
      _resolveSession();
    }
  }

  void _resolveSession() {
    widget.dependencies.authController.restore();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      authController: widget.dependencies.authController,
      organizationController: widget.dependencies.organizationController,
      child: MaterialApp(
        title: 'دینا',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        locale: AppTheme.locale,
        supportedLocales: AppTheme.supportedLocales,
        localizationsDelegates: const <LocalizationsDelegate<Object?>>[
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        home: const AuthGate(),
      ),
    );
  }
}