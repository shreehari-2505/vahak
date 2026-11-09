import 'package:flutter/material.dart';

class VahakTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      scaffoldBackgroundColor: const Color(0xFFF4EEDD), // Sandstone walls
      appBarTheme: const AppBarTheme(
        backgroundColor: Color(0xFFD96C4A), // Terracotta brick
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontSize: 24, 
          fontWeight: FontWeight.w900, 
          letterSpacing: 2,
        ),
      ),
      colorScheme: const ColorScheme.light(
        primary: Color(0xFFD96C4A),
        secondary: Color(0xFFFFB347), // Torchlight amber
      ),
    );
  }
}