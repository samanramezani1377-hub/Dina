import 'package:flutter/material.dart';
import 'package:forui/forui.dart';

abstract final class AppTheme {
  static const Locale locale = Locale('fa', 'IR');
  static const List<Locale> supportedLocales = <Locale>[locale];

  static FThemeData foruiLight() => FTheme.neutral.light.desktop;
  static FThemeData foruiDark() => FTheme.neutral.dark.desktop;

  static ThemeData light() => _materialBridge(foruiLight());
  static ThemeData dark() => _materialBridge(foruiDark());

  static ThemeData _materialBridge(FThemeData foruiTheme) {
    final ThemeData theme = foruiTheme.toApproximateMaterialTheme();
    return theme.copyWith(
      fontFamily: 'Vazirmatn',
      visualDensity: VisualDensity.standard,
      scaffoldBackgroundColor: theme.colorScheme.surface,
      textTheme: theme.textTheme.apply(fontFamily: 'Vazirmatn'),
      inputDecorationTheme: theme.inputDecorationTheme.copyWith(
        labelStyle: theme.textTheme.bodyMedium?.copyWith(fontFamily: 'Vazirmatn'),
      ),
    );
  }
}

abstract final class Breakpoints {
  static const double wide = 900;
  static const double extendedRail = 1180;
  static bool isWide(double width) => width >= wide;
  static bool isExtendedRail(double width) => width >= extendedRail;
}
