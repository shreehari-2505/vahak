import 'package:flutter/material.dart';
import 'core/theme/vahak_theme.dart';
import 'features/discovery/presentation/radar_screen.dart';

void main() {
  runApp(const VahakApp());
}

class VahakApp extends StatelessWidget {
  const VahakApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Vahak',
      debugShowCheckedModeBanner: false,
      theme: VahakTheme.lightTheme, // ← theme applied
      home: const RadarScreen(),
    );
  }
}