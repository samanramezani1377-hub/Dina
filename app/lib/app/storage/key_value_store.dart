import 'package:shared_preferences/shared_preferences.dart';

/// Minimal persistence contract the feature layer depends on.
///
/// Presentation and domain code never import a storage package directly, which
/// is what lets tests run against [InMemoryKeyValueStore] and what keeps the
/// choice of backend swappable.
abstract interface class KeyValueStore {
  Future<String?> read(String key);

  Future<void> write(String key, String value);

  Future<void> delete(String key);
}

/// Persistent store used by the running app.
class SharedPreferencesKeyValueStore implements KeyValueStore {
  SharedPreferencesKeyValueStore._(this._preferences);

  static Future<SharedPreferencesKeyValueStore> open() async {
    return SharedPreferencesKeyValueStore._(
      await SharedPreferences.getInstance(),
    );
  }

  final SharedPreferences _preferences;

  @override
  Future<String?> read(String key) async => _preferences.getString(key);

  @override
  Future<void> write(String key, String value) async {
    await _preferences.setString(key, value);
  }

  @override
  Future<void> delete(String key) async {
    await _preferences.remove(key);
  }
}

/// In-memory store for tests and for the "no platform bindings" case.
class InMemoryKeyValueStore implements KeyValueStore {
  InMemoryKeyValueStore([Map<String, String>? seed])
    : _values = <String, String>{...?seed};

  final Map<String, String> _values;

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}