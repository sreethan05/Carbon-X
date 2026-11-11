import 'package:flutter/material.dart';

import 'api_client.dart';
import 'session_store.dart';
import 'theme.dart';

class CarbonXApp extends StatefulWidget {
  const CarbonXApp({super.key, required this.api, required this.session});
  final ApiClient api;
  final SessionStore session;

  @override
  State<CarbonXApp> createState() => _CarbonXAppState();
}

class _CarbonXAppState extends State<CarbonXApp> {
  @override
  void initState() {
    super.initState();
    widget.session.addListener(_refresh);
  }

  @override
  void dispose() {
    widget.session.removeListener(_refresh);
    super.dispose();
  }

  void _refresh() => setState(() {});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'CarbonX',
      theme: CarbonXTheme.light,
      home: widget.session.isAuthenticated
          ? MobileShell(api: widget.api, session: widget.session)
          : LoginScreen(api: widget.api, session: widget.session),
    );
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.session});
  final ApiClient api;
  final SessionStore session;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final phone = TextEditingController();
  final otp = TextEditingController();
  bool otpSent = false;
  bool busy = false;
  String? error;

  Future<void> _sendOtp() async {
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(phone.text.trim())) {
      setState(() => error = 'Enter a valid 10-digit Indian mobile number.');
      return;
    }
    setState(() { busy = true; error = null; });
    final result = await widget.api.post('/login/send-otp', {'phone': phone.text.trim()});
    if (!mounted) return;
    setState(() {
      busy = false;
      otpSent = result.success;
      error = result.success ? null : result.message;
      final devOtp = result.data['dev_otp']?.toString();
      if (devOtp != null) otp.text = devOtp;
    });
  }

  Future<void> _login() async {
    setState(() { busy = true; error = null; });
    final result = await widget.api.post('/login', {
      'phone': phone.text.trim(),
      'otp': otp.text.trim(),
    });
    await _acceptLogin(result);
  }

  Future<void> _demo() async {
    setState(() { busy = true; error = null; });
    final result = await widget.api.post('/demo/login');
    await _acceptLogin(result);
  }

  Future<void> _acceptLogin(ApiResult result) async {
    if (!mounted) return;
    if (result.success && result.data['token'] != null) {
      await widget.session.save(
        newToken: result.data['token'].toString(),
        user: result.data['user'] is Map<String, dynamic>
            ? result.data['user'] as Map<String, dynamic>
            : null,
      );
    } else {
      setState(() { busy = false; error = result.message ?? 'Sign in failed.'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: CarbonXTheme.forest,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Icon(Icons.eco_rounded, color: Color(0xFF6EE7B7), size: 34),
                  ),
                  const SizedBox(height: 24),
                  const Text('CarbonX', style: TextStyle(fontSize: 36, fontWeight: FontWeight.w900, letterSpacing: -1.5)),
                  const SizedBox(height: 8),
                  Text('Evidence to income—for every field.', style: Theme.of(context).textTheme.titleMedium?.copyWith(color: Colors.blueGrey.shade600)),
                  const SizedBox(height: 32),
                  TextField(
                    controller: phone,
                    keyboardType: TextInputType.phone,
                    maxLength: 10,
                    decoration: const InputDecoration(labelText: 'Mobile number', prefixText: '+91 ', counterText: ''),
                  ),
                  if (otpSent) ...[
                    const SizedBox(height: 14),
                    TextField(
                      controller: otp,
                      keyboardType: TextInputType.number,
                      maxLength: 6,
                      decoration: const InputDecoration(labelText: '6-digit OTP', counterText: ''),
                    ),
                  ],
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Text(error!, style: const TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: busy ? null : (otpSent ? _login : _sendOtp),
                    icon: busy
                        ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : Icon(otpSent ? Icons.login : Icons.sms_outlined),
                    label: Text(otpSent ? 'Verify and sign in' : 'Send OTP'),
                  ),
                  const SizedBox(height: 12),
                  OutlinedButton.icon(
                    onPressed: busy ? null : _demo,
                    icon: const Icon(Icons.science_outlined),
                    label: const Text('Explore demo mode'),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Demo mode is available only when the backend database is intentionally unconfigured.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.blueGrey),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class MobileShell extends StatefulWidget {
  const MobileShell({super.key, required this.api, required this.session});
  final ApiClient api;
  final SessionStore session;

  @override
  State<MobileShell> createState() => _MobileShellState();
}

class _MobileShellState extends State<MobileShell> {
  int index = 0;

  @override
  Widget build(BuildContext context) {
    final pages = [
      DashboardPage(api: widget.api, session: widget.session),
      MarketplacePage(api: widget.api),
      WalletPage(api: widget.api),
      TrustPage(api: widget.api),
      ProfilePage(session: widget.session),
    ];
    return Scaffold(
      appBar: AppBar(
        title: const Row(children: [Icon(Icons.eco_rounded, color: Color(0xFF6EE7B7)), SizedBox(width: 9), Text('CarbonX', style: TextStyle(fontWeight: FontWeight.w900))]),
        actions: [IconButton(onPressed: () {}, icon: const Icon(Icons.notifications_none_rounded))],
      ),
      body: IndexedStack(index: index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.grid_view_rounded), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.storefront_outlined), label: 'Market'),
          NavigationDestination(icon: Icon(Icons.account_balance_wallet_outlined), label: 'Wallet'),
          NavigationDestination(icon: Icon(Icons.verified_user_outlined), label: 'Trust'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
        ],
      ),
    );
  }
}

