import 'package:flutter/material.dart';

/// Reusable animated transfer progress bar in Vahak's neobrutalist style.
/// Shows during both uploads and downloads.
class TransferProgressBar extends StatelessWidget {
  final String fileName;
  final int received;
  final int total;
  final bool isUpload;
  final VoidCallback? onCancel;

  const TransferProgressBar({
    super.key,
    required this.fileName,
    required this.received,
    required this.total,
    this.isUpload = false,
    this.onCancel,
  });

  String get _label => isUpload ? 'UPLOADING' : 'DOWNLOADING';
  IconData get _icon =>
      isUpload ? Icons.cloud_upload_rounded : Icons.download_rounded;

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  double get _progress =>
      (total > 0) ? (received / total).clamp(0.0, 1.0) : 0.0;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFE0B2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.black, width: 3),
        boxShadow: const [
          BoxShadow(color: Colors.black, offset: Offset(4, 4), blurRadius: 0),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_icon, color: Colors.black, size: 20),
              const SizedBox(width: 8),
              Text(
                '$_label...',
                style: const TextStyle(
                  fontWeight: FontWeight.w900,
                  fontSize: 13,
                  letterSpacing: 1.5,
                  color: Colors.black,
                ),
              ),
              const Spacer(),
              if (onCancel != null)
                GestureDetector(
                  onTap: onCancel,
                  child: const Icon(Icons.close_rounded,
                      color: Colors.black, size: 20),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            fileName,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                fontWeight: FontWeight.bold, fontSize: 15, color: Colors.black),
          ),
          const SizedBox(height: 10),
          // Progress track
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: _progress,
              minHeight: 10,
              backgroundColor: Colors.white,
              color: Colors.black,
            ),
          ),
          const SizedBox(height: 6),
          // Bytes counter
          Text(
            total > 0
                ? '${_formatBytes(received)} / ${_formatBytes(total)}'
                : '${_formatBytes(received)} received...',
            style: const TextStyle(fontSize: 12, color: Colors.black54),
          ),
        ],
      ),
    );
  }
}
