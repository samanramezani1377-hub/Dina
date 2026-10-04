import 'package:flutter/material.dart';
import 'package:forui/forui.dart';

abstract final class AppTheme {
  static const Locale locale = Locale('fa', 'IR');
  static const List<Locale> supportedLocales = <Locale>[locale];

  static FThemeData foruiLight() => FTheme.neutral.light.desktop;
  static FThemeData foruiDark() => FThemes.neutral.dark.desktop;

  static ThemeData light() => _materialTheme(Brightness.light);
  static ThemeData dark() => _materialTheme(Brightness.dark);

  static ThemeData _materialTheme(Brightness brightness) {
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF6750A4),
      brightness: brightness,
    );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'Vazirmatn',
      visualDensity: VisualDensity.standard,
    );
  }
}

abstract final class Breakpoints {
  static const double wide = 900;
  static const double extendedRail = 1180;
  static bool isWide(double width) => width >= wide;
  static bool isExtendedRail(double width) => width >= extendedRail;
}
