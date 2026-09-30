import 'package:dina_app/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('DinaApp builds and shows the Dina app bar title', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const DinaApp());

    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.widgetWithText(AppBar, 'دینا'), findsOneWidget);
  });

  testWidgets('DinaApp shows the backend placeholder body', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const DinaApp());

    expect(find.text('دینا آماده اتصال به Backend است.'), findsOneWidget);
  });
}
