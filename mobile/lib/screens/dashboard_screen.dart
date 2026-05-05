import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:fl_chart/fl_chart.dart';
import '../theme/app_theme.dart';
import '../services/api_service.dart';
import '../models/user_model.dart';
import '../widgets/tt_logo.dart';
import 'settings_screen.dart';

// ════════════════════════════════════════════════════════════
//  Dashboard — identique à user_dashboard.html
//  Graphique camembert · Top Issues · Filtres historique
// ════════════════════════════════════════════════════════════

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  int _selectedIndex = 0;

  // Filtre historique (onglet Historique)
  String _historyFilter = 'all'; // all | resolue | en_cours | transferee

  UserModel?                _user;
  UserStats?                _stats;
  List<ConversationSummary> _history    = [];
  List<TopIssue>            _topIssues  = [];

  bool    _loadingStats    = true;
  bool    _loadingHistory  = true;
  bool    _loadingTopIssues = true;
  String? _statsError;
  String? _historyError;

  final _api = ApiService();

  // Couleurs du graphique camembert
  static const _chartColors = [
    TTColors.purple,
    TTColors.green,
    TTColors.orange,
    TTColors.teal,
    Color(0xFFE8002D),
    Color(0xFF7B3FDE),
  ];

  @override
  void initState() {
    super.initState();
    _loadAll();
  }

  Future<void> _loadAll() async {
    await Future.wait([
      _loadUser(),
      _loadStats(),
      _loadHistory(),
      _loadTopIssues(),
    ]);
  }

  Future<void> _loadUser() async {
    final user = await _api.getCachedUser();
    if (mounted) setState(() => _user = user);
  }

  Future<void> _loadStats() async {
    if (!mounted) return;
    setState(() { _loadingStats = true; _statsError = null; });
    try {
      final stats = await _api.getStats();
      if (mounted) setState(() { _stats = stats; _loadingStats = false; });
    } catch (e) {
      if (mounted) setState(() { _loadingStats = false; _statsError = e.toString(); });
    }
  }

  Future<void> _loadHistory() async {
    if (!mounted) return;
    setState(() { _loadingHistory = true; _historyError = null; });
    try {
      final hist = await _api.getHistory();
      if (mounted) setState(() { _history = hist; _loadingHistory = false; });
    } catch (e) {
      if (mounted) setState(() { _loadingHistory = false; _historyError = e.toString(); });
    }
  }

  Future<void> _loadTopIssues() async {
    if (!mounted) return;
    setState(() => _loadingTopIssues = true);
    try {
      final issues = await _api.getTopIssues();
      if (mounted) setState(() { _topIssues = issues; _loadingTopIssues = false; });
    } catch (_) {
      if (mounted) setState(() => _loadingTopIssues = false);
    }
  }

  Future<void> _logout() async {
    await _api.logout();
    if (mounted) context.go('/login');
  }

  Future<void> _startNewChat() async {
    final convId = await _api.newConversation();
    if (!mounted) return;
    context.push('/chat', extra: {'convSessionId': convId ?? ''});
  }

  void _openConversation(ConversationSummary conv) {
    context.push('/chat', extra: {'convSessionId': '', 'convId': conv.convId});
  }

  // Filtre conversations
  List<ConversationSummary> get _filteredHistory {
    if (_historyFilter == 'all') return _history;
    return _history.where((c) {
      final s = c.status.toLowerCase();
      return switch (_historyFilter) {
        'resolue'    => s == 'resolue'    || s == 'resolved',
        'en_cours'   => s == 'en_cours'   || s == 'open' || s == 'in_progress',
        'transferee' => s == 'transferee' || s == 'transferred',
        _            => true,
      };
    }).toList();
  }

  // ════════════════════════════════════════════════════════
  //  BUILD
  // ════════════════════════════════════════════════════════
  @override
  Widget build(BuildContext context) {
    final isSmall = MediaQuery.of(context).size.width < 768;

    return Scaffold(
      backgroundColor: TTColors.gray,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(isSmall),
            Expanded(
              child: isSmall
                  ? _buildContent()
                  : Row(children: [
                      _buildSidebar(),
                      Expanded(child: _buildContent()),
                    ]),
            ),
          ],
        ),
      ),
      drawer:            isSmall ? Drawer(child: _buildSidebar()) : null,
      bottomNavigationBar: isSmall ? _buildBottomNav() : null,
    );
  }

  // ── Header ─────────────────────────────────────────────────
  Widget _buildHeader(bool isSmall) {
    return Container(
      height: 64,
      decoration: const BoxDecoration(
        color: TTColors.white,
        border: Border(bottom: BorderSide(color: TTColors.purple, width: 3)),
        boxShadow: [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          if (isSmall) Builder(builder: (ctx) => IconButton(
            icon: const Icon(Icons.menu_rounded, color: TTColors.purple),
            onPressed: () => Scaffold.of(ctx).openDrawer(),
          )),
          const TTLogo(size: 38, onDark: false, radius: 8),
          const SizedBox(width: 10),
          if (!isSmall) const Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Mon Espace TT',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: TTColors.purple, fontFamily: 'Cairo')),
              Text('Tunisie Telecom',
                style: TextStyle(fontSize: 10, color: TTColors.muted, fontFamily: 'Cairo')),
            ],
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: const Color(0xFFF0FDF4),
              border: Border.all(color: const Color(0xFF86EFAC)),
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Row(children: [
              Icon(Icons.circle, color: Color(0xFF16A34A), size: 8),
              SizedBox(width: 6),
              Text('En ligne', style: TextStyle(fontSize: 11, color: Color(0xFF16A34A), fontWeight: FontWeight.w600, fontFamily: 'Cairo')),
            ]),
          ),
          const SizedBox(width: 12),
          GestureDetector(
            onTap: () => setState(() => _selectedIndex = 2),
            child: CircleAvatar(
              radius: 18,
              backgroundColor: TTColors.purple,
              child: Text(
                _user != null && _user!.prenom.isNotEmpty ? _user!.prenom[0].toUpperCase() : '?',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 14, fontFamily: 'Cairo'),
              ),
            ),
          ),
          const SizedBox(width: 6),
          IconButton(
            icon: const Icon(Icons.settings_rounded, color: TTColors.muted, size: 20),
            tooltip: 'Paramètres réseau',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout_rounded, color: TTColors.muted, size: 20),
            tooltip: 'Déconnexion',
            onPressed: _logout,
          ),
        ],
      ),
    );
  }

  // ── Sidebar ────────────────────────────────────────────────
  Widget _buildSidebar() {
    return Container(
      width: 240,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter, end: Alignment.bottomCenter,
          colors: [TTColors.purpleDark, TTColors.purple],
        ),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.18), blurRadius: 14)],
      ),
      child: Column(
        children: [
          // Avatar utilisateur
          Container(
            padding: const EdgeInsets.all(20),
            child: Column(children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: Colors.white.withOpacity(0.2),
                child: Text(
                  _user != null && _user!.prenom.isNotEmpty ? _user!.prenom[0].toUpperCase() : '?',
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: Colors.white, fontFamily: 'Cairo'),
                ),
              ),
              const SizedBox(height: 10),
              Text(_user?.fullName ?? '…',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: Colors.white, fontFamily: 'Cairo'),
                textAlign: TextAlign.center),
              const SizedBox(height: 2),
              Text(_user?.email ?? '',
                style: TextStyle(fontSize: 11, color: Colors.white.withOpacity(0.7), fontFamily: 'Cairo'),
                textAlign: TextAlign.center, overflow: TextOverflow.ellipsis),
            ]),
          ),
          const Divider(color: Colors.white24, height: 1),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                _sideNavItem(Icons.home_rounded,                'Accueil',           0),
                _sideNavItem(Icons.chat_bubble_outline_rounded, 'Assistant Virtuel', -1,
                  onTap: _startNewChat, badge: true),
                _sideNavItem(Icons.history_rounded,             'Mes Réclamations',  1),
                _sideNavItem(Icons.person_outline_rounded,      'Mon Profil',        2),
                const Divider(color: Colors.white24, indent: 16, endIndent: 16),
                _sideNavItem(Icons.logout_rounded,              'Déconnexion',       -2, onTap: _logout),
              ],
            ),
          ),
          // Footer hotline
          Container(
            margin: const EdgeInsets.all(12),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.08),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(children: [
              Text('Besoin d\'aide ?', style: TextStyle(fontSize: 11, color: Colors.white.withOpacity(0.6), fontFamily: 'Cairo')),
              const SizedBox(height: 4),
              const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(Icons.phone_rounded, color: TTColors.teal, size: 14),
                SizedBox(width: 6),
                Text('1298', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: TTColors.teal, fontFamily: 'Cairo')),
              ]),
              Text('Ou le 71 001 298', style: TextStyle(fontSize: 10, color: Colors.white.withOpacity(0.5), fontFamily: 'Cairo')),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _sideNavItem(IconData icon, String label, int index,
      {VoidCallback? onTap, bool badge = false}) {
    final isActive = _selectedIndex == index;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: isActive ? Colors.white.withOpacity(0.18) : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        border: isActive ? Border(left: BorderSide(color: TTColors.teal, width: 3)) : null,
      ),
      child: ListTile(
        dense: true,
        leading: Icon(icon, size: 20, color: isActive ? Colors.white : Colors.white70),
        title: Text(label, style: TextStyle(
          fontSize: 13, fontFamily: 'Cairo',
          fontWeight: isActive ? FontWeight.w700 : FontWeight.w500,
          color: isActive ? Colors.white : Colors.white70,
        )),
        trailing: badge
            ? Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(color: TTColors.teal, borderRadius: BorderRadius.circular(12)),
                child: const Text('Nouveau', style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700, fontFamily: 'Cairo')))
            : null,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
        onTap: onTap ?? () => setState(() => _selectedIndex = index),
      ),
    );
  }

  Widget _buildBottomNav() {
    final idx = _selectedIndex < 0 ? 0 : (_selectedIndex > 2 ? 0 : _selectedIndex);
    return BottomNavigationBar(
      currentIndex: idx,
      onTap: (i) => setState(() => _selectedIndex = i),
      selectedItemColor: TTColors.purple,
      unselectedItemColor: TTColors.muted,
      selectedLabelStyle: const TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.w600, fontSize: 11),
      unselectedLabelStyle: const TextStyle(fontFamily: 'Cairo', fontSize: 11),
      items: const [
        BottomNavigationBarItem(icon: Icon(Icons.home_rounded),    label: 'Accueil'),
        BottomNavigationBarItem(icon: Icon(Icons.history_rounded), label: 'Réclamations'),
        BottomNavigationBarItem(icon: Icon(Icons.person_rounded),  label: 'Profil'),
      ],
    );
  }

  // ── Contenu principal ──────────────────────────────────────
  Widget _buildContent() {
    return IndexedStack(
      index: _selectedIndex < 0 ? 0 : (_selectedIndex > 2 ? 0 : _selectedIndex),
      children: [
        _buildHomeTab(),
        _buildHistoryTab(),
        _buildProfileTab(),
      ],
    );
  }

  // ══════════════════════════════════════════════════════════
  //  ONGLET ACCUEIL
  // ══════════════════════════════════════════════════════════
  Widget _buildHomeTab() {
    return RefreshIndicator(
      color: TTColors.purple,
      onRefresh: _loadAll,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

          // ── Bannière bienvenue ─────────────────────────
          _buildWelcomeBanner(),
          const SizedBox(height: 24),

          // ── Statistiques ──────────────────────────────
          _sectionTitle('Mes statistiques', trailing: _loadingStats
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: TTColors.purple))
              : IconButton(icon: const Icon(Icons.refresh_rounded, size: 18, color: TTColors.purple), onPressed: _loadStats)),
          const SizedBox(height: 12),
          if (_statsError != null)
            _buildErrorBanner('Erreur stats : $_statsError', _loadStats)
          else
            _buildStatsGrid(),
          const SizedBox(height: 24),

          // ── Principaux problèmes + Camembert ──────────
          _buildIssuesAndChart(),
          const SizedBox(height: 24),

          // ── Dernières réclamations ────────────────────
          _sectionTitle('Dernières réclamations', trailing: _loadingHistory
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: TTColors.purple))
              : TextButton(
                  onPressed: () => setState(() => _selectedIndex = 1),
                  child: const Text('Voir tout', style: TextStyle(fontSize: 12, color: TTColors.purple, fontFamily: 'Cairo')))),
          const SizedBox(height: 10),
          _buildRecentHistory(),
        ]),
      ),
    );
  }

  Widget _buildWelcomeBanner() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [TTColors.purpleDark, TTColors.purple, TTColors.purpleLight],
          begin: Alignment.topLeft, end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.35), blurRadius: 20, offset: const Offset(0, 8))],
      ),
      child: Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Bonjour, ${_user?.prenom ?? ''} ! 👋',
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Colors.white, fontFamily: 'Cairo')),
          const SizedBox(height: 6),
          const Text('Bienvenue dans votre espace personnel Tunisie Telecom',
            style: TextStyle(fontSize: 13, color: Colors.white70, fontFamily: 'Cairo')),
          const SizedBox(height: 18),
          ElevatedButton.icon(
            onPressed: _startNewChat,
            icon: const Icon(Icons.chat_bubble_outline_rounded, size: 16),
            label: const Text('Nouvelle réclamation', style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.w700, fontSize: 13)),
            style: ElevatedButton.styleFrom(
              backgroundColor: TTColors.teal,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              elevation: 0,
            ),
          ),
        ])),
        const SizedBox(width: 12),
        const Icon(Icons.support_agent_rounded, size: 64, color: Colors.white24),
      ]),
    );
  }

  Widget _buildStatsGrid() {
    final total       = _stats?.totalConversations ?? 0;
    final resolved    = _stats?.resolvedConversations ?? 0;
    final transferred = _stats?.transferredConversations ?? 0;
    final enCours     = total - resolved - transferred;
    final rating      = _stats?.avgRating ?? 0.0;

    String pct(int v) => total > 0 ? '${(v / total * 100).round()}%' : '0%';

    final cards = [
      _statCard('Total réclamations', total.toString(),  Icons.folder_open_rounded,     TTColors.purple,  '100%'),
      _statCard('Résolues',           resolved.toString(), Icons.check_circle_outline_rounded, TTColors.green, pct(resolved)),
      _statCard('Transférées',        transferred.toString(), Icons.headset_mic_outlined,   TTColors.orange, pct(transferred)),
      _statCard('En cours',           enCours > 0 ? enCours.toString() : '0', Icons.pending_outlined, TTColors.teal, pct(enCours > 0 ? enCours : 0)),
      _statCard('Satisfaction',
        rating > 0 ? '${rating.toStringAsFixed(1)}/5' : '—',
        Icons.star_outline_rounded,
        const Color(0xFFF59E0B),
        rating > 0 ? '${(_stats?.totalConversations ?? 0)} avis' : 'Aucun avis'),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final int cols;
        final double ratio;
        if (w >= 1100) {
          cols  = 5;   // Desktop large : une ligne de 5 cartes
          ratio = 1.45;
        } else if (w >= 750) {
          cols  = 3;   // Tablette / bureau moyen
          ratio = 1.55;
        } else if (w >= 420) {
          cols  = 2;   // Téléphone normal
          ratio = 1.50;
        } else {
          cols  = 1;   // Petit écran
          ratio = 3.20;
        }
        return GridView.count(
          crossAxisCount:   cols,
          crossAxisSpacing: 12,
          mainAxisSpacing:  12,
          shrinkWrap:       true,
          physics:          const NeverScrollableScrollPhysics(),
          childAspectRatio: ratio,
          children:         cards,
        );
      },
    );
  }

  Widget _statCard(String label, String value, IconData icon, Color color, String sub) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: TTColors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: color, width: 4)),
        boxShadow: [BoxShadow(color: color.withOpacity(0.08), blurRadius: 12, offset: const Offset(0, 4))],
      ),
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
          child: Icon(icon, color: color, size: 20),
        ),
        const SizedBox(width: 10),
        Expanded(child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: TTColors.text, fontFamily: 'Cairo')),
            Text(label, style: const TextStyle(fontSize: 10, color: TTColors.muted, fontFamily: 'Cairo')),
            const SizedBox(height: 3),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(color: color.withOpacity(0.1), borderRadius: BorderRadius.circular(99)),
              child: Text(sub, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color, fontFamily: 'Cairo')),
            ),
          ],
        )),
      ]),
    );
  }

  // ── Principaux problèmes + Camembert ─────────────────────
  Widget _buildIssuesAndChart() {
    final isWide = MediaQuery.of(context).size.width > 700;
    final content = [
      _buildTopIssuesList(),
      const SizedBox(width: 12, height: 12),
      _buildPieChartCard(),
    ];

    return isWide
        ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: content[0]),
            content[1],
            Expanded(child: content[2]),
          ])
        : Column(children: [content[0], content[1], content[2]]);
  }

  Widget _buildTopIssuesList() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: TTColors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border(left: const BorderSide(color: TTColors.purple, width: 4)),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.07), blurRadius: 10)],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.list_alt_rounded, color: TTColors.purple, size: 18),
          SizedBox(width: 8),
          Text('Principaux problèmes',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
        ]),
        const SizedBox(height: 12),
        if (_loadingTopIssues)
          const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator(color: TTColors.purple, strokeWidth: 2)))
        else if (_topIssues.isEmpty)
          Center(child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(children: [
              const Icon(Icons.inbox_outlined, color: TTColors.border, size: 36),
              const SizedBox(height: 8),
              const Text('Aucun problème enregistré',
                style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
            ]),
          ))
        else
          Column(
            children: _topIssues.take(5).toList().asMap().entries.map((e) {
              final color = _chartColors[e.key % _chartColors.length];
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: TTColors.purpleBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(children: [
                  Container(width: 8, height: 8, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
                  const SizedBox(width: 10),
                  Expanded(child: Text(e.value.label,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: TTColors.text, fontFamily: 'Cairo'),
                    overflow: TextOverflow.ellipsis)),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                    decoration: BoxDecoration(color: TTColors.white, borderRadius: BorderRadius.circular(99)),
                    child: Text(e.value.count.toString(),
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color, fontFamily: 'Cairo')),
                  ),
                ]),
              );
            }).toList(),
          ),
      ]),
    );
  }

  Widget _buildPieChartCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: TTColors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border(left: const BorderSide(color: TTColors.purple, width: 4)),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.07), blurRadius: 10)],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.pie_chart_outline_rounded, color: TTColors.purple, size: 18),
          SizedBox(width: 8),
          Text('Répartition des réclamations',
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
        ]),
        const SizedBox(height: 12),
        SizedBox(
          height: 240,
          child: _loadingTopIssues
              ? const Center(child: CircularProgressIndicator(color: TTColors.purple, strokeWidth: 2))
              : _topIssues.isEmpty
                  ? Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      const Icon(Icons.pie_chart_outline_rounded, color: TTColors.border, size: 48),
                      const SizedBox(height: 8),
                      const Text('Aucune donnée', style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
                    ]))
                  : _buildPieChart(),
        ),
        if (!_loadingTopIssues && _topIssues.isNotEmpty) ...[
          const SizedBox(height: 12),
          _buildChartLegend(),
        ],
      ]),
    );
  }

  Widget _buildPieChart() {
    final total = _topIssues.fold<int>(0, (a, b) => a + b.count);
    return PieChart(
      PieChartData(
        sections: _topIssues.take(6).toList().asMap().entries.map((e) {
          final color = _chartColors[e.key % _chartColors.length];
          final pct   = total > 0 ? (e.value.count / total * 100).round() : 0;
          return PieChartSectionData(
            color:  color,
            value:  e.value.count.toDouble(),
            title:  '$pct%',
            radius: 80,
            titleStyle: const TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700,
              color: Colors.white, fontFamily: 'Cairo',
            ),
          );
        }).toList(),
        centerSpaceRadius: 36,
        sectionsSpace: 2,
        borderData: FlBorderData(show: false),
      ),
    );
  }

  Widget _buildChartLegend() {
    return Wrap(
      spacing: 12, runSpacing: 8,
      children: _topIssues.take(6).toList().asMap().entries.map((e) {
        final color = _chartColors[e.key % _chartColors.length];
        return Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
          const SizedBox(width: 5),
          Text(e.value.label.length > 16 ? '${e.value.label.substring(0, 14)}…' : e.value.label,
            style: const TextStyle(fontSize: 11, color: TTColors.text, fontFamily: 'Cairo')),
        ]);
      }).toList(),
    );
  }

  Widget _buildRecentHistory() {
    if (_loadingHistory) {
      return const Center(child: Padding(
        padding: EdgeInsets.all(20),
        child: CircularProgressIndicator(color: TTColors.purple),
      ));
    }
    if (_historyError != null) return _buildErrorBanner('Erreur : $_historyError', _loadHistory);
    if (_history.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: TTColors.white, borderRadius: BorderRadius.circular(12)),
        child: const Center(child: Text('Aucune conversation pour le moment',
          style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo'))),
      );
    }
    return Column(
      children: _history.take(3).map((c) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: _convCard(c),
      )).toList(),
    );
  }

  // ══════════════════════════════════════════════════════════
  //  ONGLET HISTORIQUE
  // ══════════════════════════════════════════════════════════
  Widget _buildHistoryTab() {
    return RefreshIndicator(
      color: TTColors.purple,
      onRefresh: _loadHistory,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // En-tête + rafraîchir
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
          child: Row(children: [
            const Text('Historique des réclamations',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
            const Spacer(),
            TextButton.icon(
              onPressed: _loadHistory,
              icon: const Icon(Icons.refresh_rounded, size: 16, color: TTColors.purple),
              label: const Text('Actualiser', style: TextStyle(fontSize: 12, color: TTColors.purple, fontFamily: 'Cairo')),
            ),
          ]),
        ),

        // ── Boutons filtres (Toutes / Résolues / En cours / Transférées) ──
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(children: [
            _filterBtn('Toutes',      'all'),
            _filterBtn('✅ Résolues', 'resolue'),
            _filterBtn('🔄 En cours', 'en_cours'),
            _filterBtn('🎧 Transférées', 'transferee'),
          ]),
        ),

        // Compteur
        if (!_loadingHistory && _filteredHistory.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Text('${_filteredHistory.length} conversation${_filteredHistory.length > 1 ? "s" : ""}',
              style: const TextStyle(fontSize: 12, color: TTColors.muted, fontFamily: 'Cairo')),
          ),

        const SizedBox(height: 8),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: _buildHistoryList(),
          ),
        ),
      ]),
    );
  }

  Widget _filterBtn(String label, String value) {
    final isActive = _historyFilter == value;
    return GestureDetector(
      onTap: () => setState(() => _historyFilter = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
        decoration: BoxDecoration(
          color: isActive ? TTColors.purple : TTColors.white,
          border: Border.all(color: isActive ? TTColors.purple : TTColors.border, width: 1.5),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(label, style: TextStyle(
          fontSize: 12, fontWeight: FontWeight.w600, fontFamily: 'Cairo',
          color: isActive ? Colors.white : TTColors.muted,
        )),
      ),
    );
  }

  Widget _buildHistoryList() {
    if (_loadingHistory) {
      return const Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        CircularProgressIndicator(color: TTColors.purple),
        SizedBox(height: 16),
        Text('Chargement de vos conversations…',
          style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
      ]));
    }
    if (_historyError != null) {
      return Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.error_outline_rounded, color: TTColors.red, size: 48),
        const SizedBox(height: 12),
        Text('Erreur : $_historyError',
          style: const TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo'),
          textAlign: TextAlign.center),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          onPressed: _loadHistory,
          icon: const Icon(Icons.refresh_rounded, size: 18),
          label: const Text('Réessayer', style: TextStyle(fontFamily: 'Cairo')),
          style: ElevatedButton.styleFrom(backgroundColor: TTColors.purple),
        ),
      ]));
    }
    final list = _filteredHistory;
    if (list.isEmpty) {
      return Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.inbox_outlined, size: 56, color: TTColors.border),
        const SizedBox(height: 12),
        Text(
          _historyFilter == 'all'
              ? 'Aucune conversation pour le moment'
              : 'Aucune réclamation dans cette catégorie',
          style: const TextStyle(fontSize: 14, color: TTColors.muted, fontFamily: 'Cairo'),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          onPressed: _startNewChat,
          icon: const Icon(Icons.add_rounded, size: 18),
          label: const Text('Commencer un chat', style: TextStyle(fontFamily: 'Cairo')),
          style: ElevatedButton.styleFrom(backgroundColor: TTColors.purple),
        ),
      ]));
    }
    return ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: list.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (_, i) => _convCard(list[i]),
    );
  }

  // ── Carte conversation ─────────────────────────────────────
  Widget _convCard(ConversationSummary conv) {
    final statusColor = switch (conv.status.toLowerCase()) {
      'resolue'   || 'resolved'     => TTColors.green,
      'transferee'|| 'transferred'  => TTColors.orange,
      'fermee'    || 'closed'       => TTColors.muted,
      _                             => TTColors.teal,
    };
    final statusLabel = switch (conv.status.toLowerCase()) {
      'resolue'   || 'resolved'     => 'Résolue',
      'transferee'|| 'transferred'  => 'Transférée',
      'fermee'    || 'closed'       => 'Fermée',
      _                             => 'En cours',
    };
    String dateStr = '';
    if (conv.createdAt != null) {
      try { dateStr = DateFormat('dd/MM/yyyy HH:mm', 'fr').format(conv.createdAt!); } catch (_) {}
    }
    return GestureDetector(
      onTap: () => _openConversation(conv),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: TTColors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: statusColor, width: 4)),
          boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.06), blurRadius: 10, offset: const Offset(0, 3))],
        ),
        child: Row(children: [
          Container(
            width: 40, height: 40,
            decoration: BoxDecoration(color: statusColor.withOpacity(0.1), borderRadius: BorderRadius.circular(10)),
            child: Icon(Icons.chat_bubble_outline_rounded, color: statusColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
              conv.firstMessage.isNotEmpty ? conv.firstMessage : 'Conversation sans titre',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo'),
              maxLines: 1, overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 3),
            Text(
              '${conv.messageCount} msg${conv.messageCount > 1 ? "s" : ""}${dateStr.isNotEmpty ? "  ·  $dateStr" : ""}',
              style: const TextStyle(fontSize: 11, color: TTColors.muted, fontFamily: 'Cairo'),
            ),
          ])),
          const SizedBox(width: 8),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: statusColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: statusColor.withOpacity(0.3)),
              ),
              child: Text(statusLabel,
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: statusColor, fontFamily: 'Cairo')),
            ),
            if (conv.rating != null && conv.rating! > 0) ...[
              const SizedBox(height: 4),
              Row(mainAxisSize: MainAxisSize.min, children: [
                const Icon(Icons.star_rounded, color: Color(0xFFF59E0B), size: 13),
                Text(conv.rating!.toStringAsFixed(1),
                  style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: Color(0xFFF59E0B), fontFamily: 'Cairo')),
              ]),
            ],
            const SizedBox(height: 4),
            const Row(mainAxisSize: MainAxisSize.min, children: [
              Text('Voir détails', style: TextStyle(fontSize: 10, color: TTColors.purple, fontFamily: 'Cairo', fontWeight: FontWeight.w600)),
              Icon(Icons.chevron_right_rounded, color: TTColors.purple, size: 14),
            ]),
          ]),
        ]),
      ),
    );
  }

  // ══════════════════════════════════════════════════════════
  //  ONGLET PROFIL
  // ══════════════════════════════════════════════════════════
  Widget _buildProfileTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(children: [
        // Avatar + nom
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [TTColors.purpleDark, TTColors.purple]),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(children: [
            CircleAvatar(
              radius: 36, backgroundColor: Colors.white,
              child: Text(
                _user != null && _user!.prenom.isNotEmpty ? _user!.prenom[0].toUpperCase() : '?',
                style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w900, color: TTColors.purple, fontFamily: 'Cairo'),
              ),
            ),
            const SizedBox(height: 12),
            Text(_user?.fullName ?? '…',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Colors.white, fontFamily: 'Cairo')),
            const SizedBox(height: 4),
            Text(_user?.email ?? '',
              style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.75), fontFamily: 'Cairo')),
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(color: Colors.white.withOpacity(0.15), borderRadius: BorderRadius.circular(20)),
              child: const Text('Client TT',
                style: TextStyle(fontSize: 11, color: Colors.white, fontFamily: 'Cairo', fontWeight: FontWeight.w600)),
            ),
          ]),
        ),
        const SizedBox(height: 20),

        // Infos personnelles
        _infoCard('Informations personnelles', [
          (Icons.person_outline,  'Nom',       _user?.nom ?? ''),
          (Icons.person_outline,  'Prénom',    _user?.prenom ?? ''),
          (Icons.email_outlined,  'Email',     _user?.email ?? ''),
          (Icons.phone_outlined,  'Téléphone', _user?.telephone ?? ''),
        ]),
        const SizedBox(height: 16),

        // Statistiques
        _infoCard('Mes statistiques', [
          (Icons.chat_bubble_outline,  'Conversations', _stats?.totalConversations.toString() ?? '…'),
          (Icons.check_circle_outline, 'Résolues',      _stats?.resolvedConversations.toString() ?? '…'),
          (Icons.headset_mic_outlined, 'Transférées',   _stats?.transferredConversations.toString() ?? '…'),
          (Icons.star_outline, 'Note moy.',
            _stats?.avgRating != null && _stats!.avgRating > 0
                ? '${_stats!.avgRating.toStringAsFixed(1)}/5' : 'N/A'),
        ]),
        const SizedBox(height: 20),

        // Déconnexion
        SizedBox(
          width: double.infinity, height: 48,
          child: ElevatedButton.icon(
            onPressed: _logout,
            icon: const Icon(Icons.logout_rounded),
            label: const Text('Se déconnecter', style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.w700)),
            style: ElevatedButton.styleFrom(
              backgroundColor: TTColors.red,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
          ),
        ),
      ]),
    );
  }

  Widget _infoCard(String title, List<(IconData, String, String)> rows) {
    return Container(
      decoration: BoxDecoration(
        color: TTColors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.07), blurRadius: 10)],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
          child: Text(title,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
        ),
        const Divider(height: 1),
        ...rows.map((r) => ListTile(
          dense: true,
          leading: Icon(r.$1, color: TTColors.purple, size: 18),
          title: Text(r.$2, style: const TextStyle(fontSize: 11, color: TTColors.muted, fontFamily: 'Cairo')),
          trailing: Text(r.$3.isNotEmpty ? r.$3 : '—',
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: TTColors.text, fontFamily: 'Cairo')),
        )),
      ]),
    );
  }

  // ── Helpers ────────────────────────────────────────────────
  Widget _sectionTitle(String text, {Widget? trailing}) {
    return Row(children: [
      Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
      const Spacer(),
      if (trailing != null) trailing,
    ]);
  }

  Widget _buildErrorBanner(String msg, VoidCallback onRetry) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        border: Border.all(color: const Color(0xFFFECACA)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(children: [
        const Icon(Icons.error_outline_rounded, color: TTColors.red, size: 20),
        const SizedBox(width: 10),
        Expanded(child: Text(msg, style: const TextStyle(fontSize: 12, color: TTColors.red, fontFamily: 'Cairo'))),
        TextButton(onPressed: onRetry,
          child: const Text('Réessayer', style: TextStyle(fontSize: 12, color: TTColors.purple, fontFamily: 'Cairo', fontWeight: FontWeight.w700))),
      ]),
    );
  }
}
