import 'package:dina_app/features/dashboard/domain/shell_destinations_v3.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support/fixtures.dart';

const Size _phone = Size(420, 900);
const Size _desktop = Size(1400, 900);
const Size _desktopNarrow = Size(880, 900);

void main() {
  group('responsive shell', () {
    testWidgets('a narrow window uses the bottom bar and no side panel', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _phone,
      );

      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey<String>('wide-navigation')), findsNothing);
      expect(find.byTooltip('خروج از حساب'), findsOneWidget);
    });

    testWidgets('a wide window uses the side panel and no bottom bar', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );

      expect(find.byKey(const ValueKey<String>('wide-navigation')), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsNothing,
      );
      // The side panel carries the identity and the session actions, so the app
      // bar does not need them at this width.
      expect(find.text('خروج'), findsOneWidget);
      expect(find.text('شرکت الف'), findsWidgets);
    });

    testWidgets('a resized desktop window switches between the two layouts', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );
      expect(find.byKey(const ValueKey<String>('wide-navigation')), findsOneWidget);

      // The user drags the window narrower.
      await tester.binding.setSurfaceSize(_desktopNarrow);
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey<String>('wide-navigation')), findsNothing);

      await tester.binding.setSurfaceSize(_phone);
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey<String>('narrow-navigation')),
        findsOneWidget,
      );
    });
  });

  group('navigation wiring', () {
    testWidgets('every declared destination is reachable from the narrow bar or overflow', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _phone,
      );

      for (final ShellDestination destination in ShellDestinations.all) {
        if (destination.primary) {
          expect(
            find.byKey(ValueKey<String>('bottom-${destination.id}')),
            findsOneWidget,
            reason: '${destination.label} must be in the bottom bar',
          );
        } else {
          expect(
            find.byKey(ValueKey<String>('bottom-${destination.id}')),
            findsNothing,
            reason: '${destination.label} belongs in the overflow sheet',
          );
        }
      }

      // The overflow carries exactly the destinations the bar leaves out.
      await tester.tap(find.byKey(const ValueKey<String>('bottom-more')));
      await tester.pumpAndSettle();
      for (final ShellDestination destination in ShellDestinations.all) {
        if (!destination.primary) {
          expect(
            find.byKey(ValueKey<String>('more-${destination.id}')),
            findsOneWidget,
            reason: '${destination.label} must be in the overflow sheet',
          );
        }
      }
    });

    testWidgets('every declared destination is reachable from the side panel', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );

      for (final ShellDestination destination in ShellDestinations.all) {
        expect(
          find.text(destination.label),
          findsWidgets,
          reason: '${destination.label} must be in the side panel',
        );
      }
    });

    testWidgets('selecting a destination opens it and marks it in the bar', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _phone,
      );

      await tester.tap(find.byKey(const ValueKey<String>('bottom-journal-entry')));
      await tester.pumpAndSettle();
      expect(
        find.text('ثبت سند حسابداری'),
        findsOneWidget,
      );

      final NavigationBar bar = tester.widget<NavigationBar>(
        find.byKey(const ValueKey<String>('narrow-navigation')),
      );
      expect(
        ShellDestinations.primaryDestinations[bar.selectedIndex].id,
        'journal-entry',
      );
    });

    testWidgets('a destination picked from the overflow stays selected when the bar is consulted', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _phone,
      );

      await tester.tap(find.byKey(const ValueKey<String>('bottom-more')));
      await tester.pumpAndSettle();
      final Finder overflowList = find.byKey(
        const ValueKey<String>('overflow-navigation'),
      );
      final Finder settingsItem = find.byKey(
        const ValueKey<String>('more-settings'),
      );
      await tester.ensureVisible(settingsItem);
      await tester.pumpAndSettle();
      await tester.tap(settingsItem);
      await tester.pumpAndSettle();

      expect(
        find.text('سازمان فعال'),
        findsOneWidget,
      );
      // Settings is not one of the bar's own entries, so the bar falls back to
      // the overflow entry rather than highlighting the wrong destination.
      final NavigationBar bar = tester.widget<NavigationBar>(
        find.byKey(const ValueKey<String>('narrow-navigation')),
      );
      expect(bar.selectedIndex, ShellDestinations.primaryDestinations.length);
    });
  });

  group('implemented workspaces', () {
    testWidgets('the dashboard renders real report fields rather than a placeholder', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );
      expect(find.byKey(const ValueKey<String>('dashboard-home')), findsOneWidget);
      expect(find.text('جمع بدهکار'), findsOneWidget);
      expect(find.text('جمع بستانکار'), findsOneWidget);
      expect(find.text('0.00'), findsWidgets);
    });

    testWidgets('accounting destinations render their functional screens', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );
      await tester.tap(find.text('اسناد حسابداری').last);
      await tester.pumpAndSettle();
      expect(find.text('ثبت سند حسابداری'), findsOneWidget);

      await tester.tap(find.text('سرفصل حساب‌ها').last);
      await tester.pumpAndSettle();
      expect(find.text('سرفصل حساب‌ها'), findsWidgets);
    });
  });

}