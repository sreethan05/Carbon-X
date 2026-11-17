import 'package:carbonx_mobile/src/api_client.dart';
import 'package:carbonx_mobile/src/app.dart';
import 'package:carbonx_mobile/src/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('farmer can correct an invalid code and sign out',
      (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);

    final session = _MemorySession();
    final api = _FarmerApi(session);
    await tester.pumpWidget(CarbonXApp(api: api, session: session));

    await tester.enterText(find.byType(TextField), '9000000001');
    await tester.tap(find.text('Send OTP'));
    await tester.pumpAndSettle();
    expect(find.text('Change number'), findsOneWidget);
    expect(find.text('Resend code'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField).first).readOnly,
        isTrue);

    final code = find.byType(TextField).last;
    await tester.enterText(code, '123');
    await tester.tap(find.text('Verify and sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Enter the six-digit code.'), findsOneWidget);
    expect(api.loginAttempts, 0);

    await tester.enterText(code, '123456');
    await tester.tap(find.text('Verify and sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Namaste, Test Farmer'), findsOneWidget);
    expect(find.text('Demo farms'), findsOneWidget);
    expect(api.loginAttempts, 1);

    await tester.tap(find.text('Market'));
    await tester.pumpAndSettle();
    expect(find.text('Sample listings · Database offline'), findsOneWidget);
    expect(find.text('No active listings right now.'), findsOneWidget);

    await tester.tap(find.text('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Send OTP'), findsOneWidget);
    expect(session.isAuthenticated, isFalse);
    expect(tester.takeException(), isNull);
  });
}

class _FarmerApi extends ApiClient {
  _FarmerApi(super.session);

  int loginAttempts = 0;

  static const _user = {
    'name': 'Test Farmer',
    'phone': '9000000001',
    'demo': true,
  };

  @override
  Future<ApiResult> post(String path, [Map<String, dynamic>? body]) async {
    switch (path) {
      case '/login/send-otp':
        expect(body, {'phone': '9000000001'});
        return const ApiResult(success: true, data: {});
      case '/login':
        loginAttempts++;
        expect(body, {'phone': '9000000001', 'otp': '123456'});
        return const ApiResult(
          success: true,
          data: {'token': 'test-token', 'user': _user},
        );
      default:
        throw StateError('Unexpected POST $path');
    }
  }

  @override
  Future<ApiResult> get(String path) async {
    if (path == '/me') {
      return const ApiResult(success: true, data: {'user': _user, 'farms': []});
    }
    if (path.startsWith('/marketplace/listings?')) {
      return const ApiResult(
        success: true,
        data: {'source': 'fallback', 'listings': []},
      );
    }
    return const ApiResult(success: true, data: {});
  }
}

class _MemorySession extends SessionStore {
  String? _activeToken;
  String? _name;
  String? _phone;

  @override
  String? get token => _activeToken;

  @override
  String? get name => _name;

  @override
  String? get phone => _phone;

  @override
  Future<void> save(
      {required String newToken, Map<String, dynamic>? user}) async {
    _activeToken = newToken;
    _name = user?['name'] as String?;
    _phone = user?['phone'] as String?;
    notifyListeners();
  }

  @override
  Future<void> clear() async {
    _activeToken = null;
    _name = null;
    _phone = null;
    notifyListeners();
  }
}