class AsyncPage extends StatefulWidget {
  const AsyncPage({super.key, required this.loader, required this.builder});
  final Future<ApiResult> Function() loader;
  final Widget Function(BuildContext, Map<String, dynamic>) builder;

  @override
  State<AsyncPage> createState() => _AsyncPageState();
}

class _AsyncPageState extends State<AsyncPage> {
  late Future<ApiResult> future = widget.loader();
  void reload() => setState(() => future = widget.loader());

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<ApiResult>(
      future: future,
      builder: (context, snapshot) {
        if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
        final result = snapshot.data!;
        if (!result.success) {
          return Center(child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [const Icon(Icons.cloud_off_rounded, size: 48), const SizedBox(height: 12), Text(result.message ?? 'Unable to load data.', textAlign: TextAlign.center), const SizedBox(height: 16), FilledButton.tonal(onPressed: reload, child: const Text('Try again'))])));
        }
        return RefreshIndicator(onRefresh: () async => reload(), child: widget.builder(context, result.data));
      },
    );
  }
}

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key, required this.api, required this.session});
  final ApiClient api;
  final SessionStore session;

  @override
  Widget build(BuildContext context) {
    return AsyncPage(
      loader: () => api.get('/me'),
      builder: (context, data) {
        final user = data['user'] is Map ? data['user'] as Map : const {};
        final farms = data['farms'] is List ? data['farms'] as List : const [];
        final credits = farms.fold<double>(0, (sum, item) {
          final value = (item as Map)['total_credits'];
          return sum + (value is num ? value.toDouble() : 0);
        });
        return ListView(
          padding: const EdgeInsets.all(18),
          children: [
            Text('Namaste, ${user['name'] ?? session.name ?? 'Farmer'}', style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900, letterSpacing: -0.7)),
            const SizedBox(height: 6),
            Text('${user['village'] ?? 'Telangana'} · Your climate workspace', style: const TextStyle(color: Colors.blueGrey)),
            const SizedBox(height: 22),
            Row(children: [Expanded(child: MetricCard(label: 'Farms', value: '${farms.length}', icon: Icons.landscape_outlined)), const SizedBox(width: 12), Expanded(child: MetricCard(label: 'Credits', value: credits.toStringAsFixed(1), icon: Icons.eco_outlined))]),
            const SizedBox(height: 22),
            const SectionTitle('Your farms'),
            if (farms.isEmpty) const EmptyCard(message: 'No farms enrolled yet. Use the web mapping flow to register your first verified boundary.'),
            ...farms.map((item) {
              final farm = item as Map;
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Card(child: ListTile(contentPadding: const EdgeInsets.all(16), leading: const CircleAvatar(backgroundColor: Color(0xFFD1FAE5), child: Icon(Icons.grass, color: CarbonXTheme.forest)), title: Text(farm['name']?.toString() ?? 'Farm', style: const TextStyle(fontWeight: FontWeight.w800)), subtitle: Text('${farm['crop_type'] ?? 'Mixed crop'} · ${farm['area_hectares'] ?? '—'} ha\n${farm['status'] ?? 'PENDING'}'), isThreeLine: true, trailing: Text('${farm['total_credits'] ?? 0}', style: const TextStyle(fontWeight: FontWeight.w900, color: CarbonXTheme.forest))))),
              );
            }),
          ],
        );
      },
    );
  }
}

