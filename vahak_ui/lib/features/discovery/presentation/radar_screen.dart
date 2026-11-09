import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../../vault/presentation/vault_screen.dart';

class RadarScreen extends StatefulWidget {
  const RadarScreen({super.key});

  @override
  State<RadarScreen> createState() => _RadarScreenState();
}

class _RadarScreenState extends State<RadarScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  RawDatagramSocket? _udpSocket;
  bool _foundHub = false;

  final int discoveryPort = 55430;
  final int apiPort = 8000;

  // Timeout state
  Timer? _radarTimer;
  bool _timedOut = false;

  @override
  void initState() {
    super.initState();
    _pulseController =
        AnimationController(vsync: this, duration: const Duration(seconds: 2))
          ..repeat();
    _pulseAnimation = Tween<double>(begin: 0.8, end: 2.5).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeOut),
    );
    _startRadar();

    // Auto-timeout after 15 seconds if no hub found
    _radarTimer = Timer(const Duration(seconds: 15), () {
      if (mounted && !_foundHub) {
        setState(() => _timedOut = true);
      }
    });
  }

  void _startRadar() async {
    setState(() => _timedOut = false);
    _foundHub = false;
    try {
      // reusePort so it doesn't fight the Python server on the same machine
      _udpSocket = await RawDatagramSocket.bind(
          InternetAddress.anyIPv4, discoveryPort,
          reusePort: true);
      _udpSocket?.broadcastEnabled = true;
      _udpSocket?.listen((RawSocketEvent event) {
        if (event == RawSocketEvent.read && !_foundHub) {
          Datagram? dg = _udpSocket?.receive();
          if (dg != null) _verifyHub(dg.address.address);
        }
      });
    } catch (e) {
      debugPrint('Radar jammed: $e');
    }
  }

  void _verifyHub(String ip) async {
    if (_foundHub) return;
    try {
      final response = await http
          .get(Uri.parse('http://$ip:$apiPort/health'))
          .timeout(const Duration(seconds: 2));
      if (response.statusCode == 200) {
        _foundHub = true;
        _radarTimer?.cancel();
        _udpSocket?.close();
        if (mounted) {
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(builder: (_) => VaultScreen(serverIp: ip)),
          );
        }
      }
    } catch (_) {}
  }

  /// Shows a dialog to manually enter the server IP
  void _showIpDialog() {
    final controller = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: Colors.amberAccent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: Colors.black, width: 3),
        ),
        title: const Text(
          'ENTER FORT ADDRESS',
          style: TextStyle(
              fontWeight: FontWeight.w900, fontSize: 18, letterSpacing: 1.5),
        ),
        content: TextField(
          controller: controller,
          keyboardType:
              const TextInputType.numberWithOptions(decimal: true),
          autofocus: true,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          decoration: InputDecoration(
            hintText: '192.168.x.x',
            filled: true,
            fillColor: Colors.white,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: Colors.black, width: 2),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: Colors.black, width: 2),
            ),
            prefixIcon: const Icon(Icons.wifi_rounded, color: Colors.black),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('CANCEL',
                style: TextStyle(
                    color: Colors.black, fontWeight: FontWeight.bold)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.black,
              foregroundColor: Colors.amberAccent,
              side: const BorderSide(color: Colors.black, width: 2),
              elevation: 4,
              shadowColor: Colors.black,
            ),
            onPressed: () {
              final ip = controller.text.trim();
              if (ip.isNotEmpty) {
                Navigator.pop(ctx);
                _udpSocket?.close();
                Navigator.pushReplacement(
                  context,
                  MaterialPageRoute(
                      builder: (_) => VaultScreen(serverIp: ip)),
                );
              }
            },
            child: const Text('CONNECT',
                style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _retry() {
    _radarTimer?.cancel();
    _udpSocket?.close();
    setState(() => _timedOut = false);
    _startRadar();
    _radarTimer = Timer(const Duration(seconds: 15), () {
      if (mounted && !_foundHub) setState(() => _timedOut = true);
    });
  }

  @override
  void dispose() {
    _radarTimer?.cancel();
    _pulseController.dispose();
    _udpSocket?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.amberAccent,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // ── Animated radar icon ──────────────────────────────────────
            Stack(
              alignment: Alignment.center,
              children: [
                AnimatedBuilder(
                  animation: _pulseAnimation,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: _pulseAnimation.value,
                      child: Opacity(
                        opacity:
                            1.0 - (_pulseAnimation.value / 2.5).clamp(0.0, 1.0),
                        child: Container(
                          width: 100,
                          height: 100,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            border:
                                Border.all(color: Colors.black, width: 4),
                            color: Colors.white,
                          ),
                        ),
                      ),
                    );
                  },
                ),
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.black, width: 5),
                    boxShadow: const [
                      BoxShadow(
                          color: Colors.black, offset: Offset(4, 4))
                    ],
                  ),
                  child: const Icon(Icons.radar_rounded,
                      size: 54, color: Colors.black),
                ),
              ],
            ),

            const SizedBox(height: 60),

            // ── Status text ─────────────────────────────────────────────
            Text(
              _timedOut ? 'FORT NOT FOUND' : 'SEARCHING FOR FORT...',
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w900,
                color: Colors.black,
                letterSpacing: 2,
              ),
            ),

            if (_timedOut) ...[
              const SizedBox(height: 8),
              const Text(
                'No hub responded on this network.',
                style: TextStyle(color: Colors.black54, fontSize: 14),
              ),
            ],

            const SizedBox(height: 40),

            // ── Action buttons ──────────────────────────────────────────
            if (_timedOut) ...[
              // Retry scan
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.black,
                  foregroundColor: Colors.amberAccent,
                  side: const BorderSide(color: Colors.black, width: 3),
                  elevation: 6,
                  shadowColor: Colors.black,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 14),
                ),
                icon: const Icon(Icons.radar_rounded),
                onPressed: _retry,
                label: const Text('SCAN AGAIN',
                    style: TextStyle(fontWeight: FontWeight.bold)),
              ),
              const SizedBox(height: 16),
              // Manual IP entry
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.black,
                  side: const BorderSide(color: Colors.black, width: 3),
                  elevation: 6,
                  shadowColor: Colors.black,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 14),
                ),
                icon: const Icon(Icons.edit_rounded),
                onPressed: _showIpDialog,
                label: const Text('ENTER IP MANUALLY',
                    style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ] else ...[
              // During scan — still show manual override
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.white,
                  foregroundColor: Colors.black,
                  side: const BorderSide(color: Colors.black, width: 3),
                  elevation: 6,
                  shadowColor: Colors.black,
                ),
                onPressed: _showIpDialog,
                child: const Text('ENTER LOCAL FORT',
                    style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}