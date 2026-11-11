import 'dart:convert';

import 'package:http/http.dart' as http;

import 'session_store.dart';

class ApiResult {
  const ApiResult({required this.success, required this.data, this.message, this.status = 0});
  final bool success;
  final Map<String, dynamic> data;
  final String? message;
  final int status;
}

class ApiClient {
  ApiClient(this.session);

  static const baseUrl = String.fromEnvironment(
    'CARBONX_API_BASE',
    defaultValue: 'http://10.0.2.2:8000',
  );

  final SessionStore session;

  Map<String, String> get _headers => {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (session.token != null) 'Authorization': 'Bearer ${session.token}',
      };

  Future<ApiResult> get(String path) => _send('GET', path);
  Future<ApiResult> post(String path, [Map<String, dynamic>? body]) =>
      _send('POST', path, body ?? const {});

  Future<ApiResult> _send(String method, String path, [Map<String, dynamic>? body]) async {
    try {
      final uri = Uri.parse('$baseUrl$path');
      final response = method == 'GET'
          ? await http.get(uri, headers: _headers).timeout(const Duration(seconds: 15))
          : await http
              .post(uri, headers: _headers, body: jsonEncode(body))
              .timeout(const Duration(seconds: 15));
      Map<String, dynamic> decoded = {};
      if (response.body.isNotEmpty) {
        final value = jsonDecode(response.body);
        if (value is Map<String, dynamic>) decoded = value;
      }
      final ok = response.statusCode >= 200 && response.statusCode < 300 && decoded['success'] != false;
      final message = decoded['message']?.toString() ??
          (decoded['detail'] is String ? decoded['detail'].toString() : null);
      if (response.statusCode == 401) await session.clear();
      return ApiResult(success: ok, data: decoded, message: message, status: response.statusCode);
    } catch (_) {
      return const ApiResult(
        success: false,
        data: {},
        message: 'Cannot reach CarbonX. Check the backend URL and your connection.',
      );
    }
  }
}
