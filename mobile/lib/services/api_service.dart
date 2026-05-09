import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/user_model.dart';
import 'discovery_service.dart';

// ════════════════════════════════════════════════════════════
//  Service API — se connecte au backend Flask (user_app.py)
//  Port 5001 — même base de données Firebase Firestore
//
//  Stratégie : 
//    - WEB : utilise localhost (même machine)
//    - MOBILE : IP dynamique (découverte UDP ou mémorisée)
// ════════════════════════════════════════════════════════════

class ApiService {
  static const String _keyServerIp     = 'server_ip';
  static const int    _port            = 5001;
  
  // L'IP par défaut n'est plus codée en dur ; elle sera soit localhost (web)
  // soit chargée depuis SharedPreferences (mobile). Si aucune IP n'est trouvée
  // sur mobile, la découverte UDP sera automatiquement tentée lors de la
  // première connexion.
  String? _serverIp;  // null = non encore chargé/inconnu

  String get baseUrl {
    if (kIsWeb) {
      // ✅ Sur le navigateur : toujours localhost
      return 'http://localhost:$_port';
    }
    // ✅ Sur mobile : utiliser l'IP chargée (obligatoire)
    if (_serverIp == null) {
      throw Exception('ApiService non initialisé. Appeler loadServerIp() au démarrage.');
    }
    return 'http://$_serverIp:$_port';
  }

  /// Charge l'IP depuis SharedPreferences (à appeler impérativement au démarrage).
  /// Si aucune IP n'est stockée, _serverIp reste null et la découverte
  /// sera déclenchée automatiquement lors du premier appel login/register.
  Future<void> loadServerIp() async {
    if (kIsWeb) {
      _serverIp = 'localhost'; // valeur fictive, mais baseUrl utilise kIsWeb
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    _serverIp = prefs.getString(_keyServerIp);
    // Si null, la découverte UDP sera tentée plus tard.
  }

  /// Change l'IP du serveur et la persiste (mobile uniquement).
  Future<void> setServerIp(String ip) async {
    if (kIsWeb) return;
    _serverIp = ip.trim();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyServerIp, _serverIp!);
  }

  /// Retourne l'IP actuellement configurée (mobile) ou "localhost" (web).
  String get currentServerIp {
    if (kIsWeb) return 'localhost';
    return _serverIp ?? 'inconnue';
  }

  // ── Clés SharedPreferences ────────────────────────────────
  static const String _keyUserId     = 'user_id';
  static const String _keyUserEmail  = 'user_email';
  static const String _keyUserNom    = 'user_nom';
  static const String _keyUserPrenom = 'user_prenom';
  static const String _keyUserTel    = 'user_telephone';

