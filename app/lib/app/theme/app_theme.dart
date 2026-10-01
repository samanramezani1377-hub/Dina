import 'package:flutter/material.dart';

/// Visual language for the client: Material 3, Persian typography, RTL.
///
/// The app is Persian-only, so the locale and direction are fixed here rather
/// than left to the platform default.
abstract final class AppTheme {
  static const Locale locale = Locale('fa', 'IR');

  static const List<Locale> supportedLocales = <Locale>[locale];

  static ThemeData light() {
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF00695C),
      brightness: Brightness.light,
    );
    return _base(scheme);
  }

  static ThemeData dark() {
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF00695C),
      brightness: Brightness.dark,
    );
    return _base(scheme);
  }

  static ThemeData _base(ColorScheme scheme) {
    return ThemeData(
      colorScheme: scheme,
      useMaterial3: true,
      fontFamily: 'Vazirmatn',
      scaffoldBackgroundColor: scheme.surface,
      appBarTheme: AppBarTheme(
        backgroundColor: scheme.surfaceContainerHighest,
        foregroundColor: scheme.onSurface,
        centerTitle: false,
      ),
      cardTheme: CardTheme(
        clipBehavior: Clip.antiAlias,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerHighest,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      listTileTheme: const ListTileThemeData(
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      ),
    );
  }
}

/// Layout breakpoints. A resizable desktop window and a phone get genuinely
/// different navigation, not one layout stretched to fit.
abstract final class Breakpoints {
  /// At or above this width the shell shows a side navigation panel.
  static const double wide = 900;

  /// At or above this width the side panel shows labels instead of icons only.
  static const double extendedRail = 1180;

  static bool isWide(double width) => width >= wide;

  static bool isExtendedRail(double width) => width >= extendedRail;
}