class MarketplacePage extends StatelessWidget {
  const MarketplacePage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => AsyncPage(
        loader: () => api.get('/marketplace/listings?status=Active&limit=50'),
        builder: (context, data) {
          final rows = data['listings'] is List ? data['listings'] as List : const [];
          final fallback = data['source'] == 'fallback';
          return ListView(padding: const EdgeInsets.all(18), children: [
            const SectionTitle('Carbon marketplace'),
            const Text('Compare transparent farmer-level climate assets.', style: TextStyle(color: Colors.blueGrey)),
            if (fallback) const Padding(padding: EdgeInsets.only(top: 12), child: Chip(avatar: Icon(Icons.info_outline, size: 16), label: Text('SAMPLE DATA · Database offline'))),
            const SizedBox(height: 16),
            ...rows.map((item) { final row = item as Map; return Padding(padding: const EdgeInsets.only(bottom: 12), child: Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Row(children: [Expanded(child: Text(row['crop']?.toString() ?? 'Mixed crop', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900))), Text('₹${row['price_per_credit'] ?? '—'}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: CarbonXTheme.forest))]), const SizedBox(height: 6), Text(row['location']?.toString() ?? 'Telangana', style: const TextStyle(color: Colors.blueGrey)), const SizedBox(height: 14), Row(children: [const Icon(Icons.eco_outlined, size: 17), const SizedBox(width: 5), Text('${row['total_credits'] ?? 0} credits'), const Spacer(), Text(row['listing_model']?.toString() ?? 'Fixed Price')])])))); }),
          ]);
        },
      );
}

class WalletPage extends StatelessWidget {
  const WalletPage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => AsyncPage(
        loader: () => api.get('/wallet'),
        builder: (context, data) {
          final txs = data['transactions'] is List ? data['transactions'] as List : const [];
          return ListView(padding: const EdgeInsets.all(18), children: [
            const SectionTitle('Wallet & settlement ledger'),
            const SizedBox(height: 14),
            Card(color: CarbonXTheme.forest, child: Padding(padding: const EdgeInsets.all(22), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Text('Farmer share total', style: TextStyle(color: Color(0xFFA7F3D0))), const SizedBox(height: 8), Text('₹${data['farmer_share_total'] ?? 0}', style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.w900)), const SizedBox(height: 12), const Text('70% farmer floor · Ledger-recorded settlement', style: TextStyle(color: Colors.white70))]))),
            const SizedBox(height: 20), const SectionTitle('Transactions'),
            if (txs.isEmpty) const EmptyCard(message: 'No settled transactions yet.'),
            ...txs.map((item) { final tx = item as Map; return Card(child: ListTile(leading: const CircleAvatar(child: Icon(Icons.receipt_long_outlined)), title: Text('₹${tx['farmer_inr'] ?? tx['farmer_share'] ?? 0}', style: const TextStyle(fontWeight: FontWeight.w800)), subtitle: Text(tx['ledger_hash']?.toString() ?? 'Ledger pending'), trailing: const Icon(Icons.chevron_right))); }),
          ]);
        },
      );
}

class TrustPage extends StatelessWidget {
  const TrustPage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => AsyncPage(
        loader: () => api.get('/validation/status'),
        builder: (context, data) => ListView(padding: const EdgeInsets.all(18), children: [
          const SectionTitle('Trust center'),
          const SizedBox(height: 14),
          Card(child: Padding(padding: const EdgeInsets.all(20), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [const Icon(Icons.verified_user_outlined, color: CarbonXTheme.emerald, size: 34), const SizedBox(height: 12), Text((data['status'] ?? 'proxy_unvalidated').toString().replaceAll('_', ' ').toUpperCase(), style: const TextStyle(fontWeight: FontWeight.w900)), const SizedBox(height: 8), Text(data['claim']?.toString() ?? 'CarbonX estimates remain proxy estimates until field-validation thresholds pass.', style: const TextStyle(height: 1.45))]))),
          const SizedBox(height: 14),
          const TrustRow(icon: Icons.satellite_alt_outlined, title: 'Satellite MRV', body: 'Sentinel-2 vegetation evidence with provenance.'),
          const TrustRow(icon: Icons.link_rounded, title: 'Hash-chain ledger', body: 'Tamper-evident ISSUE → SALE → SPLIT → RETIRE events.'),
          const TrustRow(icon: Icons.account_balance_outlined, title: 'Transparent economics', body: 'Farmer share floor and conditional FPO split shown before settlement.'),
        ]),
      );
}

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.session});
  final SessionStore session;
  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(18), children: [
        const SectionTitle('Profile'), const SizedBox(height: 16),
        Card(child: Padding(padding: const EdgeInsets.all(20), child: Row(children: [const CircleAvatar(radius: 28, backgroundColor: Color(0xFFD1FAE5), child: Icon(Icons.person, color: CarbonXTheme.forest)), const SizedBox(width: 14), Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(session.name ?? 'CarbonX user', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900)), Text(session.phone ?? 'Authenticated session', style: const TextStyle(color: Colors.blueGrey))]))]))),
        const SizedBox(height: 16),
        const Card(child: Column(children: [ListTile(leading: Icon(Icons.language), title: Text('Language'), subtitle: Text('English · Telugu and Hindi ready')), Divider(height: 1), ListTile(leading: Icon(Icons.privacy_tip_outlined), title: Text('Privacy controls'), subtitle: Text('Manage consent and export on the Trust Center'))])),
        const SizedBox(height: 24),
        OutlinedButton.icon(onPressed: session.clear, icon: const Icon(Icons.logout), label: const Text('Sign out')),
        const SizedBox(height: 14),
        Text('API: ${ApiClient.baseUrl}', textAlign: TextAlign.center, style: const TextStyle(fontSize: 11, color: Colors.blueGrey)),
      ]);
}

