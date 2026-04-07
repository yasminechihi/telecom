# ============================================================
#  config.py — Configuration centrale du VoiceBot Tunisie Telecom
# ============================================================

import os

# ── Chemins ──────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH    = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")
MODELS_DIR      = os.path.join(BASE_DIR, "models")
LOGS_DIR        = os.path.join(BASE_DIR, "logs")
DATA_DIR        = os.path.join(BASE_DIR, "data")

# Fichiers générés
FAISS_INDEX_PATH     = os.path.join(MODELS_DIR, "faiss_index.bin")
EMBEDDINGS_PATH      = os.path.join(MODELS_DIR, "embeddings.npy")
DATASET_CACHE_PATH   = os.path.join(MODELS_DIR, "dataset_cache.pkl")
LEARNED_DATA_PATH    = os.path.join(DATA_DIR,   "learned_interactions.jsonl")
CONVERSATION_LOG     = os.path.join(LOGS_DIR,   "conversations.jsonl")

# ── Modèle STT — Whisper ─────────────────────────────────────
STT_MODEL           = "medium"          # tiny / base / small / medium / large-v3
STT_LANGUAGE        = "ar"              # Arabe (couvre le darija tunisien)
STT_DEVICE          = "cpu"             # "cuda" si GPU disponible
STT_BEAM_SIZE       = 5
STT_VAD_FILTER      = True             # Filtre silence/bruit → améliore détection
STT_SILENCE_TIMEOUT = 2.0              # secondes de silence pour arrêter l'enregistrement
STT_TEMPERATURE     = 0.0              # 0 = greedy (plus précis, moins d'hallucinations)
STT_NO_SPEECH_THRESHOLD = 0.6          # Seuil pour rejeter les segments sans parole
# Prompt initial : guide Whisper vers le dialectal tunisien
# Inclure des mots clés darija + contexte télécom pour ancrer le vocabulaire
STT_INITIAL_PROMPT  = (
    "هذا تسجيل صوتي لعميل تليكوم تونس يتكلم بالدارجة التونسية. "
    "الكلمات الشائعة: عسلامة، الريزو، الإنترنت، الموبيل، الموديم، "
    "الفاتورة، الرصيد، تليفون، بوجار، ياسر، برشا، مش، ميفوتش، "
    "المنستير، سوسة، صفاقس، تونس، قصر هلال، بنزرت."
)

# ── Modèle d'embedding — Multilingue ─────────────────────────
EMBEDDING_MODEL     = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Alternative plus puissante : "intfloat/multilingual-e5-small"

# ── Moteur RAG — Seuils ──────────────────────────────────────
RAG_TOP_K           = 5                # Nombre de résultats à récupérer
RAG_CONFIDENCE_THRESHOLD = 0.30        # Abaissé 0.55→0.30 : l'index enrichi donne des scores plus fiables
RAG_EXACT_THRESHOLD = 0.80             # Au dessus → réponse directe

# ── Audio ─────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE   = 16000            # Hz
AUDIO_CHANNELS      = 1
AUDIO_CHUNK_SIZE    = 1024
MAX_RECORD_SECONDS  = 30               # Durée max d'un tour de parole

# ── TTS ───────────────────────────────────────────────────────
TTS_LANGUAGE        = "ar"             # gTTS langue
TTS_SLOW            = False
TTS_ENGINE          = "edge-tts"       # "edge-tts" | "gtts" | "elevenlabs"

# ── edge-tts (Microsoft Neural TTS — GRATUIT, aucune clé) ─────
# Voix neurales tunisiennes disponibles :
#   "ar-TN-ReemNeural"   → Femme tunisienne  (chaleureuse, naturelle) ← recommandé
#   "ar-TN-HediNeural"   → Homme tunisien
#   "ar-SA-ZariyahNeural"→ Femme arabe standard (si voix TN non disponible)
EDGE_TTS_VOICE      = "ar-TN-ReemNeural"

# ── ElevenLabs TTS (voix masculine tunisienne) ────────────────
ELEVENLABS_API_KEY  = "YOUR_API_KEY_HERE"   # ← remplace par ta clé ElevenLabs
# Voix masculine multilingue (arabe/darija) — options :
#   "pNInz6obpgDQGcFmaJgB"  = Adam       (voix neutre masculine)
#   "VR6AewLTigWG4xSOukaG"  = Arnold     (voix grave masculine)
#   "ErXwobaYiN019PkySvjV"  = Antoni     (voix chaude masculine)
#   "TxGEqnHWrfWFTfGW9XjX"  = Josh       (voix jeune masculine)  ← recommandé
ELEVENLABS_VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"   # Josh — voix masculine naturelle
ELEVENLABS_MODEL    = "eleven_multilingual_v2"   # Supporte arabe + darija + français
ELEVENLABS_STABILITY      = 0.55   # 0.0-1.0 (plus haut = plus stable/monotone)
ELEVENLABS_SIMILARITY     = 0.80   # Fidélité à la voix
ELEVENLABS_STYLE          = 0.20   # Expressivité (0 = neutre, 1 = très expressif)
ELEVENLABS_SPEAKER_BOOST  = True   # Améliore la clarté

# ── Clarification — Questions de précision ────────────────────
# Le bot pose des questions avant de répondre pour mieux comprendre
CLARIFICATION_ENABLED    = True
MAX_CLARIFICATION_TURNS  = 2      # Nb max de tours de clarification avant réponse

