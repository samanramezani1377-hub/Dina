import 'package:flutter/material.dart';

import 'app/api/api_client.dart';
import 'app/app.dart';
import 'app/config/app_config.dart';
import 'app/storage/key_value_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final KeyValueStore store = await SharedPreferencesKeyValueStore.open();
  runApp(
    DinaApp(
      dependencies: buildDinaAppDependencies(
        store: store,
        transport: PackageHttpTransport(),
        baseUrl: AppConfig.apiRoot,
      ),
    ),
  );
}