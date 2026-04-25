import 'package:flutter/material.dart';

// ════════════════════════════════════════════════════════════
//  Thème Tunisie Telecom — couleurs identiques à user_app
// ════════════════════════════════════════════════════════════

class TTColors {
  static const Color purple      = Color(0xFF5B1FBE);
  static const Color purpleDark  = Color(0xFF3D1484);
  static const Color purpleLight = Color(0xFF7B3FDE);
  static const Color purpleBg    = Color(0xFFF3EEFF);
  static const Color teal        = Color(0xFF00B4D8);
  static const Color tealDark    = Color(0xFF0096B8);
  static const Color red         = Color(0xFFE8002D);
  static const Color green       = Color(0xFF16A34A);
  static const Color orange      = Color(0xFFD97706);
  static const Color white       = Color(0xFFFFFFFF);
  static const Color gray        = Color(0xFFF4F5F7);
  static const Color border      = Color(0xFFE5E7EB);
  static const Color text        = Color(0xFF1A1A2E);
  static const Color muted       = Color(0xFF6B7280);
}

class AppTheme {
  static ThemeData get theme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: TTColors.purple,
        primary: TTColors.purple,
        secondary: TTColors.teal,
        surface: TTColors.white,
        error: TTColors.red,
      ),
      scaffoldBackgroundColor: TTColors.gray,
      fontFamily: 'Cairo',
      appBarTheme: const AppBarTheme(
        backgroundColor: TTColors.white,
        foregroundColor: TTColors.purple,
        elevation: 2,
        shadowColor: Color(0x1A000000),
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: TTColors.purple,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: TTColors.purple,
          foregroundColor: TTColors.white,
          textStyle: const TextStyle(
            fontFamily: 'Cairo',
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(vertical: 14),
          elevation: 4,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: TTColors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: TTColors.border, width: 1.5),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: TTColors.border, width: 1.5),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: TTColors.purple, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: const BorderSide(color: TTColors.red, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        hintStyle: const TextStyle(color: TTColors.muted, fontFamily: 'Cairo'),
        labelStyle: const TextStyle(color: TTColors.muted, fontFamily: 'Cairo'),
        prefixIconColor: TTColors.muted,
      ),
      cardTheme: CardThemeData(
        color: TTColors.white,
        elevation: 2,
        shadowColor: const Color(0x1A5B1FBE),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
        ),
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 28,
          fontWeight: FontWeight.w900,
          color: TTColors.text,
        ),
        headlineMedium: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 22,
          fontWeight: FontWeight.w800,
          color: TTColors.text,
        ),
        titleLarge: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: TTColors.text,
        ),
        titleMedium: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: TTColors.text,
        ),
        bodyLarge: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 15,
          color: TTColors.text,
        ),
        bodyMedium: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 13,
          color: TTColors.muted,
        ),
        labelSmall: TextStyle(
          fontFamily: 'Cairo',
          fontSize: 11,
          color: TTColors.muted,
        ),
      ),
    );
  }
}
