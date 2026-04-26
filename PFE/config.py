# ============================================================
#  config.py — Configuration centrale du VoiceBot Tunisie Telecom
# ============================================================

import os

# ── Chemins ──────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH    = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")

# ── Source du dataset ─────────────────────────────────────────
# True  → charge depuis Firebase Firestore (collection "dataset_nlp")
#          avec fallback automatique vers le fichier JSONL si Firebase
#          est indisponible.
# False → charge uniquement depuis le fichier JSONL local.
USE_FIREBASE_DATASET = True
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
RAG_CONFIDENCE_THRESHOLD = 0.30        # Seuil réponse finale (étape 2) — en dessous → escalade
RAG_EXACT_THRESHOLD = 0.80             # Au dessus → réponse directe

# Seuil de confiance pour poser une question de clarification (étape 1).
# Doit être plus élevé que RAG_CONFIDENCE_THRESHOLD pour éviter les
# fausses questions sur des sujets hors dataset.
CLARIFICATION_CONFIDENCE_THRESHOLD = 0.50

# Seuil de confiance NLU minimum pour tenter la clarification.
# Si le ML est en dessous, le sujet est trop incertain → on saute l'étape 1.
NLU_MIN_CONFIDENCE_FOR_CLARI = 0.35

# Seuil RAG strict appliqué quand l'étape 1 est court-circuitée (sujet hors-dataset).
# Plus élevé que RAG_CONFIDENCE_THRESHOLD (0.30) pour forcer le transfert
# quand la requête ne correspond à rien dans le dataset.
RAG_STRICT_THRESHOLD = 0.45

# Seuil RAG strict appliqué APRÈS clarification (étape 2 depuis stage="clarifying").
# Plus élevé que RAG_STRICT_THRESHOLD car à ce stade l'user a déjà fourni sa réponse :
# si le RAG ne trouve toujours pas avec 0.60+ → le problème n'est pas dans le dataset
# → transfert immédiat, pas de boucle.
RAG_STRICT_THRESHOLD_AFTER_CLARI = 0.60

# Seuil RAG strict quand le NLU est peu confiant (< NLU_MIN_CONFIDENCE_FOR_CLARI).
# Si NLU < 0.35 ET RAG < 0.70 → problème probablement hors dataset → transfert immédiat.
# Évite les réponses fausses quand le NLU classifie à tort (ex: plainte générale → facturation).
RAG_STRICT_THRESHOLD_LOW_NLU = 0.70

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

# ── Coqui TTS (open-source, arabe + fine-tuning possible) ─────
# Installation : pip install TTS
# Modèle par défaut : arabe CSS10 VITS — bonne qualité, open-source, hors-ligne
# Pour fine-tuning tunisien : entraîner sur corpus darija puis pointer les chemins
#   custom ci-dessous.
# Ordre des priorités TTS : Coqui → edge-tts → ElevenLabs → gTTS
COQUI_TTS_MODEL        = "tts_models/ar/css10/vits"  # Modèle arabe pré-entraîné
COQUI_TTS_SPEAKER      = None   # Nom du speaker (si modèle multi-voix, sinon None)
COQUI_TTS_LANGUAGE     = None   # Langue (si modèle multilingue, sinon None)
# Fine-tuning tunisien : renseigner les chemins après entraînement
# Laisser vide ("") pour utiliser le modèle pré-entraîné standard
COQUI_TTS_CUSTOM_MODEL  = ""   # ex: "models/tts_tunisian/best_model.pth"
COQUI_TTS_CUSTOM_CONFIG = ""   # ex: "models/tts_tunisian/config.json"

# ── Clarification — Questions de précision ────────────────────
# Le bot pose des questions avant de répondre pour mieux comprendre
CLARIFICATION_ENABLED    = True
MAX_CLARIFICATION_TURNS  = 2      # Nb max de tours de clarification avant réponse

