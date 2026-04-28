import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';
import '../theme/app_theme.dart';
import '../services/api_service.dart';
import '../models/user_model.dart';

// ════════════════════════════════════════════════════════════
//  Écran Chat — même interface que user_dashboard.html
//  Mode Écrit + Mode Vocal (STT/TTS) · bot_response corrigé
// ════════════════════════════════════════════════════════════

class ChatScreen extends StatefulWidget {
  final String? convSessionId;
  final String? existingConvId;

  const ChatScreen({
    super.key,
    this.convSessionId,
    this.existingConvId,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with TickerProviderStateMixin {
  final _api        = ApiService();
  final _scrollCtrl = ScrollController();
  final _inputCtrl  = TextEditingController();
  final _focusNode  = FocusNode();

  // ── STT / TTS ────────────────────────────────────────────
  final _speech        = SpeechToText();
  final _tts           = FlutterTts();          // fallback si backend indisponible
  final _audioPlayer   = AudioPlayer();         // lecture audio edge-tts (backend)
  final _audioRecorder = AudioRecorder();       // enregistrement pour Whisper backend

  bool _speechAvailable = false;
  bool _isListening     = false;
  bool _isWhisperMode   = true;    // true = Whisper backend, false = on-device STT
  bool _whisperLoading  = false;   // true pendant l'envoi au backend
  String? _whisperTmpPath;         // chemin fichier audio temporaire
  String _voiceTranscript = '';
  bool _ttsEnabled      = false;
  bool _voiceMode       = false;   // false = texte, true = vocal

  // ── État conversation ────────────────────────────────────
  String _convSessionId = '';
  List<ChatMessage> _messages = [];
  bool _loading    = false;
  bool _botTyping  = false;
  bool _transferred = false;
  int? _pendingRating;
  bool _showRating = false;

  // ── Transfert agent humain ───────────────────────────────
  bool   _amiCalled     = false;  // True si appel Asterisk initié
  String _amiReason     = '';     // 'ok' | 'no_phone' | 'ami_down'
  String _agentResponse = '';     // Réponse transcrite de l'agent
  Timer? _pollingTimer;           // Polling agent_hung_up

  // ── Animation visualiseur vocal ──────────────────────────
  late AnimationController _micAnimCtrl;
  Timer? _dotTimer;
  int _dotCount = 1;

  @override
  void initState() {
    super.initState();
    _micAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    )..repeat(reverse: true);
    _initSpeech();
    _initTts();
    _init();
  }

  @override
  void dispose() {
    _micAnimCtrl.dispose();
    _dotTimer?.cancel();
    _pollingTimer?.cancel();
    _scrollCtrl.dispose();
    _inputCtrl.dispose();
    _focusNode.dispose();
    _tts.stop();
    _audioPlayer.dispose();
    _audioRecorder.dispose();
    // Nettoyer le fichier temporaire Whisper si présent
    if (_whisperTmpPath != null) {
      try { File(_whisperTmpPath!).deleteSync(); } catch (_) {}
    }
    super.dispose();
  }

  // ── Initialisation STT ───────────────────────────────────
  Future<void> _initSpeech() async {
    try {
      _speechAvailable = await _speech.initialize(
        onStatus: (status) {
          if (status == 'done' || status == 'notListening') {
            if (mounted) setState(() => _isListening = false);
          }
        },
        onError: (_) {
          if (mounted) setState(() => _isListening = false);
        },
      );
    } catch (_) {
      _speechAvailable = false;
    }
    if (mounted) setState(() {});
  }

  // ── Initialisation TTS ───────────────────────────────────
  Future<void> _initTts() async {
    // Configurer flutter_tts uniquement comme fallback (si backend inaccessible)
    try {
      await _tts.setLanguage('ar-SA');
      await _tts.setSpeechRate(0.5);
      await _tts.setVolume(1.0);
    } catch (_) {}
  }

  // ── Chargement conversation ──────────────────────────────
  Future<void> _init() async {
    if (widget.existingConvId != null && widget.existingConvId!.isNotEmpty) {
      setState(() => _loading = true);
      final msgs = await _api.getConversationDetail(widget.existingConvId!);
      setState(() {
        _messages      = msgs;
        _convSessionId = widget.existingConvId!;
        _loading       = false;
      });
      _scrollToBottom();
    } else if (widget.convSessionId != null && widget.convSessionId!.isNotEmpty) {
      _convSessionId = widget.convSessionId!;
      _addBotMessage(_greetingMessage);
    } else {
      final id = await _api.newConversation();
      _convSessionId = id ?? '';
      _addBotMessage(_greetingMessage);
    }
  }

  static const _greetingMessage =
      'مرحبا بيك في تليكوم تونس! 👋\nأنا المساعد الآلي، قادر نساعدك في:\n• مشاكل الإنترنت والشبكة\n• الفاتورات والرصيد\n• الخدمات والاشتراكات\n\nابدأ بقول «عسلامة» وحدثني عن مشكلتك';

  void _addBotMessage(String text, {bool isTransfer = false}) {
    setState(() {
      _messages.add(ChatMessage(
        role: 'bot', text: text,
        timestamp: DateTime.now(), isTransfer: isTransfer,
      ));
    });
    _scrollToBottom();
    if (_ttsEnabled && text.isNotEmpty) _speakText(text);
  }

  void _addUserMessage(String text, {bool isVoice = false}) {
    setState(() {
      _messages.add(ChatMessage(
        role: 'user', text: text,
        timestamp: DateTime.now(),
      ));
    });
    _scrollToBottom();
  }

  // ── Envoi message ────────────────────────────────────────
  Future<void> _sendMessage([String? forcedText]) async {
    final text = forcedText ?? _inputCtrl.text.trim();
    if (text.isEmpty || _botTyping) return;
    if (forcedText == null) _inputCtrl.clear();

    _addUserMessage(text);
    setState(() => _botTyping = true);

    final result = await _api.sendMessage(
      convSessionId: _convSessionId,
      text: text,
    );

    if (!mounted) return;
    setState(() => _botTyping = false);

    if (result != null) {
      // La réponse du bot est dans 'bot_response' (Flask) ou fallback sur 'response'/'text'
      final response = result['bot_response'] as String? ??
          result['response'] as String? ??
          result['text'] as String? ?? '';

      final isTransfer = result['transferred'] == true ||
          result['action'] == 'transfer';

      // Mettre à jour l'ID de conversation si fourni par Flask
      final newConvId = result['conversation_id']?.toString() ??
          result['conv_id']?.toString();
      if (newConvId != null && newConvId.isNotEmpty) {
        _convSessionId = newConvId;
      }

      if (response.isNotEmpty) {
        _addBotMessage(response, isTransfer: isTransfer);
      }

      if (isTransfer) {
        final amiCalled = result['ami_called'] == true;
        final amiReason = result['ami_reason']?.toString() ?? '';
        setState(() {
          _transferred  = true;
          _amiCalled    = amiCalled;
          _amiReason    = amiReason;
          _showRating   = false; // Attendre que l'agent raccroche
        });
        _showTransferSnackBar(amiCalled);
        if (_convSessionId.isNotEmpty) _startCallPolling(_convSessionId);
      } else if (result['session_ended'] == true) {
        setState(() => _showRating = true);
      }
    } else {
      _addBotMessage('عذراً، حدث خطأ. يرجى المحاولة مرة أخرى.');
    }
  }

  // ── Mode vocal ───────────────────────────────────────────

  /// Bascule enregistrement Whisper (backend) ou on-device selon _isWhisperMode.
  Future<void> _toggleListening() async {
    if (_isListening) {
      await _stopListening();
    } else {
      await _startListening();
    }
  }

  Future<void> _startListening() async {
    setState(() { _isListening = true; _voiceTranscript = ''; _whisperLoading = false; });

    if (_isWhisperMode) {
      // ── Mode Whisper : enregistrement vers fichier temporaire ──
      try {
        final hasPermission = await _audioRecorder.hasPermission();
        if (!hasPermission) {
          setState(() => _isListening = false);
          return;
        }
        final tmpDir  = await getTemporaryDirectory();
        final tmpPath = '${tmpDir.path}/tt_stt_${DateTime.now().millisecondsSinceEpoch}.wav';
        _whisperTmpPath = tmpPath;
        await _audioRecorder.start(
          const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
          path: tmpPath,
        );
      } catch (e) {
        // Fallback on-device si l'enregistrement échoue
        setState(() { _isListening = false; _isWhisperMode = false; });
        await _startOnDeviceListening();
      }
    } else {
      // ── Mode on-device : speech_to_text ──
      await _startOnDeviceListening();
    }
  }

  Future<void> _startOnDeviceListening() async {
    setState(() => _isListening = true);
    await _speech.listen(
      onResult: (val) {
        setState(() => _voiceTranscript = val.recognizedWords);
      },
      localeId: 'ar',
      listenFor: const Duration(seconds: 30),
      pauseFor: const Duration(seconds: 3),
    );
  }

  Future<void> _stopListening() async {
    if (_isWhisperMode) {
      // ── Arrêt Whisper : envoyer l'audio au backend ──
      setState(() { _isListening = false; _whisperLoading = true; });
      try {
        final path = await _audioRecorder.stop();
        final filePath = path ?? _whisperTmpPath;
        if (filePath != null && File(filePath).existsSync()) {
          final transcript = await _api.sttFromAudio(filePath);
          // Nettoyer le fichier temporaire
          try { File(filePath).deleteSync(); } catch (_) {}
          _whisperTmpPath = null;
          if (mounted) {
            setState(() {
              _whisperLoading = false;
              _voiceTranscript = transcript ?? '';
            });
          }
          return;
        }
      } catch (_) {}
      // En cas d'erreur : revenir au mode on-device pour ce tour
      setState(() => _whisperLoading = false);
    } else {
      // ── Arrêt on-device ──
      await _speech.stop();
      setState(() => _isListening = false);
    }
  }

  void _sendTranscript() {
    if (_voiceTranscript.isEmpty) return;
    final text = _voiceTranscript;
    setState(() { _voiceTranscript = ''; _isListening = false; _whisperLoading = false; });
    if (!_isWhisperMode) _speech.stop();
    _sendMessage(text);
  }

  /// Lit le texte via edge-tts backend (ar-TN-ReemNeural — même voix que le web).
  /// Fallback automatique sur flutter_tts si le backend est inaccessible.
  Future<void> _speakText(String text) async {
    try {
      // 1. Arrêter toute lecture en cours
      await _audioPlayer.stop();
      await _tts.stop();

      // 2. Essayer le backend edge-tts (voix tunisienne)
      final Uint8List? audioBytes = await _api.getTtsAudio(text);
      if (audioBytes != null && audioBytes.isNotEmpty) {
        await _audioPlayer.play(BytesSource(audioBytes));
        return;
      }

      // 3. Fallback : flutter_tts (voix Android intégrée)
      await _tts.speak(text);
    } catch (_) {
      // Dernier recours silencieux
      try { await _tts.speak(text); } catch (_) {}
    }
  }

  // ── Toast transfert ──────────────────────────────────────
  void _showTransferSnackBar(bool amiCalled) {
    if (!mounted) return;
    final msg = amiCalled
        ? '📞 Appel en cours — Attendez que l\'agent raccroche'
        : '🎧 Demande transférée — Contactez le 1298 pour un suivi';
    final color = amiCalled ? TTColors.green : TTColors.orange;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: const TextStyle(fontFamily: 'Cairo', fontSize: 13)),
      backgroundColor: color,
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      margin: const EdgeInsets.all(12),
    ));
  }

  // ── Polling "agent a raccroché" ───────────────────────────
  void _startCallPolling(String convId) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      if (!mounted || !_transferred) { _pollingTimer?.cancel(); return; }
      final status = await _api.getCallStatus(convId);
      if (status == null || !mounted) return;

      if (status['agent_hung_up'] == true) {
        _pollingTimer?.cancel();
        final agentResp = status['agent_response']?.toString() ?? '';
        if (agentResp.isNotEmpty) {
          _addBotMessage(agentResp);
        }
        setState(() {
          _agentResponse = agentResp;
          _showRating    = true;
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: const Text('📴 L\'agent a raccroché — Évaluez votre expérience',
              style: TextStyle(fontFamily: 'Cairo', fontSize: 13)),
            backgroundColor: TTColors.orange,
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 5),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            margin: const EdgeInsets.all(12),
          ));
        }
      }
    });
  }

  // ── Évaluation ───────────────────────────────────────────
  Future<void> _submitRating(int rating) async {
    setState(() { _pendingRating = rating; _showRating = false; });
    if (_convSessionId.isNotEmpty) {
      await _api.rateConversation(_convSessionId, rating);
    }
    if (mounted) _addBotMessage('شكراً على تقييمك! يسعدنا خدمتك.');
  }

  void _newConversation() async {
    _pollingTimer?.cancel();
    if (_ttsEnabled) { await _audioPlayer.stop(); await _tts.stop(); }
    final id = await _api.newConversation();
    setState(() {
      _convSessionId = id ?? '';
      _messages.clear();
      _transferred   = false;
      _showRating    = false;
      _pendingRating = null;
      _voiceTranscript = '';
      _amiCalled     = false;
      _amiReason     = '';
      _agentResponse = '';
    });
    _addBotMessage(_greetingMessage);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent + 200,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ════════════════════════════════════════════════════════
  //  BUILD
  // ════════════════════════════════════════════════════════
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFFAFBFF),
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: TTColors.purple))
                  : _buildMessageList(),
            ),
            if (_showRating) _buildRatingBar(),
            if (!_transferred)
              _voiceMode ? _buildVoiceZone() : _buildInputBar(),
            if (_transferred) _buildTransferredBar(),
          ],
        ),
      ),
    );
  }

  // ── Header ────────────────────────────────────────────────
  Widget _buildHeader() {
    return Container(
      height: 64,
      decoration: const BoxDecoration(
        color: TTColors.white,
        border: Border(bottom: BorderSide(color: TTColors.purple, width: 3)),
        boxShadow: [BoxShadow(color: Color(0x12000000), blurRadius: 8, offset: Offset(0, 2))],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          // Retour
          IconButton(
            icon: const Icon(Icons.arrow_back_rounded, color: TTColors.purple),
            onPressed: () => context.canPop() ? context.pop() : context.go('/dashboard'),
          ),
          // Avatar bot — logo TT (comme l'interface web)
          Container(
            width: 40, height: 40,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: TTColors.border),
              boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.15), blurRadius: 6)],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(9),
              child: Image.asset('assets/logo_tt.png', fit: BoxFit.contain),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Assistant Virtuel TT',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: TTColors.text, fontFamily: 'Cairo')),
                Row(children: [
                  Container(width: 7, height: 7, decoration: const BoxDecoration(color: Color(0xFF16A34A), shape: BoxShape.circle)),
                  const SizedBox(width: 5),
                  const Text('En ligne · 24h/24',
                    style: TextStyle(fontSize: 10, color: TTColors.muted, fontFamily: 'Cairo')),
                ]),
              ],
            ),
          ),
          // ── Toggle Mode Écrit / Vocal ─────────────────
          _buildModeToggle(),
          const SizedBox(width: 4),
          // ── Toggle TTS ───────────────────────────────
          _buildTtsToggle(),
          const SizedBox(width: 4),
          // ── Nouveau chat ─────────────────────────────
          Tooltip(
            message: 'Nouveau chat',
            child: IconButton(
              onPressed: _newConversation,
              icon: const Icon(Icons.add_circle_outline_rounded, size: 22, color: TTColors.purple),
              padding: const EdgeInsets.all(4),
              constraints: const BoxConstraints(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildModeToggle() {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: TTColors.gray, borderRadius: BorderRadius.circular(20)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _modeBtn(Icons.keyboard_rounded, 'Écrit', !_voiceMode, () => setState(() { _voiceMode = false; _speech.stop(); _isListening = false; })),
          _modeBtn(Icons.mic_rounded, 'Vocal', _voiceMode, () {
            if (!_speechAvailable) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Autorisez le microphone dans les paramètres de l\'app', style: TextStyle(fontFamily: 'Cairo')),
                  backgroundColor: TTColors.red,
                ),
              );
              return;
            }
            setState(() { _voiceMode = true; });
          }),
        ],
      ),
    );
  }

  // Toggle mode — icônes uniquement pour économiser la largeur du header
  Widget _modeBtn(IconData icon, String label, bool active, VoidCallback onTap) {
    final bool isVocal = label == 'Vocal';
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 32, height: 28,
        decoration: BoxDecoration(
          color: active ? (isVocal ? const Color(0xFFFEE2E2) : TTColors.white) : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          boxShadow: active ? [const BoxShadow(color: Color(0x14000000), blurRadius: 4)] : [],
        ),
        child: Icon(icon, size: 15,
          color: active ? (isVocal ? const Color(0xFFDC2626) : TTColors.purple) : TTColors.muted),
      ),
    );
  }

  Widget _buildTtsToggle() {
    return GestureDetector(
      onTap: () {
        setState(() => _ttsEnabled = !_ttsEnabled);
        if (!_ttsEnabled) { _audioPlayer.stop(); _tts.stop(); }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 32, height: 32,
        decoration: BoxDecoration(
          color: _ttsEnabled ? const Color(0xFF0096B8).withOpacity(0.1) : TTColors.white,
          border: Border.all(color: _ttsEnabled ? TTColors.teal : TTColors.border),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Icon(
          _ttsEnabled ? Icons.volume_up_rounded : Icons.volume_off_rounded,
          size: 16,
          color: _ttsEnabled ? TTColors.teal : TTColors.muted,
        ),
      ),
    );
  }

  // ── Liste des messages ────────────────────────────────────
  Widget _buildMessageList() {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      itemCount: _messages.length + (_botTyping ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _messages.length) return _buildTypingIndicator();
        return _buildMessageBubble(_messages[index]);
      },
    );
  }

  Widget _buildMessageBubble(ChatMessage msg) {
    if (msg.isTransfer) return _buildTransferCard(msg.text);

    final isUser = msg.isUser;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isUser) _msgAvatar(isUser: false),
          Flexible(
            child: Column(
              crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.70),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: isUser ? null : TTColors.white,
                    gradient: isUser
                        ? const LinearGradient(
                            colors: [TTColors.purple, TTColors.purpleLight],
                            begin: Alignment.topLeft, end: Alignment.bottomRight)
                        : null,
                    borderRadius: BorderRadius.only(
                      topLeft:     const Radius.circular(18),
                      topRight:    const Radius.circular(18),
                      bottomLeft:  Radius.circular(isUser ? 18 : 4),
                      bottomRight: Radius.circular(isUser ? 4 : 18),
                    ),
                    border: isUser ? null : Border.all(color: TTColors.border),
                    boxShadow: [BoxShadow(
                      color: (isUser ? TTColors.purple : TTColors.purple).withOpacity(0.10),
                      blurRadius: 8, offset: const Offset(0, 2),
                    )],
                  ),
                  child: Text(
                    msg.text,
                    style: TextStyle(
                      fontSize: 14, height: 1.6,
                      color: isUser ? Colors.white : TTColors.text,
                      fontFamily: 'Cairo',
                    ),
                    textDirection: _isArabic(msg.text) ? TextDirection.rtl : TextDirection.ltr,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  isUser ? 'Vous · ${_formatTime(msg.timestamp)}' : 'Assistant TT · ${_formatTime(msg.timestamp)}',
                  style: const TextStyle(fontSize: 10, color: TTColors.muted, fontFamily: 'Cairo'),
                  textAlign: isUser ? TextAlign.right : TextAlign.left,
                ),
              ],
            ),
          ),
          if (isUser) _msgAvatar(isUser: true),
        ],
      ),
    );
  }

  Widget _msgAvatar({required bool isUser}) {
    return Container(
      width: 32, height: 32,
      margin: EdgeInsets.only(
        right: isUser ? 0 : 8,
        left:  isUser ? 8 : 0,
        bottom: 16,
      ),
      decoration: BoxDecoration(
        color: isUser ? TTColors.purpleBg : Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: isUser ? TTColors.purple.withOpacity(0.2) : TTColors.border),
        boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.10), blurRadius: 4)],
      ),
      child: isUser
          ? const Icon(Icons.person_rounded, color: TTColors.purple, size: 16)
          : ClipRRect(
              borderRadius: BorderRadius.circular(7),
              child: Image.asset('assets/logo_tt.png', fit: BoxFit.contain),
            ),
    );
  }

  Widget _buildTransferCard(String text) {
    // Badge adapté selon l'état AMI (comme user_dashboard.html)
    final bool success  = _amiCalled;
    final bool noPhone  = _amiReason == 'no_phone';

    final Color bg         = success ? const Color(0xFFF0FDF4) : const Color(0xFFFFF7ED);
    final Color border     = success ? const Color(0xFF86EFAC) : const Color(0xFFFED7AA);
    final Color iconColor  = success ? TTColors.green          : const Color(0xFFD97706);
    final IconData icon    = success ? Icons.phone_rounded     : Icons.headset_mic_rounded;

    final String badgeText = success
        ? '📞 Appel initié — Agent contacté'
        : noPhone
            ? '⚠️ Numéro manquant dans votre profil — Contactez le 1298'
            : '🎧 Contactez le 1298 pour un suivi';
    final Color badgeBg    = success ? const Color(0xFFDCFCE7) : const Color(0xFFFEF3C7);
    final Color badgeBdr   = success ? const Color(0xFF86EFAC) : const Color(0xFFFDE68A);
    final Color badgeTxt   = success ? const Color(0xFF166534) : const Color(0xFF92400E);

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: bg,
        border: Border.all(color: border),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, color: iconColor, size: 22),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Transfert vers agent humain',
            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: iconColor, fontFamily: 'Cairo')),
          const SizedBox(height: 4),
          Text(text, style: const TextStyle(fontSize: 12, color: TTColors.text, fontFamily: 'Cairo')),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: badgeBg, borderRadius: BorderRadius.circular(12),
              border: Border.all(color: badgeBdr)),
            child: Text(badgeText,
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: badgeTxt, fontFamily: 'Cairo')),
          ),
        ])),
      ]),
    );
  }

  Widget _buildTypingIndicator() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12, left: 40),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: TTColors.white,
            border: Border.all(color: TTColors.border),
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(18), topRight: Radius.circular(18),
              bottomLeft: Radius.circular(4), bottomRight: Radius.circular(18),
            ),
            boxShadow: [BoxShadow(color: TTColors.purple.withOpacity(0.08), blurRadius: 8)],
          ),
          child: const _TypingDots(),
        ),
      ]),
    );
  }

  // ── Zone de saisie TEXTE ──────────────────────────────────
  Widget _buildInputBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      decoration: const BoxDecoration(
        color: TTColors.white,
        border: Border(top: BorderSide(color: TTColors.border)),
        boxShadow: [BoxShadow(color: Color(0x0A000000), blurRadius: 10, offset: Offset(0, -2))],
      ),
      child: Row(children: [
        Expanded(
          child: TextField(
            controller: _inputCtrl,
            focusNode: _focusNode,
            textDirection: TextDirection.rtl,
            style: const TextStyle(fontFamily: 'Cairo', fontSize: 14, color: TTColors.text),
            decoration: InputDecoration(
              hintText: 'اكتب رسالتك هنا… ابدأ بـ عسلامة',
              hintStyle: const TextStyle(color: TTColors.muted, fontFamily: 'Cairo', fontSize: 13),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: const BorderSide(color: TTColors.border)),
              enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: const BorderSide(color: TTColors.border)),
              focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: const BorderSide(color: TTColors.purple, width: 2)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              filled: true, fillColor: TTColors.gray,
            ),
            onSubmitted: (_) => _sendMessage(),
            maxLines: 4, minLines: 1,
            textInputAction: TextInputAction.send,
          ),
        ),
        const SizedBox(width: 10),
        GestureDetector(
          onTap: _botTyping ? null : _sendMessage,
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: 48, height: 48,
            decoration: BoxDecoration(
              gradient: _botTyping
                  ? const LinearGradient(colors: [TTColors.muted, TTColors.muted])
                  : const LinearGradient(colors: [TTColors.purple, TTColors.purpleLight]),
              borderRadius: BorderRadius.circular(24),
              boxShadow: _botTyping ? [] : [BoxShadow(color: TTColors.purple.withOpacity(0.4), blurRadius: 10, offset: const Offset(0, 3))],
            ),
            child: Icon(
              _botTyping ? Icons.hourglass_empty_rounded : Icons.send_rounded,
              color: Colors.white, size: 20,
            ),
          ),
        ),
      ]),
    );
  }

  // ── Zone vocale ───────────────────────────────────────────
  Widget _buildVoiceZone() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
      decoration: const BoxDecoration(
        color: TTColors.white,
        border: Border(top: BorderSide(color: TTColors.border)),
        boxShadow: [BoxShadow(color: Color(0x0A000000), blurRadius: 10, offset: Offset(0, -2))],
      ),
      child: Column(
        children: [
          // ── Sélecteur STT : Whisper (backend) / On-device ──
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _sttModeChip('Whisper AI', Icons.cloud_rounded, _isWhisperMode, () {
                if (!_isListening && !_whisperLoading) setState(() => _isWhisperMode = true);
              }),
              const SizedBox(width: 8),
              _sttModeChip('Appareil', Icons.phone_android_rounded, !_isWhisperMode, () {
                if (!_isListening && !_whisperLoading) setState(() => _isWhisperMode = false);
              }),
            ],
          ),
          const SizedBox(height: 8),

          // Transcript preview
          if (_voiceTranscript.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: TTColors.purpleBg,
                border: Border.all(color: TTColors.purple.withOpacity(0.2)),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(children: [
                const Icon(Icons.format_quote_rounded, color: TTColors.purple, size: 16),
                const SizedBox(width: 8),
                Expanded(child: Text(_voiceTranscript,
                  style: const TextStyle(fontSize: 13, color: TTColors.purple, fontFamily: 'Cairo'),
                  textDirection: TextDirection.rtl,
                )),
              ]),
            ),

          // Visualiseur barres
          _buildAudioVisualizer(),
          const SizedBox(height: 12),

          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Bouton microphone
              GestureDetector(
                onTap: (_isWhisperMode || _speechAvailable) && !_whisperLoading
                    ? _toggleListening : null,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: 72, height: 72,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: _whisperLoading
                          ? [TTColors.muted, TTColors.muted]
                          : _isListening
                              ? [const Color(0xFFDC2626), const Color(0xFFEF4444)]
                              : [TTColors.purple, TTColors.purpleLight],
                    ),
                    shape: BoxShape.circle,
                    boxShadow: [BoxShadow(
                      color: (_isListening ? const Color(0xFFDC2626) : TTColors.purple).withOpacity(0.45),
                      blurRadius: _isListening ? 20 : 12,
                      spreadRadius: _isListening ? 4 : 0,
                      offset: const Offset(0, 4),
                    )],
                  ),
                  child: _whisperLoading
                      ? const SizedBox(width: 28, height: 28,
                          child: CircularProgressIndicator(strokeWidth: 3, color: Colors.white))
                      : Icon(
                          _isListening ? Icons.stop_rounded : Icons.mic_rounded,
                          color: Colors.white, size: 32,
                        ),
                ),
              ),
              if (_voiceTranscript.isNotEmpty) ...[
                const SizedBox(width: 16),
                GestureDetector(
                  onTap: _sendTranscript,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                    decoration: BoxDecoration(
                      color: TTColors.purpleBg,
                      border: Border.all(color: TTColors.purple.withOpacity(0.3)),
                      borderRadius: BorderRadius.circular(24),
                    ),
                    child: const Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.send_rounded, color: TTColors.purple, size: 16),
                      SizedBox(width: 6),
                      Text('Envoyer', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: TTColors.purple, fontFamily: 'Cairo')),
                    ]),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 8),

          // Statut
          Text(
            _whisperLoading
                ? 'Whisper AI transcrit… patienter'
                : _isListening
                    ? 'Enregistrement… parlez maintenant'
                    : !_isWhisperMode && !_speechAvailable
                        ? 'Microphone non disponible'
                        : _voiceTranscript.isNotEmpty
                            ? 'Transcrit — vérifiez et envoyez'
                            : _isWhisperMode
                                ? 'Appuyez — Whisper capte le dialecte tunisien'
                                : 'Appuyez pour parler',
            style: TextStyle(
              fontSize: 12, fontFamily: 'Cairo', fontWeight: FontWeight.w600,
              color: _isListening ? const Color(0xFFDC2626)
                  : _whisperLoading ? TTColors.teal : TTColors.muted,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _sttModeChip(String label, IconData icon, bool active, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? TTColors.purpleBg : TTColors.gray,
          border: Border.all(color: active ? TTColors.purple.withOpacity(0.4) : TTColors.border),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(icon, size: 13, color: active ? TTColors.purple : TTColors.muted),
          const SizedBox(width: 5),
          Text(label, style: TextStyle(
            fontSize: 11, fontFamily: 'Cairo', fontWeight: FontWeight.w600,
            color: active ? TTColors.purple : TTColors.muted,
          )),
        ]),
      ),
    );
  }

  Widget _buildAudioVisualizer() {
    return SizedBox(
      height: 28,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(5, (i) {
          return AnimatedBuilder(
            animation: _micAnimCtrl,
            builder: (_, __) {
              double h = 4;
              if (_isListening) {
                final offsets = [0.0, 0.2, 0.4, 0.6, 0.8];
                final v = (_micAnimCtrl.value + offsets[i]) % 1.0;
                h = 4 + 18 * (v < 0.5 ? v * 2 : (1 - v) * 2);
              }
              return Container(
                width: 4, height: h,
                margin: const EdgeInsets.symmetric(horizontal: 2),
                decoration: BoxDecoration(
                  color: _isListening ? TTColors.purple : TTColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              );
            },
          );
        }),
      ),
    );
  }

  // ── Barre évaluation ─────────────────────────────────────
  Widget _buildRatingBar() {
    final String title = _transferred
        ? 'Appel terminé — Évaluez l\'agent'
        : 'Évaluez votre expérience';
    final String subtitle = _transferred
        ? 'Comment s\'est passée votre prise en charge ? 🎧'
        : 'Votre avis nous aide à améliorer le service 🙏';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: _transferred ? const Color(0xFFFFF7ED) : TTColors.purpleBg,
        border: Border(top: BorderSide(
          color: _transferred ? const Color(0xFFFED7AA) : TTColors.purple.withOpacity(0.2),
        )),
      ),
      child: Column(children: [
        Text(title,
          style: TextStyle(
            fontSize: 13, fontWeight: FontWeight.w700,
            color: _transferred ? const Color(0xFFD97706) : TTColors.purple,
            fontFamily: 'Cairo')),
        const SizedBox(height: 4),
        Text(subtitle,
          style: const TextStyle(fontSize: 11, color: TTColors.muted, fontFamily: 'Cairo'), textAlign: TextAlign.center),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(5, (i) => GestureDetector(
            onTap: () => _submitRating(i + 1),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6),
              child: Icon(
                (_pendingRating != null && i < _pendingRating!)
                    ? Icons.star_rounded : Icons.star_outline_rounded,
                color: TTColors.orange, size: 32,
              ),
            ),
          )),
        ),
        const SizedBox(height: 8),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          TextButton(
            onPressed: () => setState(() => _showRating = false),
            child: const Text('Plus tard', style: TextStyle(fontSize: 12, color: TTColors.muted, fontFamily: 'Cairo')),
          ),
        ]),
      ]),
    );
  }

  // ── Barre de statut transfert (bas de l'écran) ────────────
  Widget _buildTransferredBar() {
    final bool waiting = _amiCalled && !_showRating; // Appel en cours, agent pas encore raccroché

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: waiting ? const Color(0xFFF0FDF4) : const Color(0xFFFFF7ED),
        border: Border(top: BorderSide(
          color: waiting ? const Color(0xFF86EFAC) : const Color(0xFFFED7AA),
        )),
      ),
      child: Row(children: [
        if (waiting) ...[
          const SizedBox(
            width: 14, height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF16A34A)),
          ),
          const SizedBox(width: 8),
          const Expanded(child: Text(
            '📞 Appel en cours — En attente que l\'agent raccroche…',
            style: TextStyle(fontSize: 12, color: Color(0xFF166534), fontFamily: 'Cairo'),
          )),
        ] else ...[
          const Icon(Icons.headset_mic_rounded, color: Color(0xFFD97706), size: 18),
          const SizedBox(width: 8),
          const Expanded(child: Text(
            'Transféré vers un agent humain — Contactez le 1298',
            style: TextStyle(fontSize: 12, color: TTColors.text, fontFamily: 'Cairo'),
          )),
        ],
        TextButton(
          onPressed: _newConversation,
          style: TextButton.styleFrom(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          ),
          child: const Text('Nouveau chat',
            style: TextStyle(fontSize: 12, color: TTColors.purple, fontWeight: FontWeight.w700, fontFamily: 'Cairo')),
        ),
      ]),
    );
  }

  // ── Helpers ───────────────────────────────────────────────
  bool _isArabic(String text) => RegExp(r'[\u0600-\u06FF]').hasMatch(text);

  String _formatTime(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
}


// ════════════════════════════════════════════════════════════
//  Animation "..." de frappe du bot
// ════════════════════════════════════════════════════════════

class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> {
  int _dotCount = 1;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(milliseconds: 500), (_) {
      if (mounted) setState(() => _dotCount = (_dotCount % 3) + 1);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (i) => AnimatedOpacity(
        opacity: i < _dotCount ? 1.0 : 0.2,
        duration: const Duration(milliseconds: 300),
        child: Container(
          width: 7, height: 7,
          margin: const EdgeInsets.symmetric(horizontal: 2),
          decoration: BoxDecoration(color: TTColors.purple, borderRadius: BorderRadius.circular(4)),
        ),
      )),
    );
  }
}
