import 'package:flutter/material.dart';
import '../../../../core/services/vahak_api.dart';
import 'transfer_progress_bar.dart';
import '../vault_screen.dart';

class FileCrate extends StatefulWidget {
  final Map<String, dynamic> fileData;
  final VahakApi api;
  final String currentPath; // path of the parent directory

  const FileCrate({
    super.key,
    required this.fileData,
    required this.api,
    this.currentPath = '',
  });

  @override
  State<FileCrate> createState() => _FileCrateState();
}

class _FileCrateState extends State<FileCrate> {
  bool _downloading = false;
  int _received = 0;
  int _total = 0;
  String? _savedPath;

  bool get _isDir => widget.fileData['is_dir'] == true;
  String get _name => widget.fileData['name'] ?? 'Unknown';
  int get _size => widget.fileData['size_bytes'] ?? 0; // backend field is size_bytes

  // Use relative_path from API when available — it's correct for subfolders
  String get _fullRemotePath =>
      widget.fileData['relative_path'] as String? ??
      (widget.currentPath.isNotEmpty ? '${widget.currentPath}/$_name' : _name);

  String _formatSize(int bytes) {
    if (bytes <= 0) return '';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  void _download() async {
    setState(() {
      _downloading = true;
      _received = 0;
      _total = 0;
      _savedPath = null;
    });

    try {
      final file = await widget.api.downloadFile(
        _fullRemotePath,
        onProgress: (recv, total) {
          if (mounted) setState(() { _received = recv; _total = total; });
        },
      );
      if (mounted) {
        setState(() { _downloading = false; _savedPath = file.path; });
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
                const Icon(Icons.check_circle_rounded,
                    color: Colors.amberAccent),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Saved: ${file.path.split('/').last}',
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
        setState(() => _downloading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: Colors.red[900],
            content: Text('Download failed: $e',
                style: const TextStyle(color: Colors.white)),
          ),
        );
      }
    }
  }

  void _navigateInto() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => VaultScreen(
          serverIp: widget.api.serverIp,
          currentPath: _fullRemotePath,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        GestureDetector(
          onTap: _isDir ? _navigateInto : null,
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: _isDir ? const Color(0xFFFFE0B2) : Colors.white,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.black, width: 3),
              boxShadow: const [
                BoxShadow(
                  color: Colors.black,
                  offset: Offset(4, 4),
                  blurRadius: 0,
                ),
              ],
            ),
            child: ListTile(
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: Icon(
                _isDir
                    ? Icons.folder_open_rounded
                    : Icons.insert_drive_file_rounded,
                color: Colors.black,
                size: 32,
              ),
              title: Text(
                _name,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                  color: Colors.black,
                ),
              ),
              subtitle: _isDir
                  ? null
                  : _size > 0
                      ? Text(
                          _formatSize(_size),
                          style: const TextStyle(
                              color: Colors.black54, fontSize: 13),
                        )
                      : null,
              trailing: _isDir
                  ? const Icon(Icons.arrow_forward_ios_rounded,
                      color: Colors.black, size: 28)
                  : _savedPath != null
                      ? const Icon(Icons.check_circle_rounded,
                          color: Colors.green, size: 32)
                      : IconButton(
                          icon: const Icon(Icons.download_rounded,
                              color: Colors.black, size: 32),
                          onPressed: _downloading ? null : _download,
                        ),
            ),
          ),
        ),

        // Inline progress bar — appears below the crate when downloading
        if (_downloading)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: TransferProgressBar(
              fileName: _name,
              received: _received,
              total: _total,
              isUpload: false,
            ),
          ),
      ],
    );
  }
}