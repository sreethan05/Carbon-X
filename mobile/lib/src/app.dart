import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api_client.dart';
import 'session_store.dart';
import 'theme.dart';

List<Map<String, dynamic>> _rows(Object? value) =>
    value is List ? value.whereType<Map<String, dynamic>>().toList() : const [];

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

  @override
  void dispose() {
    phone.dispose();
    otp.dispose();
    super.dispose();
  }

  Future<void> _sendOtp() async {
    if (!RegExp(r'^[6-9]\d{9}$').hasMatch(phone.text.trim())) {
      setState(() => error = 'Enter a valid 10-digit Indian mobile number.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    final result =
        await widget.api.post('/login/send-otp', {'phone': phone.text.trim()});
    if (!mounted) return;
    setState(() {
      busy = false;
      if (result.success) otpSent = true;
      error =
          result.success ? null : result.message ?? 'Could not send the code.';
      final devOtp = result.data['dev_otp']?.toString();
      if (result.success) otp.text = devOtp ?? '';
    });
  }

  Future<void> _login() async {
    if (!RegExp(r'^\d{6}$').hasMatch(otp.text.trim())) {
      setState(() => error = 'Enter the six-digit code.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    final result = await widget.api.post('/login', {
      'phone': phone.text.trim(),
      'otp': otp.text.trim(),
    });
    await _acceptLogin(result);
  }

  Future<void> _demo() async {
    setState(() {
      busy = true;
      error = null;
    });
    final result = await widget.api.post('/demo/login');
    await _acceptLogin(result);
  }

  Future<void> _acceptLogin(ApiResult result) async {
    if (!mounted) return;
    final token = result.data['token'];
    final user = result.data['user'];
    if (result.success && token is String && token.isNotEmpty) {
      try {
        await widget.session.save(
          newToken: token,
          user: user is Map<String, dynamic> ? user : null,
        );
      } catch (_) {
        if (!mounted) return;
        setState(() {
          busy = false;
          error = 'Could not save the session on this device.';
        });
      }
    } else {
      setState(() {
        busy = false;
        error = result.message ?? 'Sign in failed.';
      });
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
                    child: const Icon(Icons.eco_rounded,
                        color: Color(0xFF6EE7B7), size: 34),
                  ),
                  const SizedBox(height: 24),
                  const Text('CarbonX',
                      style: TextStyle(
                          fontSize: 36,
                          fontWeight: FontWeight.w900,
                          letterSpacing: -1.5)),
                  const SizedBox(height: 8),
                  Text('Evidence to income—for every field.',
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(color: Colors.blueGrey.shade600)),
                  const SizedBox(height: 32),
                  TextField(
                    controller: phone,
                    keyboardType: TextInputType.phone,
                    maxLength: 10,
                    readOnly: otpSent || busy,
                    autofillHints: const [
                      AutofillHints.telephoneNumberNational
                    ],
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                    decoration: const InputDecoration(
                        labelText: 'Mobile number',
                        prefixText: '+91 ',
                        counterText: ''),
                  ),
                  if (otpSent) ...[
                    const SizedBox(height: 14),
                    TextField(
                      controller: otp,
                      keyboardType: TextInputType.number,
                      readOnly: busy,
                      autofillHints: const [AutofillHints.oneTimeCode],
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                      maxLength: 6,
                      decoration: const InputDecoration(
                          labelText: '6-digit OTP', counterText: ''),
                    ),
                  ],
                  if (error != null) ...[
                    const SizedBox(height: 12),
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    onPressed: busy ? null : (otpSent ? _login : _sendOtp),
                    icon: busy
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : Icon(otpSent ? Icons.login : Icons.sms_outlined),
                    label: Text(otpSent ? 'Verify and sign in' : 'Send OTP'),
                  ),
                  if (otpSent)
                    Wrap(
                      alignment: WrapAlignment.spaceBetween,
                      children: [
                        TextButton(
                          onPressed: busy
                              ? null
                              : () {
                                  setState(() {
                                    otpSent = false;
                                    otp.clear();
                                    error = null;
                                  });
                                },
                          child: const Text('Change number'),
                        ),
                        TextButton(
                          onPressed: busy ? null : _sendOtp,
                          child: const Text('Resend code'),
                        ),
                      ],
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
        title: const Row(children: [
          Icon(Icons.eco_rounded, color: Color(0xFF6EE7B7)),
          SizedBox(width: 9),
          Text('CarbonX', style: TextStyle(fontWeight: FontWeight.w900))
        ]),
      ),
      body: IndexedStack(index: index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.grid_view_rounded), label: 'Home'),
          NavigationDestination(
              icon: Icon(Icons.storefront_outlined), label: 'Market'),
          NavigationDestination(
              icon: Icon(Icons.account_balance_wallet_outlined),
              label: 'Wallet'),
          NavigationDestination(
              icon: Icon(Icons.verified_user_outlined), label: 'Trust'),
          NavigationDestination(
              icon: Icon(Icons.person_outline), label: 'Profile'),
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

  Future<void> reload() async {
    final request = widget.loader();
    setState(() => future = request);
    await request;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<ApiResult>(
      future: future,
      builder: (context, snapshot) {
        final result = snapshot.data;
        if (snapshot.connectionState == ConnectionState.waiting &&
            result?.success != true) {
          return const Center(child: CircularProgressIndicator());
        }
        if (result == null || !result.success || snapshot.hasError) {
          return Center(
              child: Padding(
                  padding: const EdgeInsets.all(28),
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.cloud_off_rounded, size: 48),
                    const SizedBox(height: 12),
                    Text(result?.message ?? 'Unable to load data.',
                        textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton.tonal(
                        onPressed: reload, child: const Text('Try again'))
                  ])));
        }
        return RefreshIndicator(
          onRefresh: reload,
          child: widget.builder(context, result.data),
        );
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
        final farms = _rows(data['farms']);
        final credits = farms.fold<double>(0, (sum, item) {
          final value = item['total_credits'];
          return sum + (value is num ? value.toDouble() : 0);
        });
        return ListView(
          padding: const EdgeInsets.all(18),
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            Text('Namaste, ${user['name'] ?? session.name ?? 'Farmer'}',
                style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.7)),
            if (user['village'] case final String village)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(village,
                    style: const TextStyle(color: Colors.blueGrey)),
              ),
            if (user['demo'] == true)
              const Align(
                alignment: Alignment.centerLeft,
                child: Chip(label: Text('Demo farms')),
              ),
            const SizedBox(height: 22),
            Row(children: [
              Expanded(
                  child: MetricCard(
                      label: 'Farms',
                      value: '${farms.length}',
                      icon: Icons.landscape_outlined)),
              const SizedBox(width: 12),
              Expanded(
                  child: MetricCard(
                      label: 'Estimated credits',
                      value: credits.toStringAsFixed(1),
                      icon: Icons.eco_outlined))
            ]),
            const SizedBox(height: 22),
            const SectionTitle('Your farms'),
            if (farms.isEmpty)
              const EmptyCard(
                  message:
                      'No farms enrolled yet. Use the web mapping flow to register your first verified boundary.'),
            ...farms.map((farm) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Card(
                  child: ListTile(
                    contentPadding: const EdgeInsets.all(16),
                    leading: const CircleAvatar(
                      backgroundColor: Color(0xFFD1FAE5),
                      child: Icon(Icons.grass, color: CarbonXTheme.forest),
                    ),
                    title: Text(
                      farm['name']?.toString() ?? 'Farm',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    subtitle: Text(
                      '${farm['crop_type'] ?? 'Mixed crop'} · ${farm['area_hectares'] ?? '—'} ha'
                      '\n${farm['status'] ?? 'PENDING'} · ${farm['total_credits'] ?? 0} estimated credits',
                    ),
                    isThreeLine: true,
                  ),
                ),
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
          final rows = _rows(data['listings']);
          final fallback = data['source'] == 'fallback';
          return ListView(
            padding: const EdgeInsets.all(18),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              const SectionTitle('Carbon marketplace'),
              if (fallback)
                const Padding(
                  padding: EdgeInsets.only(top: 12),
                  child: Text('Sample listings · Database offline'),
                ),
              const SizedBox(height: 16),
              if (rows.isEmpty)
                const EmptyCard(message: 'No active listings right now.'),
              ...rows.map((row) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              row['crop']?.toString() ?? 'Mixed crop',
                              style: const TextStyle(
                                  fontSize: 18, fontWeight: FontWeight.w900),
                            ),
                            if (row['location'] case final String location)
                              Text(location),
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 14,
                              runSpacing: 6,
                              children: [
                                if (row['price_per_credit']
                                    case final num price)
                                  Text(
                                      '₹${price.toStringAsFixed(2)} per credit'),
                                if (row['total_credits'] case final num credits)
                                  Text('$credits estimated credits'),
                                if (row['listing_model']
                                    case final String model)
                                  Text(model),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  )),
            ],
          );
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
          final transactions = _rows(data['transactions']);
          final farmerShare = data['farmer_share_total'];
          return ListView(
            padding: const EdgeInsets.all(18),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              const SectionTitle('Wallet & settlement ledger'),
              if (data['demo_mode'] == true) const Text('Demo wallet'),
              const SizedBox(height: 14),
              Card(
                color: CarbonXTheme.forest,
                child: Padding(
                  padding: const EdgeInsets.all(22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('Farmer share total',
                          style: TextStyle(color: Color(0xFFA7F3D0))),
                      const SizedBox(height: 8),
                      Text(
                        farmerShare is num
                            ? '₹${farmerShare.toStringAsFixed(2)}'
                            : 'Unavailable',
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 32,
                            fontWeight: FontWeight.w900),
                      ),
                      if (data['payout_note'] case final String note)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: Text(note,
                              style: const TextStyle(color: Colors.white70)),
                        ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 20),
              const SectionTitle('Transactions'),
              if (transactions.isEmpty)
                const EmptyCard(message: 'No transactions yet.'),
              ...transactions.map((tx) {
                final share = tx['farmer_share'];
                final status = tx['status']?.toString().replaceAll('_', ' ');
                final hash = tx['ledger_hash'];
                final details = [
                  if (tx['date'] case final String date when date.isNotEmpty)
                    date,
                  if (status != null) status,
                  if (hash is String && hash.isNotEmpty) 'Ledger hash: $hash',
                ];
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Card(
                    child: ListTile(
                      leading: const Icon(Icons.receipt_long_outlined),
                      title: Text(share is num
                          ? '₹${share.toStringAsFixed(2)}'
                          : 'Share unavailable'),
                      subtitle:
                          details.isEmpty ? null : Text(details.join('\n')),
                    ),
                  ),
                );
              }),
            ],
          );
        },
      );
}

