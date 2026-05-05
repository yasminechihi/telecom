import 'dart:async';
import 'dart:io';

// ════════════════════════════════════════════════════════════
//  Service de découverte automatique du serveur (UDP Broadcast)
//
//  Protocole :
//    1. L'app envoie "DISCOVER_TT_SERVER" en broadcast UDP (port 5002)
//    2. Le serveur (user_app.py) répond "TT_SERVER_FOUND:5001"
//    3. L'app récupère l'adresse IP source → connexion automatique
//
//  Fonctionne sur n'importe quel réseau : WiFi maison, hotspot, etc.
//  Aucune saisie d'IP manuelle nécessaire.
// ════════════════════════════════════════════════════════════

class DiscoveryService {
  static const int _discoveryPort = 5002;
  static const String _request    = 'DISCOVER_TT_SERVER';
  static const String _response   = 'TT_SERVER_FOUND:5001';
  static const Duration _timeout  = Duration(seconds: 4);

  /// Cherche le serveur sur le réseau local via UDP broadcast.
  ///
  /// Retourne l'IP du serveur si trouvé, null sinon.
  /// [onAttempt] : callback appelé à chaque tentative (pour l'UI).
  static Future<String?> findServer({void Function(int attempt)? onAttempt}) async {
    // 3 tentatives pour être robuste (perte de paquets UDP possible)
    for (int attempt = 1; attempt <= 3; attempt++) {
      onAttempt?.call(attempt);
      final ip = await _singleScan();
      if (ip != null) return ip;
      if (attempt < 3) await Future.delayed(const Duration(milliseconds: 500));
    }
    return null;
  }

  static Future<String?> _singleScan() async {
    RawDatagramSocket? socket;
    try {
      socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      socket.broadcastEnabled = true;

      // Envoi du broadcast
      socket.send(
        _request.codeUnits,
        InternetAddress('255.255.255.255'),
        _discoveryPort,
      );

      final completer = Completer<String?>();

      // Timeout
      final timer = Timer(_timeout, () {
        if (!completer.isCompleted) completer.complete(null);
      });

      socket.listen((event) {
        if (event == RawSocketEvent.read) {
          final datagram = socket!.receive();
          if (datagram == null) return;
          final msg = String.fromCharCodes(datagram.data).trim();
          if (msg == _response && !completer.isCompleted) {
            timer.cancel();
            completer.complete(datagram.address.address);
          }
        }
      });

      final result = await completer.future;
      return result;
    } catch (_) {
      return null;
    } finally {
      socket?.close();
    }
  }
}
