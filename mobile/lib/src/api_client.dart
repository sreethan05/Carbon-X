import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'session_store.dart';

class ApiResult {
  const ApiResult(
      {required this.success,
      required this.data,
      this.message,
      this.status = 0});
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

  Future<ApiResult> get(String path) => _send('GET', path);
  Future<ApiResult> post(String path, [Map<String, dynamic>? body]) =>
      _send('POST', path, body ?? const {});

  Future<ApiResult> _send(String method, String path,
      [Map<String, dynamic>? body]) async {
    final token = session.token;
    final headers = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
    try {
      final uri = Uri.parse('${baseUrl.replaceFirst(RegExp(r'/+$'), '')}$path');
      if (uri.host.isEmpty ||
          !(uri.scheme == 'https' || (kDebugMode && uri.scheme == 'http'))) {
        return const ApiResult(
          success: false,
          data: {},
          message: 'Set CARBONX_API_BASE to the CarbonX HTTPS backend URL.',
        );
      }
      final response = method == 'GET'
          ? await http
              .get(uri, headers: headers)
              .timeout(const Duration(seconds: 15))
          : await http
              .post(uri, headers: headers, body: jsonEncode(body))
              .timeout(const Duration(seconds: 15));
      if (response.statusCode == 401 &&
          token != null &&
          session.token == token) {
        await session.clear();
      }
      Map<String, dynamic>? decoded;
      try {
        final value = jsonDecode(utf8.decode(response.bodyBytes));
        if (value is Map<String, dynamic>) decoded = value;
      } on FormatException {
        // A proxy can return an HTML or otherwise non-JSON error page.
      }
      final ok = response.statusCode >= 200 &&
          response.statusCode < 300 &&
          decoded != null &&
          decoded['success'] != false;
      final detail = decoded?['detail'];
      final message = decoded?['message']?.toString() ??
          (detail is String ? detail : null) ??
          (ok
              ? null
              : 'Unexpected server response (HTTP ${response.statusCode}).');
      return ApiResult(
          success: ok,
          data: decoded ?? const {},
          message: message,
          status: response.statusCode);
    } catch (_) {
      return const ApiResult(
        success: false,
        data: {},
        message:
            'Cannot reach CarbonX. Check the backend URL and your connection.',
      );
    }
  }
}
