import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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

/// Production store: ordinary preferences plus OS-backed secure storage for credentials.
class SecureKeyValueStore implements KeyValueStore {
  SecureKeyValueStore._(this._preferences);
  static Future<SecureKeyValueStore> open() async => SecureKeyValueStore._(await SharedPreferences.getInstance());
  final SharedPreferences _preferences;
  final FlutterSecureStorage _secure = const FlutterSecureStorage();
  bool _secureKey(String key) => key.startsWith('dina.session.');
  @override Future<String?> read(String key) => _secureKey(key) ? _secure.read(key:key) : Future<String?>.value(_preferences.getString(key));
  @override Future<void> write(String key,String value) async { if(_secureKey(key)){await _secure.write(key:key,value:value);}else{await _preferences.setString(key,value);} }
  @override Future<void> delete(String key) async { if(_secureKey(key)){await _secure.delete(key: key);}else{await _preferences.remove(key);} }
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