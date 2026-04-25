// ════════════════════════════════════════════════════════════
//  Modèle Utilisateur — même structure que Firebase Firestore
// ════════════════════════════════════════════════════════════

class UserModel {
  final String uid;
  final String email;
  final String nom;
  final String prenom;
  final String telephone;
  final DateTime? createdAt;

  const UserModel({
    required this.uid,
    required this.email,
    required this.nom,
    required this.prenom,
    required this.telephone,
    this.createdAt,
  });

  String get fullName => '$prenom $nom';

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      uid: json['uid'] ?? '',
      email: json['email'] ?? '',
      nom: json['nom'] ?? '',
      prenom: json['prenom'] ?? '',
      telephone: json['telephone'] ?? '',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
    'uid': uid,
    'email': email,
    'nom': nom,
    'prenom': prenom,
    'telephone': telephone,
  };
}


// ════════════════════════════════════════════════════════════
//  Modèle Message de chat
// ════════════════════════════════════════════════════════════

class ChatMessage {
  final String role;   // 'user' ou 'bot'
  final String text;
  final DateTime timestamp;
  final bool isTransfer;

  const ChatMessage({
    required this.role,
    required this.text,
    required this.timestamp,
    this.isTransfer = false,
  });

  bool get isUser => role == 'user';
  bool get isBot  => role == 'bot' || role == 'assistant';

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      role: json['role'] ?? 'bot',
      text: json['text'] ?? json['content'] ?? '',
      timestamp: json['timestamp'] != null
          ? DateTime.tryParse(json['timestamp'].toString()) ?? DateTime.now()
          : DateTime.now(),
      isTransfer: json['is_transfer'] == true,
    );
  }
}


// ════════════════════════════════════════════════════════════
//  Modèle Conversation (historique)
// ════════════════════════════════════════════════════════════

class ConversationSummary {
  final String convId;
  final String firstMessage;
  final String lastMessage;
  final int messageCount;
  final String status;
  final DateTime? createdAt;
  final double? rating;

  const ConversationSummary({
    required this.convId,
    required this.firstMessage,
    required this.lastMessage,
    required this.messageCount,
    required this.status,
    this.createdAt,
    this.rating,
  });

  factory ConversationSummary.fromJson(Map<String, dynamic> json) {
    return ConversationSummary(
      convId: json['conv_id'] ?? json['id'] ?? '',
      firstMessage: json['first_message'] ?? '',
      lastMessage: json['last_message'] ?? '',
      messageCount: json['message_count'] ?? 0,
      status: json['status'] ?? 'open',
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'].toString())
          : null,
      rating: json['rating'] != null
          ? double.tryParse(json['rating'].toString())
          : null,
    );
  }
}


// ════════════════════════════════════════════════════════════
//  Top Issues (graphique camembert)
// ════════════════════════════════════════════════════════════

class TopIssue {
  final String label;
  final int count;

  const TopIssue({required this.label, required this.count});

  factory TopIssue.fromJson(Map<String, dynamic> json) => TopIssue(
    label: json['label']?.toString() ?? 'Autre',
    count: (json['count'] as num?)?.toInt() ?? 0,
  );
}


// ════════════════════════════════════════════════════════════
//  Statistiques utilisateur
// ════════════════════════════════════════════════════════════

class UserStats {
  final int totalConversations;
  final int resolvedConversations;
  final int transferredConversations;
  final double avgRating;

  const UserStats({
    required this.totalConversations,
    required this.resolvedConversations,
    required this.transferredConversations,
    required this.avgRating,
  });

  factory UserStats.fromJson(Map<String, dynamic> json) {
    return UserStats(
      totalConversations:    json['total_conversations'] ?? 0,
      resolvedConversations: json['resolved_conversations'] ?? 0,
      transferredConversations: json['transferred_conversations'] ?? 0,
      avgRating: double.tryParse(json['avg_rating']?.toString() ?? '0') ?? 0.0,
    );
  }
}
