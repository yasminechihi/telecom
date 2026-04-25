import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_theme.dart';
import '../services/api_service.dart';
import '../widgets/tt_logo.dart';

// ════════════════════════════════════════════════════════════
//  Écran d'Inscription — identique à user_login.html (mode register)
// ════════════════════════════════════════════════════════════

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final _formKey     = GlobalKey<FormState>();
  final _nomCtrl     = TextEditingController();
  final _prenomCtrl  = TextEditingController();
  final _emailCtrl   = TextEditingController();
  final _telCtrl     = TextEditingController();
  final _passCtrl    = TextEditingController();
  final _confirmCtrl = TextEditingController();

  bool _loading      = false;
  bool _showPass     = false;
  bool _showConfirm  = false;
  String? _error;

  @override
  void dispose() {
    _nomCtrl.dispose(); _prenomCtrl.dispose(); _emailCtrl.dispose();
    _telCtrl.dispose(); _passCtrl.dispose(); _confirmCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_passCtrl.text != _confirmCtrl.text) {
      setState(() => _error = 'Les mots de passe ne correspondent pas');
      return;
    }
    setState(() { _loading = true; _error = null; });

    final err = await ApiService().register(
      email:     _emailCtrl.text.trim(),
      password:  _passCtrl.text,
      nom:       _nomCtrl.text.trim(),
      prenom:    _prenomCtrl.text.trim(),
      telephone: _telCtrl.text.trim(),
    );

    if (!mounted) return;
    setState(() => _loading = false);

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
              child: isSmall ? _buildMobileLayout() : _buildDesktopLayout(),
            ),
            _buildFooter(),
          ],
        ),
      ),
    );
  }

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
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(color: TTColors.teal, borderRadius: BorderRadius.circular(20)),
            child: const Row(children: [
              Icon(Icons.shield_outlined, color: Colors.white, size: 14),
              SizedBox(width: 6),
              Text('Espace sécurisé', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600, fontFamily: 'Cairo')),
            ]),
          ),
        ],
      ),
    );
  }

  Widget _buildMobileLayout() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(children: [
        const SizedBox(height: 16),
        _buildBrandPanelCompact(),
        const SizedBox(height: 16),
        _buildFormPanel(),
      ]),
    );
  }

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
        child: Row(children: [
          Expanded(child: _buildBrandPanelFull()),
          Expanded(
            child: SingleChildScrollView(
              child: _buildFormPanel(inCard: true),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _buildBrandPanelCompact() {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight,
            colors: [TTColors.purpleDark, TTColors.purple, TTColors.purpleLight]),
        ),
        child: Row(children: [
          const TTLogo(size: 46, onDark: true, radius: 12),
          const SizedBox(width: 16),
          const Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Bienvenue sur Mon Espace TT', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Colors.white, fontFamily: 'Cairo')),
            SizedBox(height: 4),
            Text('Créez votre compte en quelques secondes', style: TextStyle(fontSize: 12, color: Colors.white70, fontFamily: 'Cairo')),
          ])),
        ]),
      ),
    );
  }

  Widget _buildBrandPanelFull() {
    return Container(
      padding: const EdgeInsets.all(40),
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight,
          colors: [TTColors.purpleDark, TTColors.purple, TTColors.purpleLight]),
        borderRadius: BorderRadius.horizontal(left: Radius.circular(16)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const TTLogoBig(size: 90),
          const SizedBox(height: 24),
          const Text('Créer un compte\nMon Espace TT',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Colors.white, fontFamily: 'Cairo', height: 1.3)),
          const SizedBox(height: 8),
          Text('Rejoignez des milliers de clients\nqui gèrent leurs services en ligne',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.8), fontFamily: 'Cairo', height: 1.5)),
          const SizedBox(height: 28),
          ...[
            (Icons.smart_toy_outlined, 'Assistant virtuel intelligent'),
            (Icons.history_outlined, 'Historique de vos réclamations'),
            (Icons.access_time, 'Disponible 24h/24, 7j/7'),
            (Icons.headset_mic_outlined, 'Transfert vers agent humain'),
          ].map((e) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(children: [
              Icon(e.$1, color: TTColors.teal, size: 18),
              const SizedBox(width: 10),
              Text(e.$2, style: TextStyle(color: Colors.white.withOpacity(0.85), fontSize: 13, fontFamily: 'Cairo')),
            ]),
          )),
        ],
      ),
    );
  }

  Widget _buildFormPanel({bool inCard = false}) {
    final content = Padding(
      padding: const EdgeInsets.all(28),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _buildTabs(),
            const SizedBox(height: 24),
            const Text('Créer un compte',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: TTColors.text, fontFamily: 'Cairo')),
            const SizedBox(height: 4),
            const Text('Rejoignez Mon Espace TT en quelques secondes',
              style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
            const SizedBox(height: 20),
            if (_error != null) _buildError(_error!),

            // Nom + Prénom
            Row(children: [
              Expanded(child: _buildField(_nomCtrl, 'Nom', 'Ben Ali', Icons.person_outline,
                validator: (v) => (v == null || v.isEmpty) ? 'Requis' : null)),
              const SizedBox(width: 12),
              Expanded(child: _buildField(_prenomCtrl, 'Prénom', 'Mohamed', Icons.person_outline,
                validator: (v) => (v == null || v.isEmpty) ? 'Requis' : null)),
            ]),
            const SizedBox(height: 12),

            // Email
            _buildField(_emailCtrl, 'Email', 'exemple@email.com', Icons.email_outlined,
              keyboardType: TextInputType.emailAddress,
              validator: (v) {
                if (v == null || v.isEmpty) return 'Email requis';
                if (!v.contains('@')) return 'Email invalide';
                return null;
              }),
            const SizedBox(height: 12),

            // Téléphone
            _buildField(_telCtrl, 'Numéro de téléphone', '2X XXX XXX', Icons.phone_outlined,
              keyboardType: TextInputType.phone,
              validator: (v) => (v == null || v.isEmpty) ? 'Téléphone requis' : null),
            const SizedBox(height: 12),

            // Mot de passe + Confirmer
            Row(children: [
              Expanded(child: _buildField(_passCtrl, 'Mot de passe', 'Min. 6 car.', Icons.lock_outline,
                obscure: !_showPass,
                suffix: IconButton(
                  icon: Icon(_showPass ? Icons.visibility_off_outlined : Icons.visibility_outlined, color: TTColors.muted, size: 18),
                  onPressed: () => setState(() => _showPass = !_showPass),
                ),
                validator: (v) {
                  if (v == null || v.isEmpty) return 'Requis';
                  if (v.length < 6) return 'Min. 6 car.';
                  return null;
                })),
              const SizedBox(width: 12),
              Expanded(child: _buildField(_confirmCtrl, 'Confirmer', 'Répétez', Icons.lock_outline,
                obscure: !_showConfirm,
                suffix: IconButton(
                  icon: Icon(_showConfirm ? Icons.visibility_off_outlined : Icons.visibility_outlined, color: TTColors.muted, size: 18),
                  onPressed: () => setState(() => _showConfirm = !_showConfirm),
                ),
                validator: (v) => (v == null || v.isEmpty) ? 'Requis' : null)),
            ]),
            const SizedBox(height: 22),

            // Bouton
            SizedBox(
              height: 50,
              child: ElevatedButton(
                onPressed: _loading ? null : _submit,
                style: ElevatedButton.styleFrom(
                  backgroundColor: TTColors.purple,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
                child: _loading
                    ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation<Color>(Colors.white)))
                    : const Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                        Icon(Icons.person_add_rounded, size: 18),
                        SizedBox(width: 8),
                        Text('Créer mon compte', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, fontFamily: 'Cairo')),
                      ]),
              ),
            ),
            const SizedBox(height: 18),
            Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              const Text('Déjà un compte ? ', style: TextStyle(fontSize: 13, color: TTColors.muted, fontFamily: 'Cairo')),
              GestureDetector(
                onTap: () => context.go('/login'),
                child: const Text('Se connecter', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: TTColors.purple, fontFamily: 'Cairo')),
              ),
            ]),
          ],
        ),
      ),
    );

    if (inCard) return content;
    return Card(elevation: 6, shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)), child: content);
  }

  Widget _buildTabs() {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: TTColors.gray, borderRadius: BorderRadius.circular(10)),
      child: Row(children: [
        Expanded(
          child: GestureDetector(
            onTap: () => context.go('/login'),
            child: const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Center(child: Text('Se connecter', style: TextStyle(color: TTColors.muted, fontWeight: FontWeight.w600, fontSize: 13, fontFamily: 'Cairo'))),
            ),
          ),
        ),
        Expanded(
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: BoxDecoration(color: TTColors.purple, borderRadius: BorderRadius.circular(8),
              boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.3), blurRadius: 8)]),
            child: const Center(child: Text('Créer un compte', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 13, fontFamily: 'Cairo'))),
          ),
        ),
      ]),
    );
  }

  Widget _buildField(
    TextEditingController ctrl,
    String label,
    String hint,
    IconData icon, {
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
          controller: ctrl,
          obscureText: obscure,
          keyboardType: keyboardType,
          validator: validator,
          style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, color: TTColors.text),
          decoration: InputDecoration(hintText: hint, prefixIcon: Icon(icon, size: 18), suffixIcon: suffix),
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
      child: Row(children: [
        const Icon(Icons.error_outline, color: Color(0xFFDC2626), size: 18),
        const SizedBox(width: 8),
        Expanded(child: Text(msg, style: const TextStyle(color: Color(0xFFDC2626), fontSize: 13, fontFamily: 'Cairo'))),
      ]),
    );
  }

  Widget _buildFooter() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(
        gradient: LinearGradient(colors: [TTColors.purpleDark, Color(0xFF2D1270)]),
      ),
      child: const Text('© 2024 Tunisie Telecom — Tous droits réservés',
        textAlign: TextAlign.center,
        style: TextStyle(color: Colors.white60, fontSize: 12, fontFamily: 'Cairo')),
    );
  }
}
