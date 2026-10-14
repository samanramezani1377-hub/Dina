import 'package:flutter/material.dart';
import 'package:forui/forui.dart';

abstract final class AppTheme {
  static const Locale locale = Locale('fa', 'IR');
  static const List<Locale> supportedLocales = <Locale>[locale];

  static FThemeData foruiLight() => FThemes.zinc.light;
  static FThemeData foruiDark() => FThemes.zinc.dark;

  static ThemeData light() => _materialTheme(Brightness.light);
  static ThemeData dark() => _materialTheme(Brightness.dark);

  static ThemeData _materialTheme(Brightness brightness) {
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF14532D),
      brightness: brightness,
    );
    return ThemeData(
      useMaterial3: false,
      colorScheme: scheme,\n      scaffoldBackgroundColor: brightness == Brightness.light\n          ? const Color(0xFFFFFFFF)\n          : const Color(0xFF101713),
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