# ── Dialogue ─────────────────────────────────────────────────
MAX_TURNS           = 20              # Nombre max de tours avant clôture
GREETING_MESSAGE    = "مرحبا بيك في تليكوم تونس! أنا المساعد الآلي، كيفاش نجم نعاونك اليوم؟"
FAREWELL_MESSAGE    = "شكرن على اتصالك بتليكوم تونس، يوم سعيد!"
TRANSFER_MESSAGE    = "سامحني منجمش نحل المشكل، باش نحولك لوكيل بشري يعاونك."
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
    # ── Wilayas ──────────────────────────────────────────────────
    "تونس": "تونس",               "أريانة": "أريانة",
    "اريانة": "أريانة",           "بن عروس": "بن عروس",
    "منوبة": "منوبة",             "زغوان": "زغوان",
    "نابل": "نابل",               "بنزرت": "بنزرت",
    "الكاف": "الكاف",             "سليانة": "سليانة",
    "القيروان": "القيروان",        "القصرين": "القصرين",
    "قصرين": "القصرين",           "سيدي بوزيد": "سيدي بوزيد",
    "سوسة": "سوسة",               "المنستير": "المنستير",
    "المهدية": "المهدية",          "صفاقس": "صفاقس",
    "قابس": "قابس",               "مدنين": "مدنين",
    "تطاوين": "تطاوين",           "قفصة": "قفصة",
    "توزر": "توزر",               "قبلي": "قبلي",
    "جندوبة": "جندوبة",           "باجة": "باجة",
    # ── 1. تونس ──────────────────────────────────────────────────
    "تونس المدينة": "تونس المدينة","باب البحر": "باب البحر",
    "باب سويقة": "باب سويقة",     "سيدي البشير": "سيدي البشير",
    "الزهور": "الزهور",           "السيجومي": "السيجومي",
    "العمران": "العمران",          "العمران الأعلى": "العمران الأعلى",
    "التحرير": "التحرير",          "المنزه": "المنزه",
    "حي الخضراء": "حي الخضراء",   "الكبارية": "الكبارية",
    "جبل الجلود": "جبل الجلود",   "المرسى": "المرسى",
    "قرطاج": "قرطاج",             "حلق الوادي": "حلق الوادي",
    "باردو": "باردو",             "التضامن": "التضامن",
    "الملاسين": "الملاسين",        "الوردية": "الوردية",
    "سيدي حسين": "سيدي حسين",
    # ── 2. أريانة ────────────────────────────────────────────────
    "أريانة المدينة": "أريانة المدينة","سكرة": "سكرة",
    "رواد": "رواد",               "قلعة الأندلس": "قلعة الأندلس",
    "المنيهلة": "المنيهلة",
    # ── 3. بن عروس ───────────────────────────────────────────────
    "المروج": "المروج",           "حمام الأنف": "حمام الأنف",
    "حمام الشط": "حمام الشط",     "بومهل البساتين": "بومهل البساتين",
    "رادس": "رادس",               "مقرين": "مقرين",
    "فوشانة": "فوشانة",           "المحمدية": "المحمدية",
    "مرناق": "مرناق",             "الزهراء": "الزهراء",
    # ── 4. منوبة ─────────────────────────────────────────────────
    "دوار هيشر": "دوار هيشر",     "وادي الليل": "وادي الليل",
    "طبربة": "طبربة",             "المرناقية": "المرناقية",
    "برج العامري": "برج العامري", "البطان": "البطان",
    # ── 5. نابل ──────────────────────────────────────────────────
    "دار شعبان الفهري": "دار شعبان الفهري","بني خيار": "بني خيار",
    "الحمامات": "الحمامات",       "سليمان": "سليمان",
    "قرمبالية": "قرمبالية",       "منزل بوزلفة": "منزل بوزلفة",
    "تاكلسة": "تاكلسة",           "الهوارية": "الهوارية",
    "قربة": "قربة",               "الميدة": "الميدة",
    "بني خلاد": "بني خلاد",       "منزل تميم": "منزل تميم",
    "قليبية": "قليبية",           "اقليبية": "قليبية",
    "حمام الغزاز": "حمام الغزاز", "بوفيشة": "بوفيشة",
    # ── 6. زغوان ─────────────────────────────────────────────────
    "الفحص": "الفحص",             "بئر مشارقة": "بئر مشارقة",
    "الناظور": "الناظور",          "الزريبة": "الزريبة",
    "صواف": "صواف",
    # ── 7. بنزرت ─────────────────────────────────────────────────
    "جرزونة": "جرزونة",           "منزل بورقيبة": "منزل بورقيبة",
    "منزل جميل": "منزل جميل",     "العالية": "العالية",
    "رأس الجبل": "رأس الجبل",     "غار الملح": "غار الملح",
    "سجنان": "سجنان",             "ماطر": "ماطر",
    "جومين": "جومين",             "غزالة": "غزالة",
    "تينجة": "تينجة",             "أوتيك": "أوتيك",
    # ── 8. باجة ──────────────────────────────────────────────────
    "عمدون": "عمدون",             "نفزة": "نفزة",
    "تستور": "تستور",             "تيبار": "تيبار",
    "مجاز الباب": "مجاز الباب",   "قبلاط": "قبلاط",
    "تبرسق": "تبرسق",
    # ── 9. جندوبة ────────────────────────────────────────────────
    "بوسالم": "بوسالم",           "بلطة بوعوان": "بلطة بوعوان",
    "طبرقة": "طبرقة",             "عين دراهم": "عين دراهم",
    "غار الدماء": "غار الدماء",   "فرنانة": "فرنانة",
    "الفرنانة": "فرنانة",          "وادي مليز": "وادي مليز",
    # ── 10. الكاف ────────────────────────────────────────────────
    "تاجروين": "تاجروين",         "الدهماني": "الدهماني",
    "السرس": "السرس",             "نبر": "نبر",
    "قلعة سنان": "قلعة سنان",     "ساقية سيدي يوسف": "ساقية سيدي يوسف",
    "الجريصة": "الجريصة",         "القلعة الخصبة": "القلعة الخصبة",
    "الطويرف": "الطويرف",
    # ── 11. سليانة ───────────────────────────────────────────────
    "الكريب": "الكريب",           "بوعرادة": "بوعرادة",
    "قعفور": "قعفور",             "الروحية": "الروحية",
    "برقو": "برقو",               "مكثر": "مكثر",
    "كسرى": "كسرى",               "سيدي بورويس": "سيدي بورويس",
    "العروسة": "العروسة",
    # ── 12. القيروان ─────────────────────────────────────────────
    "الشبيكة": "الشبيكة",         "السبيخة": "السبيخة",
    "الوسلاتية": "الوسلاتية",     "حفوز": "حفوز",
    "العلا": "العلا",             "نصر الله": "نصر الله",
    "حاجب العيون": "حاجب العيون", "منزل المهيري": "منزل المهيري",
    "الشراردة": "الشراردة",       "بوحجلة": "بوحجلة",
    "عين جلولة": "عين جلولة",
    # ── 13. القصرين ──────────────────────────────────────────────
    "سبيبة": "سبيبة",             "سبيطلة": "سبيطلة",
    "تالة": "تالة",               "حاسي الفريد": "حاسي الفريد",
    "فوسانة": "فوسانة",           "فريانة": "فريانة",
    "ماجل بلعباس": "ماجل بلعباس", "جدليان": "جدليان",
    "العيون": "العيون",            "حيدرة": "حيدرة",
    # ── 14. سيدي بوزيد ───────────────────────────────────────────
    "الرقاب": "الرقاب",           "المكناسي": "المكناسي",
    "منزل بوزيان": "منزل بوزيان", "بئر الحفي": "بئر الحفي",
    "جلمة": "جلمة",               "السبالة": "السبالة",
    "المزونة": "المزونة",          "السوق الجديد": "السوق الجديد",
    "أولاد حفوز": "أولاد حفوز",   "السعيدة": "السعيدة",
    # ── 15. سوسة ─────────────────────────────────────────────────
    "مساكن": "مساكن",             "القلعة الكبرى": "القلعة الكبرى",
    "القلعة الصغرى": "القلعة الصغرى","أكودة": "أكودة",
    "حمام سوسة": "حمام سوسة",     "هرقلة": "هرقلة",
    "كندار": "كندار",             "النفيضة": "النفيضة",
    # ── 16. المنستير ─────────────────────────────────────────────
    "قصر هلال": "قصر هلال",       "قصيبة المديوني": "قصيبة المديوني",
    "طبلبة": "طبلبة",             "المكنين": "المكنين",
    "جمال": "جمال",               "زرمدين": "زرمدين",
    "بني حسان": "بني حسان",       "وردانين": "وردانين",
    "الساحلين": "الساحلين",        "صيادة": "صيادة",
    "لمطة": "لمطة",               "بوحجر": "بوحجر",
    # ── 17. المهدية ──────────────────────────────────────────────
    "قصور الساف": "قصور الساف",   "الشابة": "الشابة",
    "ملولش": "ملولش",             "سيدي علوان": "سيدي علوان",
    "أولاد الشامخ": "أولاد الشامخ","بومرداس": "بومرداس",
    "هبيرة": "هبيرة",             "السواسي": "السواسي",
    "كركر": "كركر",               "البرادعة": "البرادعة",
    "الجم": "الجم",
    # ── 18. صفاقس ────────────────────────────────────────────────
    "ساقية الزيت": "ساقية الزيت", "ساقية الدائر": "ساقية الدائر",
    "جبنيانة": "جبنيانة",         "العامرة": "العامرة",
    "المحرس": "المحرس",            "عقارب": "عقارب",
    "قرقنة": "قرقنة",             "منزل شاكر": "منزل شاكر",
    "بئر علي بن خليفة": "بئر علي بن خليفة","الصخيرة": "الصخيرة",
    "الغريبة": "الغريبة",          "الحنشة": "الحنشة",
    "منزل شكار": "منزل شكار",
    # ── 19. قفصة ─────────────────────────────────────────────────
    "الرديف": "الرديف",           "المتلوي": "المتلوي",
    "أم العرائس": "أم العرائس",   "المظيلة": "المظيلة",
    "سيدي عيش": "سيدي عيش",       "القطار": "القطار",
    "بلخير": "بلخير",             "زانوش": "زانوش",
    "السند": "السند",
    # ── 20. توزر ─────────────────────────────────────────────────
    "دقاش": "دقاش",               "نفطة": "نفطة",
    "تمغزة": "تمغزة",             "حامة الجريد": "حامة الجريد",
    # ── 21. قبلي ─────────────────────────────────────────────────
    "دوز": "دوز",                 "دوز الشمالية": "دوز الشمالية",
    "دوز الجنوبية": "دوز الجنوبية","سوق الأحد": "سوق الأحد",
    "الفوار": "الفوار",            "رجيم معتوق": "رجيم معتوق",
    # ── 22. قابس ─────────────────────────────────────────────────
    "الحامة": "الحامة",           "مارث": "مارث",
    "مطماطة": "مطماطة",           "مطماطة الجديدة": "مطماطة الجديدة",
    "غنوش": "غنوش",               "وذرف": "وذرف",
    "منزل الحبيب": "منزل الحبيب",
    # ── 23. مدنين ────────────────────────────────────────────────
    "جرجيس": "جرجيس",             "بن قردان": "بن قردان",
    "بنقردان": "بن قردان",         "جربة حومة السوق": "جربة حومة السوق",
    "حومة السوق": "حومة السوق",   "جربة ميدون": "جربة ميدون",
    "جربة أجيم": "جربة أجيم",     "سيدي مخلوف": "سيدي مخلوف",
    "بني خداش": "بني خداش",       "زرزيس": "زرزيس",
    "بوقرارة": "بوقرارة",
    # ── 24. تطاوين ───────────────────────────────────────────────
    "غمراسن": "غمراسن",           "رمادة": "رمادة",
    "البئر الأحمر": "البئر الأحمر","ذهيبة": "ذهيبة",
    "الصمار": "الصمار",
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
    # تعابير تونسية للشكر
    "يعطيك الصحة", "يعطيك صحة", "يعطيك الصحه", "يعطيك صحه",
    "يعطيك", "عطيك الصحة", "عطيك صحة",
    # français
    "merci", "parfait", "bravo", "bravoo",
]

