import 'package:flutter/material.dart';
import '../services/api_service.dart';

// ════════════════════════════════════════════════════════════
//  Écran Paramètres Réseau
//  Permet de changer l'IP du serveur sans recompiler l'app.
//
//  Cas d'usage :
//    • WiFi maison      → ex: 192.168.1.224
//    • Partage tel.     → ex: 192.168.43.x  (voir ipconfig sur PC)
//    • Émulateur        → 10.0.2.2
// ════════════════════════════════════════════════════════════

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _ipController = TextEditingController();
  bool _saving = false;
  bool _testing = false;
  String? _testResult;
  bool? _testSuccess;

  @override
  void initState() {
    super.initState();
    _ipController.text = ApiService().currentServerIp;
  }

  @override
  void dispose() {
    _ipController.dispose();
    super.dispose();
  }

  Future<void> _saveIp() async {
    final ip = _ipController.text.trim();
    if (ip.isEmpty) return;
    setState(() => _saving = true);
    await ApiService().setServerIp(ip);
    setState(() => _saving = false);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('✅ IP enregistrée. Redémarrez l\'app si besoin.'),
        backgroundColor: Color(0xFF3D1484),
      ),
    );
  }

  Future<void> _testConnection() async {
    final ip = _ipController.text.trim();
    if (ip.isEmpty) return;
    setState(() { _testing = true; _testResult = null; _testSuccess = null; });

    // Sauvegarde temporairement l'IP pour le test
    final oldIp = ApiService().currentServerIp;
    await ApiService().setServerIp(ip);

    try {
      final result = await ApiService().login('__ping__@test.local', '__ping__');
      // Si on reçoit "Email ou mot de passe incorrect" = serveur joignable ✅
      // Si on reçoit "Serveur non disponible" = serveur inaccessible ❌
      final reachable = result != 'Serveur non disponible. Lancez user_app.py (port 5001).';
      setState(() {
        _testSuccess = reachable;
        _testResult = reachable
            ? 'Serveur joignable sur $ip:5001 ✅'
            : 'Impossible de joindre $ip:5001 ❌\nVérifiez l\'IP et que user_app.py est lancé.';
      });
      if (!reachable) {
        // Restaure l'ancienne IP si le test échoue
        await ApiService().setServerIp(oldIp);
        _ipController.text = oldIp;
      }
    } catch (_) {
      setState(() {
        _testSuccess = false;
        _testResult = 'Erreur de connexion vers $ip:5001 ❌';
      });
      await ApiService().setServerIp(oldIp);
      _ipController.text = oldIp;
    } finally {
      setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F5F5),
      appBar: AppBar(
        backgroundColor: const Color(0xFF3D1484),
        foregroundColor: Colors.white,
        title: const Text(
          'Paramètres réseau',
          style: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
        ),
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Carte info ──
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFEDE7F6),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF3D1484).withOpacity(0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(
                    children: [
                      Icon(Icons.info_outline, color: Color(0xFF3D1484), size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Pourquoi changer l\'IP ?',
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF3D1484),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _infoRow('📶 WiFi maison', 'Garder l\'IP par défaut (192.168.1.x)'),
                  _infoRow('📱 Partage tel. (hotspot)', 'Changer l\'IP → voir ipconfig sur PC'),
                  _infoRow('🤖 Émulateur Android', 'Utiliser 10.0.2.2'),
                  const Divider(height: 20),
                  const Text(
                    '💡 Sur Windows : ouvrir CMD → taper ipconfig\n'
                    '→ chercher "Adaptateur réseau sans fil"\n'
                    '→ copier "Adresse IPv4"',
                    style: TextStyle(fontSize: 12, color: Colors.black87, fontFamily: 'Cairo'),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 28),

            // ── Champ IP ──
            const Text(
              'Adresse IP du serveur (PC)',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.bold,
                fontSize: 15,
                color: Color(0xFF3D1484),
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _ipController,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              style: const TextStyle(fontFamily: 'Cairo', fontSize: 16),
              decoration: InputDecoration(
                hintText: 'ex: 192.168.43.105',
                prefixIcon: const Icon(Icons.router, color: Color(0xFF3D1484)),
                filled: true,
                fillColor: Colors.white,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF3D1484)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide(color: Colors.grey.shade300),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: Color(0xFF3D1484), width: 2),
                ),
              ),
            ),

            const SizedBox(height: 16),

            // ── Résultat du test ──
            if (_testResult != null)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _testSuccess == true
                      ? const Color(0xFFE8F5E9)
                      : const Color(0xFFFFEBEE),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  _testResult!,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    color: _testSuccess == true ? Colors.green[800] : Colors.red[800],
                    fontSize: 13,
                  ),
                ),
              ),

            const SizedBox(height: 20),

            // ── Boutons ──
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _testing ? null : _testConnection,
                    icon: _testing
                        ? const SizedBox(
                            width: 18, height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.wifi_find),
                    label: Text(
                      _testing ? 'Test...' : 'Tester',
                      style: const TextStyle(fontFamily: 'Cairo'),
                    ),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFF3D1484),
                      side: const BorderSide(color: Color(0xFF3D1484)),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: _saving ? null : _saveIp,
                    icon: _saving
                        ? const SizedBox(
                            width: 18, height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.save),
                    label: Text(
                      _saving ? 'Sauvegarde...' : 'Enregistrer',
                      style: const TextStyle(fontFamily: 'Cairo'),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3D1484),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(
              label,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontFamily: 'Cairo', fontSize: 12, color: Colors.black87),
            ),
          ),
        ],
      ),
    );
  }
}
