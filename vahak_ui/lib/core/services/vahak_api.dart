import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// Central API layer for Vahak.
/// All HTTP calls go through here — screens never touch raw http.
///
/// Backend route map (match exactly or requests will 404):
///   List root   : GET  /api/v1/scan/list
///   List subdir : GET  /api/v1/scan/list/{sub_path}        ← path param in URL
///   Download    : GET  /api/v1/transfer/pull/{file_path}   ← path param in URL
///   Upload      : POST /api/v1/transfer/push/{dest_path}   ← path param in URL
///   Health      : GET  /health
class VahakApi {
  final String serverIp;
  final int port;

  VahakApi({required this.serverIp, this.port = 8000});

  String get _base => 'http://$serverIp:$port';

  // ── Directory listing ───────────────────────────────────────────────────────

  /// Lists files/folders at [path] (empty string = root).
  /// Backend: GET /api/v1/scan/list          → root
  ///          GET /api/v1/scan/list/{path}   → subfolder
  Future<List<dynamic>> listDirectory({String path = ''}) async {
    // Path goes in the URL segment, NOT as a query parameter
    final endpoint = path.isNotEmpty
        ? '$_base/api/v1/scan/list/${Uri.encodeComponent(path)}'
        : '$_base/api/v1/scan/list';

    final response = await http
        .get(Uri.parse(endpoint))
        .timeout(const Duration(seconds: 10));

    if (response.statusCode == 200) {
      return jsonDecode(response.body)['contents'] as List<dynamic>;
    }
    throw Exception('List failed (${response.statusCode}): ${response.body}');
  }

  // ── Download ────────────────────────────────────────────────────────────────

  /// Downloads [remotePath] and saves it to the app documents directory.
  /// Backend: GET /api/v1/transfer/pull/{file_path}
  /// [remotePath] should be the `relative_path` value from the list response.
  /// Calls [onProgress] with (bytesReceived, totalBytes) during transfer.
  Future<File> downloadFile(
    String remotePath, {
    required void Function(int received, int total) onProgress,
  }) async {
    // Path goes in the URL segment after /pull/
    final endpoint = '$_base/api/v1/transfer/pull/${Uri.encodeComponent(remotePath)}';

    final client = http.Client();
    try {
      final request = http.Request('GET', Uri.parse(endpoint));
      final streamed = await client.send(request);

      if (streamed.statusCode != 200) {
        throw Exception('Download failed (${streamed.statusCode})');
      }

      final total = streamed.contentLength ?? 0;
      int received = 0;
      final bytes = <int>[];

      await for (final chunk in streamed.stream) {
        bytes.addAll(chunk);
        received += chunk.length;
        onProgress(received, total);
      }

      final dir = await getApplicationDocumentsDirectory();
      final fileName = remotePath.split('/').last;
      final file = File('${dir.path}/$fileName');
      await file.writeAsBytes(bytes);
      return file;
    } finally {
      client.close();
    }
  }

  // ── Upload ──────────────────────────────────────────────────────────────────

  /// Uploads the file at [localPath] to [destPath] inside the Vault.
  /// Backend: POST /api/v1/transfer/push/{dest_path}
  /// [destPath] is the target subfolder in the Vault (empty = root).
  /// Calls [onProgress] with (bytesSent, totalBytes).
  Future<void> uploadFile(
    String localPath, {
    String destPath = '',
    required void Function(int sent, int total) onProgress,
  }) async {
    final file = File(localPath);
    final bytes = await file.readAsBytes();
    final total = bytes.length;
    final fileName = localPath.split('/').last;

    // dest_path goes in the URL segment after /push/
    final segment = destPath.isNotEmpty
        ? Uri.encodeComponent(destPath)
        : ''; // empty → uploads to Vault root
    final endpoint = '$_base/api/v1/transfer/push/$segment';

    final request = http.MultipartRequest('POST', Uri.parse(endpoint))
      ..files.add(
        http.MultipartFile.fromBytes('file', bytes, filename: fileName),
      );

    onProgress(0, total);
    final response = await request.send();
    onProgress(total, total);

    if (response.statusCode != 201) {
      throw Exception('Upload failed (${response.statusCode})');
    }
  }
}
