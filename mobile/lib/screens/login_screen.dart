import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_theme.dart';
import '../services/api_service.dart';
import '../widgets/tt_logo.dart';
import 'settings_screen.dart';

// ════════════════════════════════════════════════════════════
//  Écran de Connexion — identique à user_login.html
//  Design Tunisie Telecom (violet + teal)
// ════════════════════════════════════════════════════════════

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey    = GlobalKey<FormState>();
  final _emailCtrl  = TextEditingController();
  final _passCtrl   = TextEditingController();

  bool _loading      = false;
  bool _showPassword = false;
  String? _error;
  // Message affiché pendant la recherche automatique du serveur
  String _loadingMsg = 'Connexion en cours…';

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() { _loading = true; _error = null; _loadingMsg = 'Connexion en cours…'; });

    // Tentative normale (IP mémorisée)
    final api = ApiService();
    var err = await api.login(_emailCtrl.text.trim(), _passCtrl.text);

    // Si le serveur n'a pas répondu, on informe que la recherche auto est en cours
    if (err != null && err.contains('non disponible') && mounted) {
      setState(() => _loadingMsg = 'Recherche du serveur sur le réseau…');
      // La découverte UDP est déjà lancée dans login() — on relance
      // avec le nouvel IP si trouvé
      err = await api.login(_emailCtrl.text.trim(), _passCtrl.text);
    }

    if (!mounted) return;
    setState(() { _loading = false; _loadingMsg = 'Connexion en cours…'; });

    if (err == null) {
      context.go('/dashboard');
    } else {
      setState(() => _error = err);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isSmall = MediaQuery.of(context).size.width < 600;

    return Scaffold(
      backgroundColor: TTColors.gray,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: isSmall
                  ? _buildMobileLayout()
                  : _buildDesktopLayout(),
            ),
            _buildFooter(),
          ],
        ),
      ),
    );
  }

  // ── Header ─────────────────────────────────────────────────
  Widget _buildHeader() {
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: const BoxDecoration(
        color: TTColors.white,
        border: Border(bottom: BorderSide(color: TTColors.purple, width: 3)),
        boxShadow: [BoxShadow(color: Color(0x14000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      child: Row(
        children: [
          // Logo
          const TTLogo(size: 44, onDark: false),
          const SizedBox(width: 12),
          const Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Tunisie Telecom', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: TTColors.purple, fontFamily: 'Cairo')),
              Text('Mon Espace Client', style: TextStyle(fontSize: 11, color: TTColors.muted, fontFamily: 'Cairo')),
            ],
          ),
          const Spacer(),
          // Bouton paramètres réseau (changer l'IP du serveur)
          IconButton(
            icon: const Icon(Icons.settings_ethernet_rounded, color: TTColors.muted, size: 22),
            tooltip: 'Paramètres réseau (IP serveur)',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: TTColors.teal,
              borderRadius: BorderRadius.circular(20),
            ),
            child: const Row(
              children: [
                Icon(Icons.shield_outlined, color: Colors.white, size: 14),
                SizedBox(width: 6),
                Text('Espace sécurisé', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600, fontFamily: 'Cairo')),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Layout mobile (vertical) ───────────────────────────────
  Widget _buildMobileLayout() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          const SizedBox(height: 20),
          _buildBrandPanel(compact: true),
          const SizedBox(height: 20),
          _buildFormPanel(),
        ],
      ),
    );
  }

  // ── Layout desktop (horizontal) ────────────────────────────
  Widget _buildDesktopLayout() {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 900),
        margin: const EdgeInsets.all(30),
        decoration: BoxDecoration(
          color: TTColors.white,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.18), blurRadius: 40, offset: const Offset(0, 12))],
        ),
        child: Row(
          children: [
            Expanded(child: _buildBrandPanel(compact: false)),
            Expanded(child: _buildFormPanel(inCard: true)),
          ],
        ),
      ),
    );
  }

  // ── Panneau branding (gauche) ──────────────────────────────
  Widget _buildBrandPanel({required bool compact}) {
    final container = Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [TTColors.purpleDark, TTColors.purple, TTColors.purpleLight],
        ),
        borderRadius: BorderRadius.horizontal(left: Radius.circular(16)),
      ),
      padding: EdgeInsets.all(compact ? 24 : 40),
      child: Column(
        mainAxisSize: compact ? MainAxisSize.min : MainAxisSize.max,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Logo box
          const TTLogoBig(size: 90),
          const SizedBox(height: 24),
          const Text(
            'Bienvenue sur\nMon Espace TT',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Colors.white, fontFamily: 'Cairo', height: 1.3),
          ),
          const SizedBox(height: 8),
          Text(
            'Gérez vos réclamations et\nchattez avec notre assistant',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.8), fontFamily: 'Cairo', height: 1.5),
          ),
          if (!compact) ...[
            const SizedBox(height: 28),
            ...[
              (Icons.smart_toy_outlined, 'Assistant virtuel intelligent'),
              (Icons.history_outlined,   'Historique de vos réclamations'),
              (Icons.access_time,        'Disponible 24h/24, 7j/7'),
              (Icons.headset_mic_outlined,'Transfert vers agent humain'),
            ].map((e) => _featureRow(e.$1, e.$2)),
          ],
        ],
      ),
    );

    if (compact) {
      return ClipRRect(borderRadius: BorderRadius.circular(16), child: container);
    }
    return container;
  }

  Widget _featureRow(IconData icon, String label) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, color: TTColors.teal, size: 18),
          const SizedBox(width: 10),
          Text(label, style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 13, fontFamily: 'Cairo')),
        ],
      ),
    );
  }

  // ── Panneau formulaire ─────────────────────────────────────
  Widget _buildFormPanel({bool inCard = false}) {
    final content = Padding(
      padding: const EdgeInsets.all(28),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Onglets Connexion / Inscription
            _buildTabs(),
            const SizedBox(height: 24),
            const Text('Connexion',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: TTColors.text, fontFamily: 'Cairo')),
            const SizedBox(height: 4),
            const Text('Accédez à votre espace personnel',
              style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
            const SizedBox(height: 20),

            // Message d'erreur
            if (_error != null) _buildError(_error!),

            // Email
            _buildField(
              controller: _emailCtrl,
              label: 'Adresse email',
              hint: 'exemple@email.com',
              icon: Icons.email_outlined,
              keyboardType: TextInputType.emailAddress,
              validator: (v) {
                if (v == null || v.isEmpty) return 'Email requis';
                if (!v.contains('@')) return 'Email invalide';
                return null;
              },
            ),
            const SizedBox(height: 14),

            // Mot de passe
            _buildField(
              controller: _passCtrl,
              label: 'Mot de passe',
              hint: '••••••••',
              icon: Icons.lock_outline,
              obscure: !_showPassword,
              suffix: IconButton(
                icon: Icon(_showPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined, color: TTColors.muted, size: 20),
                onPressed: () => setState(() => _showPassword = !_showPassword),
              ),
              validator: (v) {
                if (v == null || v.isEmpty) return 'Mot de passe requis';
                return null;
              },
            ),
            const SizedBox(height: 22),

            // Bouton connexion
            SizedBox(
              height: 50,
              child: ElevatedButton(
                onPressed: _loading ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: TTColors.purple,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  elevation: 4,
                ),
                child: _loading
                    ? Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation<Color>(Colors.white))),
                          const SizedBox(width: 10),
                          Text(_loadingMsg, style: const TextStyle(fontSize: 13, fontFamily: 'Cairo', color: Colors.white)),
                        ],
                      )
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.login_rounded, size: 18),
                          SizedBox(width: 8),
                          Text('Se connecter', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, fontFamily: 'Cairo')),
                        ],
                      ),
              ),
            ),
            const SizedBox(height: 18),

            // Lien inscription
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text("Pas encore de compte ? ", style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
                GestureDetector(
                  onTap: () => context.go('/register'),
                  child: const Text('Créer un compte', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: TTColors.purple, fontFamily: 'Cairo')),
                ),
              ],
            ),
          ],
        ),
      ),
    );

    if (inCard) return content;
    return Card(
      elevation: 6,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: content,
    );
  }

  Widget _buildTabs() {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: TTColors.gray,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: TTColors.purple,
                borderRadius: BorderRadius.circular(8),
                boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.3), blurRadius: 8)],
              ),
              child: const Center(
                child: Text('Se connecter', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13, fontFamily: 'Cairo')),
              ),
            ),
          ),
          Expanded(
            child: GestureDetector(
              onTap: () => context.go('/register'),
              child: const Padding(
                padding: EdgeInsets.symmetric(vertical: 10),
                child: Center(
                  child: Text('Créer un compte', style: TextStyle(color: TTColors.muted, fontWeight: FontWeight.w600, fontSize: 13, fontFamily: 'Cairo')),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required IconData icon,
    bool obscure = false,
    TextInputType? keyboardType,
    Widget? suffix,
    String? Function(String?)? validator,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: TTColors.text, fontFamily: 'Cairo')),
        const SizedBox(height: 6),
        TextFormField(
          controller: controller,
          obscureText: obscure,
          keyboardType: keyboardType,
          validator: validator,
          style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, color: TTColors.text),
          decoration: InputDecoration(
            hintText: hint,
            prefixIcon: Icon(icon, size: 18),
            suffixIcon: suffix,
          ),
        ),
      ],
    );
  }

  Widget _buildError(String msg) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        border: Border.all(color: const Color(0xFFFECACA)),
        borderRadius: BorderRadius.circular(9),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: Color(0xFFDC2626), size: 18),
          const SizedBox(width: 8),
          Expanded(child: Text(msg, style: const TextStyle(color: Color(0xFFDC2626), fontSize: 13, fontFamily: 'Cairo'))),
        ],
      ),
    );
  }

  Widget _buildFooter() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [TTColors.purpleDark, Color(0xFF2D1270)]),
      ),
      child: const Text(
        '© 2026 Tunisie Telecom — Tous droits réservés',
        textAlign: TextAlign.center,
        style: TextStyle(color: Colors.white60, fontSize: 12, fontFamily: 'Cairo'),
      ),
    );
  }
}