class MetricCard extends StatelessWidget {
  const MetricCard({super.key, required this.label, required this.value, required this.icon});
  final String label; final String value; final IconData icon;
  @override
  Widget build(BuildContext context) => Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Icon(icon, color: CarbonXTheme.emerald), const SizedBox(height: 14), Text(value, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900)), Text(label, style: const TextStyle(color: Colors.blueGrey))])));
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key}); final String text;
  @override
  Widget build(BuildContext context) => Text(text, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: -0.5));
}

class EmptyCard extends StatelessWidget {
  const EmptyCard({super.key, required this.message}); final String message;
  @override
  Widget build(BuildContext context) => Card(child: Padding(padding: const EdgeInsets.all(24), child: Column(children: [const Icon(Icons.inbox_outlined, size: 34, color: Colors.blueGrey), const SizedBox(height: 10), Text(message, textAlign: TextAlign.center, style: const TextStyle(color: Colors.blueGrey))])));
}

class TrustRow extends StatelessWidget {
  const TrustRow({super.key, required this.icon, required this.title, required this.body});
  final IconData icon; final String title; final String body;
  @override
  Widget build(BuildContext context) => Padding(padding: const EdgeInsets.only(bottom: 12), child: Card(child: ListTile(contentPadding: const EdgeInsets.all(14), leading: CircleAvatar(backgroundColor: const Color(0xFFD1FAE5), child: Icon(icon, color: CarbonXTheme.forest)), title: Text(title, style: const TextStyle(fontWeight: FontWeight.w800)), subtitle: Text(body))));
}