THANKS_MESSAGE = (
    "يعطيك الصحة! يسعدنا خدمتك. "
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

# ── Mots-clés de négation (user répond "non" à une question de clarification) ──
# Détectés à l'étape 2 pour retourner une réponse alternative
# ⚠️  IMPORTANT — Règles de détection négation/affirmation :
#
#  1. AFFIRMATION_KEYWORDS est vérifié EN PREMIER dans _is_negation().
#     Si l'user dit "إي", "نعم", "أيوا"… → return False immédiatement.
#     Cela évite les faux positifs sur des phrases comme :
#       "إي نعم، لومبة لوس (LOS) تشعل بالأحمر"
#       qui contient "لا" dans "بالأحمر" (بال+اح → "لا" en substring).
#
#  2. Les keywords courts (≤ 3 chars comme "لا") sont matchés
#     avec word-boundary dans _is_negation() → ne matchent PAS au milieu
#     d'un mot composé comme "بالأحمر", "بلاصة", "غلا".
AFFIRMATION_KEYWORDS = [
    "إي", "اي", "نعم", "أيوا", "ايوا", "أيه", "ايه",
    "صحيح", "صح", "بالضبط", "أكيد", "اكيد",
    "يزي", "يزي يزي",
    "oui", "yes", "yep",
    "إي نعم", "اي نعم",
]

NEGATION_KEYWORDS = [
    # Phrases longues — matchées sans word-boundary (suffisamment spécifiques)
    "لا معنديش", "لا ما عنديش", "لا مانجمش",
    "ماعنديش", "معنديش", "ما عنديش",
    "مانجمش", "ما نجمش",
    "مش عندي", "ما عندي",
    "مش موجود", "ماهوش موجود",
    "ما عندي رقم", "ما حفظتش",
    "مش لاقي", "ما لقيتش",
    "فقدت الرقم", "ما حفظتش الرقم",
    # Keywords courts — matchés avec word-boundary dans _is_negation()
    # (≤ 3 chars) pour éviter les faux positifs dans les mots composés
    "لا",        # ⚠️  word-boundary obligatoire (بالأحمر contient "لا")
    "لا عندي",
    "non", "nope",
]

# Réponse quand le user répond négativement à une question de clarification
# (ex: "لا معنديش" quand le bot demande رقم المعاملة, ou toute autre info)
NEGATION_CLARIFICATION_RESPONSE = (
    "مش مشكلة، تنجم تمشي لاقرب وكالة تليكوم تاعنا "
    "وهما ينجموا يعاونوك مباشرة."
)