  // ── Singleton ─────────────────────────────────────────────
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  String? _userId;

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    if (_userId != null) 'X-User-ID': _userId!,
  };

  /// Body de base qui inclut toujours le user_id
  Map<String, dynamic> _body([Map<String, dynamic>? extra]) {
    final b = <String, dynamic>{};
    if (_userId != null) b['user_id'] = _userId!;
    if (extra != null) b.addAll(extra);
    return b;
  }

  // ════════════════════════════════════════════════════════
  //  AUTHENTIFICATION — avec fallback découverte UDP (mobile)
  // ════════════════════════════════════════════════════════

  Future<String?> login(String email, String password) async {
    // 1ère tentative avec l'IP actuelle
    var result = await _tryLogin(email, password);
    if (result != _kServerUnavailable) return result;

    // Si c'est la version web, inutile de chercher une IP : le serveur n'est pas dispo
    if (kIsWeb) return _kServerUnavailable;

    // Serveur non joignable sur mobile → découverte automatique UDP
    final discoveredIp = await DiscoveryService.findServer();
    if (discoveredIp != null && discoveredIp != _serverIp) {
      await setServerIp(discoveredIp);
      return await _tryLogin(email, password);
    }

    return _kServerUnavailable;
  }

  static const String _kServerUnavailable =
      'Serveur non disponible. Lancez user_app.py (port $_port).';

  Future<String?> _tryLogin(String email, String password) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/login'),
        headers: _headers,
        body: jsonEncode({'email': email, 'password': password}),
      ).timeout(const Duration(seconds: 6));

      final data = jsonDecode(resp.body) as Map<String, dynamic>;

      if (resp.statusCode == 200 && data['success'] == true) {
        final user = data['user'] as Map<String, dynamic>? ?? {};
        _userId = user['uid']?.toString() ?? '';
        await _saveUser(user, email);
        return null; // succès
      } else {
        return data['error'] ?? 'Email ou mot de passe incorrect.';
      }
    } catch (_) {
      return _kServerUnavailable;
    }
  }

  Future<String?> register({
    required String email,
    required String password,
    required String nom,
    required String prenom,
    required String telephone,
  }) async {
    // 1ère tentative avec l'IP actuelle
    var result = await _tryRegister(
        email: email, password: password,
        nom: nom, prenom: prenom, telephone: telephone);
    if (result != _kServerUnavailable) return result;

    if (kIsWeb) return _kServerUnavailable;

    // Serveur non joignable sur mobile → découverte automatique UDP
    final discoveredIp = await DiscoveryService.findServer();
    if (discoveredIp != null && discoveredIp != _serverIp) {
      await setServerIp(discoveredIp);
      return await _tryRegister(
          email: email, password: password,
          nom: nom, prenom: prenom, telephone: telephone);
    }

    return _kServerUnavailable;
  }

  Future<String?> _tryRegister({
    required String email,
    required String password,
    required String nom,
    required String prenom,
    required String telephone,
  }) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/register'),
        headers: _headers,
        body: jsonEncode({
          'email': email, 'password': password,
          'nom': nom, 'prenom': prenom, 'telephone': telephone,
        }),
      ).timeout(const Duration(seconds: 10));

      final data = jsonDecode(resp.body) as Map<String, dynamic>;

      if (resp.statusCode == 200 && data['success'] == true) {
        final user = data['user'] as Map<String, dynamic>? ?? {};
        _userId = user['uid']?.toString() ?? '';
        await _saveUser(user, email);
        return null;
      } else {
        return data['error'] ?? "Erreur lors de l'inscription";
      }
    } catch (_) {
      return _kServerUnavailable;
    }
  }

  Future<void> logout() async {
    _userId = null;
    await _clearUser();
  }

  // ════════════════════════════════════════════════════════
  //  PROFIL & STATS  — routes /api/mobile/*
  // ════════════════════════════════════════════════════════

  Future<UserModel?> getProfile() async {
    if (_userId == null) return getCachedUser();
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/profile'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        return UserModel.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
      }
    } catch (_) {}
    return getCachedUser();
  }

  Future<UserStats?> getStats() async {
    if (_userId == null) return null;
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/stats'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        return UserStats.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
      }
    } catch (_) {}
    return null;
  }

  // ════════════════════════════════════════════════════════
  //  HISTORIQUE DES CONVERSATIONS
  // ════════════════════════════════════════════════════════

  Future<List<TopIssue>> getTopIssues() async {
    if (_userId == null) return [];
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/top_issues'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        final list = data['issues'] as List? ?? [];
        return list.map((e) => TopIssue.fromJson(e as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
    return [];
  }

  Future<List<ConversationSummary>> getHistory() async {
    if (_userId == null) return [];
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/history'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 15));

      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        final list = data is List ? data : (data['conversations'] as List? ?? []);
        return list
            .map((e) => ConversationSummary.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  Future<List<ChatMessage>> getConversationDetail(String convId) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/conversation/$convId'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        final messages = data['messages'] as List? ?? [];
        return messages
            .map((e) => ChatMessage.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    return [];
  }

  // ════════════════════════════════════════════════════════
  //  CHAT
  // ════════════════════════════════════════════════════════

  Future<Map<String, dynamic>?> sendMessage({
    required String convSessionId,
    required String text,
  }) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/chat'),
        headers: _headers,
        body: jsonEncode(_body({
          'conv_session_id': convSessionId,
          'text': text,
        })),
      ).timeout(const Duration(seconds: 20));

      if (resp.statusCode == 200) {
        return jsonDecode(resp.body) as Map<String, dynamic>;
      }

      String errMsg;
      try {
        final errData = jsonDecode(resp.body) as Map<String, dynamic>;
        errMsg = errData['error']?.toString() ?? 'Erreur serveur (${resp.statusCode})';
      } catch (_) {
        errMsg = 'Erreur serveur (${resp.statusCode})';
      }
      return {'bot_response': errMsg, 'error': true};
    } on Exception catch (e) {
      final msg = e.toString().contains('TimeoutException')
          ? 'Le serveur ne répond pas. Vérifiez que user_app.py est lancé (port $_port).'
          : 'Connexion impossible. Vérifiez votre réseau et que user_app.py est lancé.';
      return {'bot_response': msg, 'error': true};
    }
  }

  Future<Map<String, dynamic>?> getCallStatus(String convId) async {
    if (convId.isEmpty) return null;
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/call_status/$convId'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 8));
      if (resp.statusCode == 200) {
        return jsonDecode(resp.body) as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  Future<String?> newConversation() async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/new_conversation'),
        headers: _headers,
        body: jsonEncode(_body()),
      ).timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        return data['conv_session_id']?.toString() ?? data['conv_id']?.toString();
      }
    } catch (_) {}
    return null;
  }

  Future<void> rateConversation(String convId, int rating) async {
    try {
      await http.post(
        Uri.parse('$baseUrl/api/mobile/rate_conversation'),
        headers: _headers,
        body: jsonEncode(_body({'conv_id': convId, 'rating': rating})),
      ).timeout(const Duration(seconds: 10));
    } catch (_) {}
  }

  // ════════════════════════════════════════════════════════
  //  STT — Whisper backend
  // ════════════════════════════════════════════════════════

  Future<String?> sttFromAudio(String filePath) async {
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/api/mobile/stt'),
      );
      if (_userId != null) request.headers['X-User-ID'] = _userId!;
      request.files.add(await http.MultipartFile.fromPath('audio', filePath));
      final streamed = await request.send().timeout(const Duration(seconds: 30));
      final resp = await http.Response.fromStream(streamed);
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body) as Map<String, dynamic>;
        final text = data['text']?.toString() ?? '';
        return text.isNotEmpty ? text : null;
      }
    } catch (_) {}
    return null;
  }

  // ════════════════════════════════════════════════════════
  //  TTS — edge-tts backend
  // ════════════════════════════════════════════════════════

  Future<Uint8List?> getTtsAudio(String text) async {
    try {
      final resp = await http.post(
        Uri.parse('$baseUrl/api/mobile/tts'),
        headers: {
          'Content-Type': 'application/json',
          if (_userId != null) 'X-User-ID': _userId!,
        },
        body: jsonEncode({'text': text}),
      ).timeout(const Duration(seconds: 15));

      if (resp.statusCode == 200) {
        return resp.bodyBytes;
      }
    } catch (_) {}
    return null;
  }

  // ════════════════════════════════════════════════════════
  //  STOCKAGE LOCAL (SharedPreferences)
  // ════════════════════════════════════════════════════════

  Future<void> _saveUser(Map<String, dynamic> user, String email) async {
    final prefs = await SharedPreferences.getInstance();
    final uid = user['uid']?.toString() ?? '';
    await prefs.setString(_keyUserId,     uid);
    await prefs.setString(_keyUserEmail,  user['email']?.toString() ?? email);
    await prefs.setString(_keyUserNom,    user['nom']?.toString() ?? '');
    await prefs.setString(_keyUserPrenom, user['prenom']?.toString() ?? '');
    await prefs.setString(_keyUserTel,    user['telephone']?.toString() ?? '');
    _userId = uid;
  }

  Future<void> _clearUser() async {
    final prefs = await SharedPreferences.getInstance();
    for (final k in [_keyUserId, _keyUserEmail, _keyUserNom, _keyUserPrenom, _keyUserTel]) {
      await prefs.remove(k);
    }
  }

  Future<bool> isLoggedIn() async {
    final prefs = await SharedPreferences.getInstance();
    final uid = prefs.getString(_keyUserId);
    if (uid != null && uid.isNotEmpty) {
      _userId = uid;
      return true;
    }
    return false;
  }

  Future<UserModel?> getCachedUser() async {
    final prefs = await SharedPreferences.getInstance();
    final email = prefs.getString(_keyUserEmail);
    if (email == null) return null;
    final uid = prefs.getString(_keyUserId) ?? '';
    if (_userId == null && uid.isNotEmpty) _userId = uid;
    return UserModel(
      uid:       uid,
      email:     email,
      nom:       prefs.getString(_keyUserNom) ?? '',
      prenom:    prefs.getString(_keyUserPrenom) ?? '',
      telephone: prefs.getString(_keyUserTel) ?? '',
    );
  }
}