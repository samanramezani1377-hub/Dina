import 'package:dina_app/features/dashboard/domain/shell_destination.dart';
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
        find.byKey(const ValueKey<String>('placeholder-journal-entry')),
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
      await tester.tap(find.byKey(const ValueKey<String>('more-settings')));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey<String>('placeholder-settings')),
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

  group('honesty about what exists', () {
    testWidgets('every unimplemented destination says so and shows no figures', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );

      final List<ShellDestination> unimplemented = ShellDestinations.all
          .where((ShellDestination d) => !d.implemented)
          .toList();
      expect(unimplemented, isNotEmpty);

      for (final ShellDestination destination in unimplemented) {
        await tester.tap(find.text(destination.label).last);
        await tester.pumpAndSettle();

        expect(
          find.byKey(ValueKey<String>('placeholder-${destination.id}')),
          findsOneWidget,
          reason: '${destination.label} must render its placeholder',
        );
        expect(
          find.text('هنوز پیاده‌سازی نشده است'),
          findsOneWidget,
          reason: '${destination.label} must be marked as not implemented',
        );
        expect(
          find.text('هیچ داده‌ای برای این بخش بارگذاری نشده است.'),
          findsOneWidget,
        );
      }
    });

    testWidgets('the dashboard shows an empty state and no invented balance', (
      WidgetTester tester,
    ) async {
      await tester.pumpDina(
        transport: authenticatedTransport(),
        store: signedInStore(),
        surfaceSize: _desktop,
      );

      expect(find.byKey(const ValueKey<String>('dashboard-home')), findsOneWidget);
      expect(find.text('هنوز داده‌ای برای نمایش وجود ندارد'), findsOneWidget);

      // The only way a fabricated figure could reach this screen is if one were
      // hardcoded, so assert that the text of the page carries no digits.
      final Finder dashboard = find.byKey(const ValueKey<String>('dashboard-home'));
      final Iterable<String> texts = tester
          .widgetList<Text>(
            find.descendant(of: dashboard, matching: find.byType(Text)),
          )
          .map((Text t) => t.data ?? '')
          .where((String t) => t.isNotEmpty);
      for (final String text in texts) {
        expect(
          RegExp(r'[0-9۰-۹]').hasMatch(text),
          isFalse,
          reason: 'The dashboard must not display "$text"',
        );
      }
    });
  });
}