# ── Dialogue ─────────────────────────────────────────────────
MAX_TURNS           = 20              # Nombre max de tours avant clôture
GREETING_MESSAGE    = "مرحبا بيك في تليكوم تونس! أنا المساعد الآلي، كيفاش نجم نعاونك اليوم؟"
FAREWELL_MESSAGE    = "شكرن على اتصالك بتليكوم تونس، يوم سعيد!"
TRANSFER_MESSAGE    = "نحولك لوكيل بشري متخصص، استنى برشا."
NOT_UNDERSTOOD_MSG  = "سامحني ما فهمتش برشا، قادر تعاود تقول؟"
# Demande de précision sur la délégation (utilisé quand seule la wilaya est connue)
# {wilaya} est remplacé dynamiquement par la wilaya détectée
DELEGATION_QUESTION = "وكذلك، قولي من أي معتمدية في {wilaya}؟"
ESCALATION_ATTEMPTS = 2               # Nb d'essais avant transfert auto

# ── Transfert humain ─────────────────────────────────────────
HUMAN_AGENT_QUEUE   = os.path.join(DATA_DIR, "human_queue.jsonl")
HUMAN_AGENT_EMAIL   = "support@tunisietelecom.tn"   # Notification optionnelle

# ── Apprentissage continu ────────────────────────────────────
AUTO_RETRAIN        = True            # Réentraîner après N nouvelles interactions
RETRAIN_THRESHOLD   = 50             # Nb interactions avant réentraînement

# ── Logging ──────────────────────────────────────────────────
LOG_LEVEL           = "INFO"
LOG_CONVERSATIONS   = True

# ── Localisations tunisiennes (pour substitution dans les réponses RAG) ──
# Clé = forme mentionnée dans le texte, valeur = forme canonique
TUNISIAN_LOCATIONS = {
    # Gouvernorats / Wilayas
    "تونس": "تونس", "أريانة": "أريانة", "اريانة": "أريانة",
    "بن عروس": "بن عروس", "منوبة": "منوبة", "زغوان": "زغوان",
    "نابل": "نابل", "بنزرت": "بنزرت", "الكاف": "الكاف",
    "سليانة": "سليانة", "قصرين": "قصرين", "القصرين": "القصرين",
    "سيدي بوزيد": "سيدي بوزيد", "القيروان": "القيروان",
    "سوسة": "سوسة", "المنستير": "المنستير", "المهدية": "المهدية",
    "صفاقس": "صفاقس", "قابس": "قابس", "مدنين": "مدنين",
    "تطاوين": "تطاوين", "قفصة": "قفصة", "توزر": "توزر",
    "جندوبة": "جندوبة", "باجة": "باجة",
    # Délégations / villes importantes
    "بوحجلة": "بوحجلة", "حجلة": "بوحجلة",
    "حمام الأنف": "حمام الأنف", "رادس": "رادس",
    "المرسى": "المرسى", "قرطاج": "قرطاج",
    "حلق الوادي": "حلق الوادي", "الزهراء": "الزهراء",
    "مجاز الباب": "مجاز الباب", "طبرقة": "طبرقة",
    "بوسالم": "بوسالم", "عين دراهم": "عين دراهم",
    "سبيطلة": "سبيطلة", "تالة": "تالة",
    "الحمامات": "الحمامات", "قربة": "قربة",
    "الجم": "الجم", "اقليبية": "اقليبية",
    "الشابة": "الشابة", "بوقرارة": "بوقرارة",
    "جرجيس": "جرجيس", "بنقردان": "بنقردان",
    "زرزيس": "زرزيس", "رمادة": "رمادة",
    "حومة السوق": "حومة السوق", "قليبية": "قليبية",
    "الفرنانة": "الفرنانة", "نفطة": "نفطة",
    "دقاش": "دقاش", "ماطر": "ماطر",
    "منزل بورقيبة": "منزل بورقيبة", "غار الملح": "غار الملح",
    "تينجة": "تينجة", "منزل تميم": "منزل تميم",
    "قعفور": "قعفور", "المكنين": "المكنين",
    "المطوية": "المطوية", "الرقاب": "الرقاب",
    "عين جلولة": "عين جلولة", "حفوز": "حفوز",
    "العيون": "العيون", "الدهماني": "الدهماني",
    "تبرسق": "تبرسق", "بوعرادة": "بوعرادة",
    "العلا": "العلا", "جدليان": "جدليان",
    "الفحص": "الفحص", "المحرين": "المحرين",
}

# ── Mots-clés de salutation (le user doit commencer par ça) ──
GREETING_KEYWORDS = [
    "عسلامة", "السلام", "مرحبا", "أهلا", "اهلا", "آهلا",
    "هلو", "هالو", "bonjour", "salut", "hello", "hi",
    "سلامتك", "صباح الخير", "مساء الخير", "كيف حالك",
]

# ── Mots-clés de remerciement (après réception de la solution) ─
THANKS_KEYWORDS = [
    # عربي / دارجة
    "شكرن", "شكرا", "شكراً", "شكرًا", "شكر",
    "يعيشك", "عيشك", "مشكور", "يبارك فيك",
    "مرسي", "ميرسي", "بارك الله", "يبارك", "ربي يحفظك",
    "برابر", "مزيان",
    # français
    "merci", "parfait", "bravo", "bravoo",
]

THANKS_MESSAGE = (
    "يسعدنا خدمتك! "
    "إذا عندك أي مشكلة أخرى، إحنا هنا دايماً. "
    "يوم سعيد وربي يحفظك!"
)

# ── Mots-clés d'arrêt (client peut quitter à tout moment) ────
# Note : يعيشك / شكرن / مرسي → déplacés vers THANKS_KEYWORDS
STOP_KEYWORDS = [
    "وداعا", "باي", "خلاص", "بسلامة",
    "yezzi", "ما نحتاجش",
    "اوقف", "stop", "quitter", "fin", "terminer"
]
