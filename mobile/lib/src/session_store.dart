import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SessionStore extends ChangeNotifier {
  static const _tokenKey = 'carbonx_token';
  static const _nameKey = 'carbonx_name';
  static const _phoneKey = 'carbonx_phone';

  String? token;
  String? name;
  String? phone;
  bool restored = false;

  bool get isAuthenticated => token?.isNotEmpty == true;

  Future<void> restore() async {
    final prefs = await SharedPreferences.getInstance();
    token = prefs.getString(_tokenKey);
    name = prefs.getString(_nameKey);
    phone = prefs.getString(_phoneKey);
    restored = true;
  }

  Future<void> save({required String newToken, Map<String, dynamic>? user}) async {
    token = newToken;
    name = user?['name']?.toString();
    phone = user?['phone']?.toString();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, newToken);
    if (name != null) await prefs.setString(_nameKey, name!);
    if (phone != null) await prefs.setString(_phoneKey, phone!);
    notifyListeners();
  }

  Future<void> clear() async {
    token = null;
    name = null;
    phone = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_nameKey);
    await prefs.remove(_phoneKey);
    notifyListeners();
  }
}