class TrustPage extends StatelessWidget {
  const TrustPage({super.key, required this.api});
  final ApiClient api;
  @override
  Widget build(BuildContext context) => AsyncPage(
        loader: () => api.get('/validation/status'),
        builder: (context, data) => ListView(
            padding: const EdgeInsets.all(18),
            physics: const AlwaysScrollableScrollPhysics(),
            children: [
              const SectionTitle('Trust center'),
              const SizedBox(height: 14),
              Card(
                  child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.verified_user_outlined,
                                color: CarbonXTheme.emerald, size: 34),
                            const SizedBox(height: 12),
                            Text(
                                data['public_label']?.toString() ??
                                    'Validation status unavailable.',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w900))
                          ]))),
              const SizedBox(height: 14),
              const TrustRow(
                  icon: Icons.satellite_alt_outlined,
                  title: 'Satellite MRV',
                  body: 'Sentinel-2 vegetation evidence with provenance.'),
              const TrustRow(
                  icon: Icons.link_rounded,
                  title: 'Hash-chain ledger',
                  body: 'Tamper-evident ISSUE → SALE → SPLIT → RETIRE events.'),
              const TrustRow(
                  icon: Icons.account_balance_outlined,
                  title: 'Transparent economics',
                  body:
                      'Farmer share floor and conditional FPO split shown before settlement.'),
            ]),
      );
}

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key, required this.session});
  final SessionStore session;
  @override
  Widget build(BuildContext context) =>
      ListView(padding: const EdgeInsets.all(18), children: [
        const SectionTitle('Profile'),
        const SizedBox(height: 16),
        Card(
            child: Padding(
                padding: const EdgeInsets.all(20),
                child: Row(children: [
                  const CircleAvatar(
                      radius: 28,
                      backgroundColor: Color(0xFFD1FAE5),
                      child: Icon(Icons.person, color: CarbonXTheme.forest)),
                  const SizedBox(width: 14),
                  Expanded(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Text(session.name ?? 'CarbonX user',
                            style: const TextStyle(
                                fontSize: 18, fontWeight: FontWeight.w900)),
                        Text(session.phone ?? 'Authenticated session',
                            style: const TextStyle(color: Colors.blueGrey))
                      ]))
                ]))),
        const SizedBox(height: 24),
        OutlinedButton.icon(
            onPressed: session.clear,
            icon: const Icon(Icons.logout),
            label: const Text('Sign out')),
      ]);
}

class MetricCard extends StatelessWidget {
  const MetricCard(
      {super.key,
      required this.label,
      required this.value,
      required this.icon});
  final String label;
  final String value;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icon, color: CarbonXTheme.emerald),
            const SizedBox(height: 14),
            Text(value,
                style:
                    const TextStyle(fontSize: 26, fontWeight: FontWeight.w900)),
            Text(label, style: const TextStyle(color: Colors.blueGrey))
          ])));
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Text(text,
      style: const TextStyle(
          fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: -0.5));
}

class EmptyCard extends StatelessWidget {
  const EmptyCard({super.key, required this.message});
  final String message;
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(children: [
            const Icon(Icons.inbox_outlined, size: 34, color: Colors.blueGrey),
            const SizedBox(height: 10),
            Text(message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.blueGrey))
          ])));
}

class TrustRow extends StatelessWidget {
  const TrustRow(
      {super.key, required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
          child: ListTile(
              contentPadding: const EdgeInsets.all(14),
              leading: CircleAvatar(
                  backgroundColor: const Color(0xFFD1FAE5),
                  child: Icon(icon, color: CarbonXTheme.forest)),
              title: Text(title,
                  style: const TextStyle(fontWeight: FontWeight.w800)),
              subtitle: Text(body))));
}
