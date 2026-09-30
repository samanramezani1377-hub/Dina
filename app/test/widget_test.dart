import 'package:dina_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('renders the Dina shell with the Persian title', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const DinaApp());

    expect(find.text('دینا'), findsWidgets);
    expect(find.byType(AppBar), findsOneWidget);
    expect(find.byType(MaterialApp), findsOneWidget);
  });

  testWidgets('disables the debug banner', (WidgetTester tester) async {
    await tester.pumpWidget(const DinaApp());

    final MaterialApp app = tester.widget<MaterialApp>(
      find.byType(MaterialApp),
    );
    expect(app.debugShowCheckedModeBanner, isFalse);
  });
}
