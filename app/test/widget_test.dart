import 'package:dina_app/app/config/app_config.dart';
import 'package:dina_app/app/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fake_transport.dart';
import 'support/fixtures.dart';

/// The root widget and the build-time configuration.
///
/// This file must keep existing and keep passing. CI materialises the Android
/// platform files with `flutter create .`, and a test directory without this
/// file gets the framework's default counter test written back into the tree,
/// which does not compile against this app.
void main() {
  test('the app is configured for a Persian right-to-left locale', () {
    // Every versioned endpoint hangs off the configured base url.
    expect(AppConfig.apiRoot, '${AppConfig.apiBaseUrl}/api/v1');
    expect(AppTheme.locale.languageCode, 'fa');
    expect(AppTheme.locale.countryCode, 'IR');
    expect(AppTheme.supportedLocales, <Locale>[AppTheme.locale]);
  });

  testWidgets('DinaApp builds a Persian Material app rooted at the auth gate', (
    WidgetTester tester,
  ) async {
    await tester.pumpDina(transport: FakeTransport());

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(
      Directionality.of(tester.element(find.byType(Text).first)),
      TextDirection.rtl,
    );
  });

  testWidgets('the signed-out tree shows the product name and the login form', (
    WidgetTester tester,
  ) async {
    await tester.pumpDina(transport: FakeTransport());

    expect(find.text('دینا'), findsOneWidget);
    expect(tester.emailField, findsOneWidget);
    expect(tester.passwordField, findsOneWidget);
  });
}
