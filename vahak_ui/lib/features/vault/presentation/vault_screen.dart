import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../../../../core/services/vahak_api.dart';
import 'widgets/file_crate.dart';
import 'widgets/transfer_progress_bar.dart';

class VaultScreen extends StatefulWidget {
  final String serverIp;
  final String currentPath; // empty = root, 'Docs/Project' = subfolder

  const VaultScreen({
    super.key,
    required this.serverIp,
    this.currentPath = '',
  });

  @override
  State<VaultScreen> createState() => _VaultScreenState();
}

class _VaultScreenState extends State<VaultScreen> {
  late final VahakApi _api;
  late Future<List<dynamic>> _dirFuture;

  // Upload state
  bool _uploading = false;
  int _uploadSent = 0;
  int _uploadTotal = 0;
  String _uploadFileName = '';

  @override
  void initState() {
    super.initState();
    _api = VahakApi(serverIp: widget.serverIp);
    _load();
  }

  void _load() {
    setState(() {
      _dirFuture = _api.listDirectory(path: widget.currentPath);
    });
  }

  Future<void> _upload() async {
    // file_picker 13.x: static method, returns List<PlatformFile>
    final files = await FilePicker.pickFiles();
    if (files.isEmpty) return;

    final pickedFile = files.first;
    final filePath = pickedFile.path;
    if (filePath == null) return;

    setState(() {
      _uploading = true;
      _uploadFileName = pickedFile.name;
      _uploadSent = 0;
      _uploadTotal = 0;
    });

    try {
      await _api.uploadFile(
        filePath,
        onProgress: (sent, total) {
          if (mounted) setState(() { _uploadSent = sent; _uploadTotal = total; });
        },
      );

      if (mounted) {
        setState(() => _uploading = false);
        _load(); // Refresh list to show new file
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.black,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: const BorderSide(color: Colors.amberAccent, width: 2),
            ),
            content: Row(
              children: [
                const Icon(Icons.cloud_done_rounded, color: Colors.amberAccent),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '$_uploadFileName uploaded!',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _uploading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red[900],
            content: Text('Upload failed: $e',
                style: const TextStyle(color: Colors.white)),
          ),
        );
      }
    }
  }

  String get _title {
    if (widget.currentPath.isEmpty) return 'VAHAK VAULT';
    return widget.currentPath.split('/').last.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16.0),
            child: IconButton(
              icon: const Icon(Icons.cloud_upload_rounded,
                  color: Colors.black, size: 36),
              onPressed: _uploading ? null : _upload,
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // Upload progress bar (shown when uploading)
          if (_uploading)
            TransferProgressBar(
              fileName: _uploadFileName,
              received: _uploadSent,
              total: _uploadTotal,
              isUpload: true,
            ),

          // File list
          Expanded(
            child: RefreshIndicator(
              color: Colors.black,
              backgroundColor: Colors.amberAccent,
              onRefresh: () async => _load(),
              child: FutureBuilder<List<dynamic>>(
                future: _dirFuture,
                builder: (context, snapshot) {
                  // ── Loading ──────────────────────────────────────────────
                  if (snapshot.connectionState == ConnectionState.waiting) {
                    return const Center(
                      child: CircularProgressIndicator(
                        color: Color(0xFFD96C4A),
                        strokeWidth: 6,
                      ),
                    );
                  }

                  // ── Error ────────────────────────────────────────────────
                  if (snapshot.hasError) {
                    return Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(20),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                                border: Border.all(
                                    color: Colors.black, width: 4),
                                boxShadow: const [
                                  BoxShadow(
                                      color: Colors.black,
                                      offset: Offset(4, 4))
                                ],
                              ),
                              child: const Icon(
                                  Icons.wifi_off_rounded,
                                  size: 48,
                                  color: Colors.black),
                            ),
                            const SizedBox(height: 24),
                            const Text(
                              'CONNECTION LOST',
                              style: TextStyle(
                                fontWeight: FontWeight.w900,
                                fontSize: 20,
                                letterSpacing: 2,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '${snapshot.error}',
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                  color: Colors.black54, fontSize: 13),
                            ),
                            const SizedBox(height: 28),
                            ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.amberAccent,
                                foregroundColor: Colors.black,
                                side: const BorderSide(
                                    color: Colors.black, width: 3),
                                elevation: 6,
                                shadowColor: Colors.black,
                              ),
                              icon: const Icon(Icons.refresh_rounded),
                              label: const Text('RETRY',
                                  style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 1.5)),
                              onPressed: _load,
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  final files = snapshot.data!;

                  // ── Empty state ──────────────────────────────────────────
                  if (files.isEmpty) {
                    return Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(24),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              shape: BoxShape.circle,
                              border: Border.all(
                                  color: Colors.black, width: 4),
                              boxShadow: const [
                                BoxShadow(
                                    color: Colors.black,
                                    offset: Offset(4, 4))
                              ],
                            ),
                            child: const Icon(
                                Icons.inventory_2_rounded,
                                size: 48,
                                color: Colors.black),
                          ),
                          const SizedBox(height: 20),
                          const Text(
                            'VAULT IS EMPTY',
                            style: TextStyle(
                              fontWeight: FontWeight.w900,
                              fontSize: 20,
                              letterSpacing: 2,
                            ),
                          ),
                          const SizedBox(height: 8),
                          const Text('Drop something in via the upload button',
                              style: TextStyle(color: Colors.black54)),
                        ],
                      ),
                    );
                  }

                  // ── File list ────────────────────────────────────────────
                  return ListView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.only(top: 8, bottom: 32),
                    itemCount: files.length,
                    itemBuilder: (context, index) {
                      return FileCrate(
                        fileData: files[index],
                        api: _api,
                        currentPath: widget.currentPath,
                      );
                    },
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}