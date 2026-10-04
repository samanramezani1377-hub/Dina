import 'package:flutter/material.dart';
import 'package:forui/forui.dart';

abstract final class AppTheme {
  static FThemeData foruiLight() => FTheme.neutral.light.desktop;
  static FThemeData foruiDark() => FTheme.neutral.dark.desktop;
  static const Locale locale = Locale('fa', 'IR');
  static const List<Locale> supportedLocales = <Locale>[locale];
  static ThemeData light() => _foruiMaterial(FTheme.neutral.light.desktop);
  static ThemeData dark() => _foruiMaterial(FTheme.neutral.dark.desktop);

  static ThemeData _foruiMaterial(FThemeData theme) => theme
      .toApproximateMaterialTheme()
      .copyWith(fontFamily: 'Vazirmatn', visualDensity: VisualDensity.standard);

  static ThemeData _base(ColorScheme scheme) => ThemeData(
    colorScheme: scheme, useMaterial3: true, fontFamily: 'Vazirmatn',
    scaffoldBackgroundColor: scheme.surface,
    appBarTheme: AppBarTheme(backgroundColor: scheme.surface, foregroundColor: scheme.onSurface, elevation: 0, scrolledUnderElevation: 1),
    cardTheme: CardTheme(clipBehavior: Clip.antiAlias, elevation: 0, margin: const EdgeInsets.symmetric(vertical: 6),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20), side: BorderSide(color: scheme.outlineVariant)), color: scheme.surfaceContainerLow),
    inputDecorationTheme: InputDecorationTheme(filled: true, fillColor: scheme.surfaceContainerLow, isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: scheme.outlineVariant)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: scheme.outlineVariant)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide(color: scheme.primary, width: 1.5))),
    filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(minimumSize: const Size(44,46), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)))),
    outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(minimumSize: const Size(44,46), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)))),
    listTileTheme: const ListTileThemeData(contentPadding: EdgeInsets.symmetric(horizontal: 18, vertical: 4)),
    navigationBarTheme: NavigationBarThemeData(height: 72, indicatorShape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18))),
    snackBarTheme: SnackBarThemeData(behavior: SnackBarBehavior.floating, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14))),
    dialogTheme: DialogThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24))),
  );
}
abstract final class Breakpoints {
  static const double wide = 900;
  static const double extendedRail = 1180;
  static bool isWide(double width) => width >= wide;
  static bool isExtendedRail(double width) => width >= extendedRail;
}
