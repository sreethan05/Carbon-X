import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SessionStore extends ChangeNotifier {
  static const _tokenKey = 'carbonx_token';
  static const _nameKey = 'carbonx_name';
  static const _phoneKey = 'carbonx_phone';

  String? token;
  String? name;
  String? phone;
  bool get isAuthenticated => token?.isNotEmpty == true;

  Future<void> restore() async {
    final prefs = await SharedPreferences.getInstance();
    token = prefs.getString(_tokenKey);
    name = prefs.getString(_nameKey);
    phone = prefs.getString(_phoneKey);
  }

  Future<void> save(
      {required String newToken, Map<String, dynamic>? user}) async {
    final prefs = await SharedPreferences.getInstance();
    final newName = user?['name']?.toString();
    final newPhone = user?['phone']?.toString();
    if (newName == null) {
      await prefs.remove(_nameKey);
    } else {
      await prefs.setString(_nameKey, newName);
    }
    if (newPhone == null) {
      await prefs.remove(_phoneKey);
    } else {
      await prefs.setString(_phoneKey, newPhone);
    }
    if (!await prefs.setString(_tokenKey, newToken)) {
      throw StateError('Session storage is unavailable.');
    }
    token = newToken;
    name = newName;
    phone = newPhone;
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
