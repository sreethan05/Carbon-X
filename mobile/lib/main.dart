import 'package:flutter/material.dart';

import 'src/api_client.dart';
import 'src/app.dart';
import 'src/session_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final session = SessionStore();
  await session.restore();
  runApp(CarbonXApp(api: ApiClient(session), session: session));
}
