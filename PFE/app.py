#!/usr/bin/env python3
# ============================================================
#  app.py — Interface Web VoiceBot Tunisie Telecom
#  Flask backend — Dialogue naturel en 2 étapes
#
#  Flow :
#    1. User décrit problème  → Bot pose une QUESTION (du dataset)
#    2. User répond           → Bot donne la RÉPONSE finale (RAG)
#
#  Stack : Whisper STT + AraBERT/TF-IDF NLU + FAISS RAG
#          + ElevenLabs TTS + Apprentissage continu
# ============================================================

import os, sys, json, uuid, logging, tempfile, re, io
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as Config

from modules.ml_predictor    import MLPredictor
from modules.nlu             import NLUModule, DELEGATION_WILAYA_MAP
from modules.response_engine import ResponseEngine
from modules.learning        import LearningModule
from modules.human_transfer  import HumanTransfer

# ── Toutes les localisations tunisiennes connues (triées longueur desc) ───────
# Construites une seule fois au démarrage pour _localize_response()
_ALL_TUNISIAN_LOCS = sorted(
    set(DELEGATION_WILAYA_MAP.keys()) | set(DELEGATION_WILAYA_MAP.values()),
    key=len, reverse=True
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "tt_voicebot_2026"

# ── Chargement modules ────────────────────────────────────────
logger.info("Chargement modules...")
ml_predictor   = MLPredictor(Config)
nlu            = NLUModule(Config, ml_predictor=ml_predictor)
response_eng   = ResponseEngine(Config)
learning       = LearningModule(Config)
transfer       = HumanTransfer(Config)

logger.info(f"ML Backend : {ml_predictor.backend_name}")

# Whisper STT
stt_model = None
try:
    from faster_whisper import WhisperModel
    stt_model = WhisperModel(Config.STT_MODEL, device=Config.STT_DEVICE, compute_type="int8")
    logger.info("Whisper chargé.")
except Exception as e:
    logger.warning(f"Whisper non dispo: {e}")

logger.info("✅ Modules prêts.")

# ── Coqui TTS — chargement lazy (au premier appel /api/tts) ──
_coqui_tts_instance = None   # initialisé à None, chargé à la demande

def _get_coqui_tts():
    """
    Chargement lazy du modèle Coqui TTS.
    - Si COQUI_TTS_CUSTOM_MODEL est défini dans config.py → utilise le modèle fine-tuné.
    - Sinon → utilise le modèle arabe pré-entraîné (tts_models/ar/css10/vits).
    Retourne None si la bibliothèque TTS n'est pas installée.
    """
    global _coqui_tts_instance
    if _coqui_tts_instance is not None:
        return _coqui_tts_instance
    try:
        from TTS.api import TTS as CoquiTTS
        custom_model  = getattr(Config, "COQUI_TTS_CUSTOM_MODEL",  "")
        custom_config = getattr(Config, "COQUI_TTS_CUSTOM_CONFIG", "")
        if custom_model and os.path.isfile(custom_model):
            logger.info(f"Coqui TTS : chargement modèle fine-tuné → {custom_model}")
            _coqui_tts_instance = CoquiTTS(
                model_path=custom_model,
                config_path=custom_config or None,
            )
        else:
            model_name = getattr(Config, "COQUI_TTS_MODEL", "tts_models/ar/css10/vits")
            logger.info(f"Coqui TTS : chargement modèle standard → {model_name}")
            _coqui_tts_instance = CoquiTTS(model_name)
        logger.info("✅ Coqui TTS prêt.")
        return _coqui_tts_instance
    except ImportError:
        logger.info("Coqui TTS non installé (pip install TTS) → fallback edge-tts/gTTS")
        return None
    except Exception as e:
        logger.warning(f"Coqui TTS échec chargement : {e} → fallback edge-tts/gTTS")
        return None

# ── Sessions ──────────────────────────────────────────────────
sessions = {}

# ── Apprentissage global (toutes sessions, perdu au redémarrage) ──────────────
# Réponses apprises des agents humains — partagées entre toutes les sessions
# tant que le serveur tourne. Oublié dès que le serveur est redémarré.
_global_learned_responses = []   # liste de {problem_text, response_text, embedding}

# ════════════════════════════════════════════════════════════
#  Helpers NLU / Localisation — portés depuis user_app.py
# ════════════════════════════════════════════════════════════

def _norm_intent_key(s: str) -> str:
    """Normalise une clé d'intent : ة→ه, variantes alef→ا, espaces normalisés."""
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('ة', 'ه').replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    return s

# ── Wilayas tunisiennes pour détection dans les réponses RAG ──────────────────
_WILAYA_RAW_DETECT = sorted([
    "سيدي بوزيد", "بن عروس",  "القيروان", "القصرين",
    "المنستير",   "المهدية",  "أريانة",   "اريانة",
    "جندوبة",     "بنزرت",    "تطاوين",   "صفاقس",
    "مدنين",      "سليانة",   "قفصة",     "سوسة",
    "الكاف",      "منوبة",    "قابس",     "توزر",
    "زغوان",      "قصرين",    "نابل",     "باجة",
    "قبلي",
], key=len, reverse=True)

_WILAYA_DETECT_RE = re.compile(
    "(" + "|".join(re.escape(w) for w in _WILAYA_RAW_DETECT) + ")"
)

def _response_has_wilaya(text: str) -> bool:
    """Retourne True si la réponse RAG contient un nom de wilaya hardcodé."""
    return bool(text and _WILAYA_DETECT_RE.search(text))

def _extract_wilaya_from_text(text: str) -> str:
    """Détecte une wilaya directement dans le texte utilisateur (regex fallback)."""
    if not text:
        return ""
    m = _WILAYA_DETECT_RE.search(text)
    return m.group(0) if m else ""

def _extract_delegation_from_text(text: str) -> str:
    """
    Extrait la معتمدية depuis le texte.
    1. Pattern 'في X' où X n'est pas un nom de wilaya connu.
    2. Fallback direct : vérifie si le texte (ou un token) est une معتمدية connue
       dans DELEGATION_WILAYA_MAP — couvre le cas où l'user répond juste "الحمامات".
    """
    if not text:
        return ""
    # ── Passe 1 : pattern "في X" ─────────────────────────────────────────────
    candidates = re.findall(r'في\s+([\u0600-\u06FF\s\-]{2,30}?)(?:\s*[،,\.\!؟]|$)', text)
    for cand in candidates:
        cand = cand.strip()
        if cand and not _WILAYA_DETECT_RE.fullmatch(cand):
            return cand
    # ── Passe 2 : lookup direct dans DELEGATION_WILAYA_MAP ───────────────────
    text_clean = text.strip()
    if text_clean in DELEGATION_WILAYA_MAP and not _WILAYA_DETECT_RE.fullmatch(text_clean):
        return text_clean
    for token in text_clean.split():
        token = token.strip()
        if token in DELEGATION_WILAYA_MAP and not _WILAYA_DETECT_RE.fullmatch(token):
            return token
    return ""

# ── Intents sensibles à la localisation ───────────────────────────────────────
def _needs_location_intent(intent: str) -> bool:
    """True si l'intent nécessite une localisation (wilaya + délégation)."""
    if not intent:
        return False
    loc_intents = getattr(Config, "LOCATION_DEPENDENT_INTENTS", set())
    intent_norm = _norm_intent_key(intent)
    return intent_norm in {_norm_intent_key(i) for i in loc_intents}

def _needs_location(entities: dict, intent: str = "") -> bool:
    """True si l'intent nécessite une localisation ET ni wilaya ni délégation ne sont connues."""
    if not _needs_location_intent(intent):
        return False
    if not entities:
        return True
    return not bool(entities.get("wilaya", "")) and not bool(entities.get("delegation", ""))

# ── Intents qui ne déclenchent jamais de transfert ────────────────────────────
_NO_TRANSFER_INTENTS_NORM: frozenset = frozenset(
    _norm_intent_key(k) for k in {
        "استفسار عن التغطية",
        "استفسار عن التغطيه",
    }
)

def _is_no_transfer_intent(intent: str) -> bool:
    return bool(intent and _norm_intent_key(intent.strip()) in _NO_TRANSFER_INTENTS_NORM)

# ── Regex numéro de demande ────────────────────────────────────────────────────
_ASK_NUMBER_RE      = re.compile(r'[اأ]عطيني\s*(الرقم|رقم)', re.UNICODE)
_CALLBACK_NUMBER_RE = re.compile(r'خلّ?[يا][لن]ي\s*رقمك', re.UNICODE)

# ── Intents qui nécessitent TOUJOURS le numéro de demande avant réponse ───────
_ASK_NUMBER_INTENTS_NORM: frozenset = frozenset(
    _norm_intent_key(k) for k in {
        "مشكلة في الدفع",    "مشكله في الدفع",
        "اعتراض على الفاتورة", "اعتراض على الفاتوره",
        "انقطاع الانترنات",  "انقطاع الانترنت",
        "تأخير في التركيب",  "تاخير في التركيب",
    }
)

def _is_ask_number_intent(intent: str) -> bool:
    """True si cet intent doit TOUJOURS passer par la demande du numéro de demande."""
    return bool(intent and _norm_intent_key(intent.strip()) in _ASK_NUMBER_INTENTS_NORM)


def get_session(sid: str) -> dict:
    if sid not in sessions:
        sessions[sid] = {
            "id":               sid,
            "history":          [],
            "turn":             0,
            "transferred":      False,
            "stage":            "waiting_greeting",   # attend la salutation du user
            "pending_intent":   "",
            "original_problem": "",   # Problème initial (étape 1)
            "collected_entities": {},
            "solution_given":   False,  # True après qu'une réponse finale a été fournie
            "start":            datetime.now().isoformat(),
            # ── Apprentissage éphémère (session uniquement) ──────────────
            # Liste de {problem_text, response_text, embedding} appris depuis
            # les réponses d'agents humains DANS cette session.
            # Oublié dès la fermeture de session ou le redémarrage de l'app.
            "session_learned_responses": [],
            "last_transferred_problem":  "",  # texte du problème qui a déclenché le dernier transfert
        }
    return sessions[sid]

# ════════════════════════════════════════════════════════════
#  Apprentissage éphémère (session uniquement)
# ════════════════════════════════════════════════════════════

def _session_learn_store(sess, problem_text, response_text):
    """
    Stocke une réponse apprise dans DEUX niveaux :
      1. Store global (_global_learned_responses) : partagé entre toutes les sessions,
         persiste tant que le serveur tourne, oublié au redémarrage.
      2. Store session (sess["session_learned_responses"]) : pour compatibilité.

    TOUJOURS stocke le texte, et TENTE d'ajouter l'embedding en bonus.
    """
    global _global_learned_responses

    entry = {
        "problem_text":  problem_text.strip(),
        "response_text": response_text.strip(),
        "embedding":     None,   # sera ajouté si le modèle est dispo
    }

    # Tenter d'ajouter l'embedding (optionnel, améliore la détection des reformulations)
    if response_eng.model is not None:
        try:
            entry["embedding"] = response_eng.model.encode([problem_text])[0]
            logger.info(
                f"[Global Learning] Embedding calculé pour '{problem_text[:50]}'"
            )
        except Exception as _e:
            logger.warning(f"[Global Learning] Embedding échoué (text-only mode) : {_e}")
    else:
        logger.warning("[Global Learning] Modèle embedding None — stockage texte seulement")

    # ── Niveau 1 : store global (toutes sessions) ──────────────
    _global_learned_responses.append(entry)
    logger.info(
        f"[Global Learning] ✅ Réponse mémorisée (global #{len(_global_learned_responses)}) : "
        f"'{problem_text[:50]}' → '{response_text[:50]}'"
    )

    # ── Niveau 2 : store session (compatibilité) ───────────────
    sess.setdefault("session_learned_responses", []).append(entry)
    logger.info(
        f"[Global Learning] ✅ Aussi dans session #{len(sess['session_learned_responses'])}"
    )


def _find_session_learned_response(sess, query_text):
    """
    Cherche si query_text correspond à un problème déjà résolu par un agent
    humain DANS CETTE SESSION.

    Stratégie multi-couches (du plus fiable au plus souple) :
      1. Correspondance exacte (score 1.0)
      2. Sous-chaîne (score 0.92)
      3. Recoupement de mots-clés ≥ 2 mots (score proportionnel)
      4. Similarité cosinus embedding ≥ 0.62

    Retourne la réponse apprise ou None.
    Oublié au redémarrage du serveur (in-memory uniquement).
    """
    # ── Priorité au store global : contient les réponses de TOUTES les sessions ──
    # Si vide, fallback sur le store session (compatibilité)
    learned = _global_learned_responses or sess.get("session_learned_responses", [])
    if not learned:
        return None

    logger.info(
        f"[Global Learning] Vérification : {len(learned)} réponse(s) en mémoire globale "
        f"pour query='{query_text[:50]}'"
    )

    import numpy as np

    # Pré-calculer l'embedding de la requête une seule fois (si modèle dispo)
    q_emb = None
    if response_eng.model is not None:
        try:
            q_emb = response_eng.model.encode([query_text])[0]
        except Exception as _e:
            logger.warning(f"[Global Learning] Erreur encoding requête : {_e}")

    best_score, best_resp, best_problem, best_method = 0.0, None, "", "—"

    for entry in learned:
        problem = entry.get("problem_text", "").strip()
        resp    = entry.get("response_text", "")
        if not problem or not resp:
            continue

        score, method = 0.0, "none"

        # ── Couche 1 : correspondance exacte ─────────────────
        if query_text.strip() == problem:
            score, method = 1.0, "exact"

        # ── Couche 2 : sous-chaîne ────────────────────────────
        elif problem in query_text or query_text in problem:
            score, method = 0.92, "substring"

        else:
            # ── Couche 3 : recoupement de mots-clés ──────────
            q_words = set(w for w in query_text.split() if len(w) > 2)
            p_words = set(w for w in problem.split()       if len(w) > 2)
            common  = q_words & p_words
            if len(common) >= 2 and max(len(q_words), len(p_words), 1):
                kw_score = len(common) / max(len(q_words), len(p_words))
                kw_final = min(0.90, kw_score * 1.1)   # légère amplification
                if kw_final > score:
                    score, method = kw_final, f"keywords({len(common)})"

            # ── Couche 4 : similarité cosinus (embedding) ────
            if q_emb is not None:
                emb = entry.get("embedding")
                if emb is not None:
                    try:
                        norm = (float(np.linalg.norm(q_emb)) *
                                float(np.linalg.norm(emb))) + 1e-9
                        cos  = float(np.dot(q_emb, emb)) / norm
                        if cos > score:
                            score, method = cos, f"cosine({cos:.3f})"
                    except Exception:
                        pass

        logger.info(
            f"[Global Learning]   score={score:.3f} ({method}) "
            f"'{query_text[:30]}' vs '{problem[:30]}'"
        )

        if score > best_score:
            best_score, best_resp   = score, resp
            best_problem, best_method = problem, method

    THRESHOLD = 0.62
    if best_score >= THRESHOLD and best_resp:
        logger.info(
            f"[Global Learning] ✅ MATCH ! score={best_score:.3f} "
            f"method={best_method} problem='{best_problem[:50]}'"
        )
        return best_resp

    logger.info(
        f"[Global Learning] ❌ Aucune correspondance "
        f"(meilleur={best_score:.3f} < {THRESHOLD})"
    )
    return None

# ════════════════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/new_session", methods=["POST"])
def new_session():
    sid  = "TT_" + uuid.uuid4().hex[:10].upper()
    sess = get_session(sid)
    # Ne pas envoyer le greeting automatiquement — le user doit saluer en premier
    return jsonify({
        "session_id":    sid,
        "needs_greeting": True,   # indique au frontend d'afficher un hint
        "ml_active":     ml_predictor.is_available,
        "ml_backend":    ml_predictor.backend_name,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    data      = request.get_json()
    user_text = (data.get("message") or "").strip()
    sid       = data.get("session_id") or "default"

    if not user_text:
        return jsonify({"error": "Message vide"}), 400

    sess = get_session(sid)

    # ── ÉTAPE 0 : Attente de salutation ──────────────────────
    stage = sess.get("stage", "waiting_greeting")

    if stage == "waiting_greeting":
        sess["history"].append(("user", user_text))
        if _is_greeting(user_text):
            greeting = Config.GREETING_MESSAGE
            sess["history"].append(("bot", greeting))
            sess["stage"] = "initial"
            logger.info(f"[{sid}] Salutation reçue → greeting envoyé")
            return jsonify({
                "bot_response":  greeting,
                "is_greeting":   True,
                "session_ended": False,
                "analysis":      {},
            })
        else:
            # User n'a pas salué → lui demander poliment de saluer
            hint = "مرحبا! قبل ما نبداو، قولي عسلامة"
            sess["history"].append(("bot", hint))
            return jsonify({
                "bot_response":  hint,
                "is_greeting":   False,
                "session_ended": False,
                "analysis":      {},
            })

    # ── Remerciement après solution ───────────────────────────
    if _is_thanks(user_text) and sess.get("solution_given"):
        sess["history"].append(("user", user_text))
        thanks_resp = Config.THANKS_MESSAGE
        sess["history"].append(("bot", thanks_resp))
        sess["stage"]          = "waiting_greeting"
        sess["solution_given"] = False
        logger.info(f"[{sid}] Remerciement reçu → message de clôture envoyé")
        return jsonify({
            "bot_response":  thanks_resp,
            "session_ended": True,
            "analysis":      {},
        })

    # ── Mot de clôture ────────────────────────────────────────
    if _is_stop(user_text):
        sess["history"].append(("user", user_text))
        sess["history"].append(("bot", Config.FAREWELL_MESSAGE))
        return jsonify({
            "bot_response":  Config.FAREWELL_MESSAGE,
            "session_ended": True,
            "analysis":      {},
        })

    sess["turn"] += 1
    sess["history"].append(("user", user_text))

    # ── NLU ───────────────────────────────────────────────────
    nlu_result   = nlu.analyze(user_text)
    intent       = nlu_result.get("intent", "")
    ml_conf      = nlu_result.get("confidence", 0)
    service_type = nlu_result.get("entities", {}).get("service_type", "")

    # Mettre à jour les entités collectées (+ fallback regex depuis le texte)
    _update_entities(sess, nlu_result, user_text)

    # ══════════════════════════════════════════════════════════
    #  DIALOGUE EN 2 ÉTAPES (fidèle au dataset)
    # ══════════════════════════════════════════════════════════

    # ── ÉTAPE 1 : Première plainte → poser une QUESTION ──────
    if stage == "initial":
        # Chercher la question dans le dataset via similarité sémantique pure
        clari = response_eng.find_clarification_question(
            user_text, nlu_intent=intent, nlu_service=service_type
        )

        # Double filtre avant de poser une question de clarification :
        #  1. La confiance sémantique de la question doit être ≥ 0.50
        #     (seuil élevé pour éviter les fausses questions hors-sujet)
        #  2. La confiance NLU (ML) doit être ≥ 0.35
        #     (si le NLU est incertain, le sujet n'est probablement pas dans le dataset)
        # Si l'un des deux seuils n'est pas atteint → on passe directement à l'étape 2
        # qui tentera une réponse directe ou déclenchera le transfert humain.
        CLARI_MIN_CONF     = Config.CLARIFICATION_CONFIDENCE_THRESHOLD   # 0.50
        NLU_MIN_CONF_CLARI = Config.NLU_MIN_CONFIDENCE_FOR_CLARI         # 0.35

        clari_ok = (
            clari["question"]
            and clari["confidence"] >= CLARI_MIN_CONF
            and ml_conf >= NLU_MIN_CONF_CLARI
        )

        if clari_ok:
            bot_resp = response_eng._strip_emojis(clari["question"])
            _ents_clari = sess.get("collected_entities", {})

            # Combiner clarification + question de localisation dans un seul message
            if _needs_location_intent(intent):
                if _needs_delegation(_ents_clari):
                    # Wilaya connue, délégation manquante
                    bot_resp += "  " + _build_delegation_question(_ents_clari)
                    sess["location_in_clari"] = "delegation"
                elif _needs_location(_ents_clari, intent):
                    # Ni wilaya ni délégation
                    bot_resp += "  " + Config.LOCATION_QUESTION
                    sess["location_in_clari"] = "full"
            elif _needs_delegation(_ents_clari):
                # Intent non listé dans LOCATION_DEPENDENT_INTENTS mais wilaya mentionnée
                # → compléter avec la délégation (essentiel pour analyse NLU et réponses RAG)
                bot_resp += "  " + _build_delegation_question(_ents_clari)
                sess["location_in_clari"] = "delegation"

            sess["stage"] = "clarifying"

            record_intent = clari.get("intent") or intent
            sess["pending_intent"]   = record_intent
            sess["original_problem"] = user_text

            sess["history"].append(("bot", bot_resp))

            logger.info(
                f"[{sid}] ÉTAPE 1 → NLU='{intent}' RECORD='{record_intent}' "
                f"question='{bot_resp[:60]}' conf={clari['confidence']:.3f}"
            )

            return jsonify({
                "bot_response":  bot_resp,
                "clarifying":    True,
                "transferred":   False,
                "session_ended": False,
                "analysis":      _build_analysis(nlu_result, {}, clarifying=True,
                                                 collected_entities=sess.get("collected_entities")),
            })

        # ── Problème non reconnu → transfert immédiat ───────────
        # Si le NLU ne reconnaît pas l'intent ET que la similarité sémantique
        # est trop faible → le problème est hors dataset → transfert humain direct.
        intent_unknown = intent in ("غير محدد", "unknown", "")
        rag_gate_failed = not clari["question"]   # gate RAW < 0.50 dans find_clarification_question

        if intent_unknown and rag_gate_failed:
            logger.info(
                f"[{sid}] Problème NON RECONNU "
                f"(intent='{intent}' | clari_conf={clari['confidence']:.3f}) "
                f"→ transfert humain immédiat"
            )
            sess["transferred"] = True
            sess["last_transferred_problem"] = user_text   # pour apprentissage session
            bot_resp = Config.TRANSFER_MESSAGE
            ticket = transfer.create_ticket(
                session_id=sid, history=sess["history"],
                user_last_text=user_text, nlu_result=nlu_result,
                rag_confidence=clari["confidence"],
            )
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            return jsonify({
                "bot_response": bot_resp,
                "transferred":  True,
                "ticket_id":    ticket.get("ticket_id"),
                "analysis":     _build_analysis(nlu_result, {},
                                                unknown_problem=True),
            })

        # ── NOUVEAU : clari confidence < seuil → problème HORS DATASET ─────────
        # Même si le NLU a détecté un intent avec confiance correcte, si le RAG
        # ne trouve pas de question de clarification pertinente (conf < 0.50),
        # c'est que le problème N'EXISTE PAS dans le dataset.
        # → Transférer immédiatement au lieu de donner une réponse erronée.
        if clari["confidence"] < CLARI_MIN_CONF:
            logger.info(
                f"[{sid}] Problème HORS DATASET "
                f"(clari_conf={clari['confidence']:.3f} < seuil={CLARI_MIN_CONF} | "
                f"intent='{intent}' nlu_conf={ml_conf:.2f}) "
                f"→ transfert humain immédiat"
            )
            sess["transferred"] = True
            sess["last_transferred_problem"] = user_text   # pour apprentissage session
            bot_resp = Config.TRANSFER_MESSAGE
            ticket = transfer.create_ticket(
                session_id=sid, history=sess["history"],
                user_last_text=user_text, nlu_result=nlu_result,
                rag_confidence=clari["confidence"],
            )
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            return jsonify({
                "bot_response": bot_resp,
                "transferred":  True,
                "ticket_id":    ticket.get("ticket_id"),
                "analysis":     _build_analysis(nlu_result, {},
                                                unknown_problem=True),
            })

        # Seuil NLU bas → passer direct à l'étape 2 avec seuil strict
        logger.info(
            f"[{sid}] ÉTAPE 1 ignorée (NLU bas) "
            f"(clari_conf={clari['confidence']:.3f} | nlu_conf={ml_conf:.2f}) "
            f"→ passage direct ÉTAPE 2"
        )
        sess["stage"]            = "responding"
        sess["pending_intent"]   = intent
        sess["original_problem"] = user_text
        # Vérifier la localisation avant d'aller au RAG
        if _needs_location(sess.get("collected_entities"), intent):
            bot_resp = Config.LOCATION_QUESTION
            sess["stage"] = "waiting_for_location"
            sess["history"].append(("bot", bot_resp))
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False, "analysis": {}})
        elif _needs_delegation(sess.get("collected_entities")):
            # Tous intents — wilaya connue mais délégation manquante
            bot_resp = _build_delegation_question(sess.get("collected_entities"))
            sess["stage"] = "waiting_for_delegation"
            sess["history"].append(("bot", bot_resp))
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False, "analysis": {}})

    # ── ÉTAPE 2 : Réponse finale (après clarification) ───────
    active_intent = sess.get("pending_intent") or intent

    # ── Numéro de rappel reçu → clore la conversation ────────
    if stage == "waiting_for_callback_number":
        bot_resp = Config.THANKS_MESSAGE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "waiting_greeting"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return jsonify({"bot_response": bot_resp, "transferred": False,
                        "session_ended": True, "analysis": {}})

    # ── Localisation attendue ─────────────────────────────────
    if stage == "waiting_for_location":
        _ents_loc = sess.get("collected_entities", {})
        if not _ents_loc.get("wilaya") and not _ents_loc.get("delegation"):
            bot_resp = Config.LOCATION_QUESTION
            sess["history"].append(("bot", bot_resp))
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False, "analysis": {}})
        elif _ents_loc.get("wilaya") and not _ents_loc.get("delegation"):
            bot_resp = _build_delegation_question(_ents_loc)
            sess["stage"] = "waiting_for_delegation"
            sess["history"].append(("bot", bot_resp))
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False, "analysis": {}})
        else:
            sess["stage"] = "responding"
            stage         = "responding"

    # ── Délégation attendue ───────────────────────────────────
    if stage == "waiting_for_delegation":
        _ents_deleg = sess.get("collected_entities", {})
        if not _ents_deleg.get("delegation"):
            bot_resp = _build_delegation_question(_ents_deleg)
            sess["history"].append(("bot", bot_resp))
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False, "analysis": {}})
        else:
            sess["stage"] = "responding"
            stage         = "responding"

    # ── Numéro de demande reçu → réponse apprise OU transfert ───────────────────
    if stage == "waiting_for_request_number":
        _orig_prob_nr = (sess.get("original_problem") or
                         sess.get("last_transferred_problem") or "").strip()
        _learned_nr   = _find_session_learned_response(sess, _orig_prob_nr) if _orig_prob_nr else None
        if _learned_nr:
            bot_resp = _localize_response(_learned_nr, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] Réponse apprise (waiting_for_request_number) — transfert évité")
            return jsonify({
                "bot_response": bot_resp, "transferred": False, "session_ended": False,
                "analysis": _build_analysis(nlu_result, {},
                                            collected_entities=sess.get("collected_entities")),
            })
        sess["transferred"] = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        ticket = transfer.create_ticket(
            session_id=sid, history=sess["history"],
            user_last_text=user_text, nlu_result=nlu_result,
            rag_confidence=0.0,
        )
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["solution_given"] = True
        logger.info(f"[{sid}] Numéro de demande reçu → transfert humain")
        _transfer_rag = {"confidence": 0.0, "escalate": True,
                         "issue_type": sess.get("pending_intent", ""),
                         "service_type": "", "action": "تحويل لوكيل بشري"}
        return jsonify({
            "bot_response": bot_resp, "transferred": True,
            "ticket_id":    ticket.get("ticket_id"),
            "analysis":     _build_analysis(nlu_result, _transfer_rag,
                                            collected_entities=sess.get("collected_entities"),
                                            transferred=True),
        })

    # ── Détection de négation : user répond "non" à la question de clarification ──
    # Ex : Bot demande "عندك رقم المعاملة؟" → User répond "لا معنديش"
    # Dans ce cas le dataset n'a pas de réponse → on guide vers l'agence
    if stage == "clarifying" and _is_negation(user_text):
        bot_resp = Config.NEGATION_CLARIFICATION_RESPONSE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True   # active le remerciement au prochain tour
        logger.info(f"[{sid}] Négation détectée → réponse alternative agence")
        # Construire un rag_result factice pour l'analyse (حل تلقائي car on a une réponse)
        _neg_rag = {"confidence": 1.0, "escalate": False,
                    "issue_type": "", "service_type": "", "action": ""}
        return jsonify({
            "bot_response":  bot_resp,
            "clarifying":    False,
            "transferred":   False,
            "session_ended": False,
            "analysis":      _build_analysis(nlu_result, _neg_rag,
                                             collected_entities=sess.get("collected_entities")),
            "turn":          sess["turn"],
        })

    # ── Check localisation avant RAG ─────────────────────────────────────────
    _ents_step2   = sess.get("collected_entities", {})
    _intent_step2 = active_intent or intent
    _loc_in_clari = sess.pop("location_in_clari", None)
    _asked_full_loc  = (_loc_in_clari == "full")
    _asked_deleg_loc = (_loc_in_clari == "delegation")

    if _loc_in_clari:
        _update_entities(sess, {}, user_text)
        _ents_step2 = sess.get("collected_entities", {})

    if _needs_location(_ents_step2, _intent_step2) and not _asked_full_loc:
        bot_resp = Config.LOCATION_QUESTION
        sess["stage"] = "waiting_for_location"
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        if not sess.get("pending_intent"):
            sess["pending_intent"] = _intent_step2
        sess["history"].append(("bot", bot_resp))
        return jsonify({"bot_response": bot_resp, "transferred": False,
                        "session_ended": False, "analysis": {}})
    elif _needs_delegation(_ents_step2):
        # Tous intents — wilaya connue mais délégation manquante.
        # Note : on ne bloque plus sur _asked_deleg_loc car si l'user a répondu à la
        # question combinée sans donner la délégation, on doit la redemander en standalone.
        bot_resp = _build_delegation_question(_ents_step2)
        sess["stage"] = "waiting_for_delegation"
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        if not sess.get("pending_intent"):
            sess["pending_intent"] = _intent_step2
        sess["history"].append(("bot", bot_resp))
        return jsonify({"bot_response": bot_resp, "transferred": False,
                        "session_ended": False, "analysis": {}})

    # ── Apprentissage éphémère : check avant RAG ──────────────────────────────
    # Si une réponse apprise existe → l'utiliser directement pour TOUS les intents
    # (y compris مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب)
    # Le bot a déjà appris comment répondre → plus besoin de demander le numéro
    _force_num_step2 = _is_ask_number_intent(
        (sess.get("pending_intent") or active_intent or "").strip()
    )
    _orig_prob_step2 = (sess.get("original_problem") or
                        sess.get("last_transferred_problem") or user_text).strip()
    _learned_step2 = _find_session_learned_response(sess, _orig_prob_step2)
    if _learned_step2:
        bot_resp = _localize_response(_learned_step2, sess.get("collected_entities"))
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        logger.info(f"[{sid}] Réponse apprise (step2) — transfert évité")
        return jsonify({"bot_response": bot_resp, "transferred": False,
                        "session_ended": False,
                        "analysis": _build_analysis(nlu_result, {},
                                                    collected_entities=sess.get("collected_entities"))})

    # Construire la requête : problème original + réponse clarification
    enriched_query = _build_enriched_query(sess, user_text)

    # Chercher la réponse dans le RAG avec filtrage strict par intent
    rag_result = response_eng.find_response(
        enriched_query,
        sess["history"],
        nlu_intent=active_intent
    )

    # ── Décision : répondre ou transférer ─────────────────────
    rag_conf     = rag_result.get("confidence", 0)
    rag_escalate = rag_result.get("escalate", False)

    # Seuil STRICT dans deux cas :
    #  1. sess["stage"] == "responding" : étape 1 court-circuitée (hors-dataset)
    #     → seuil = RAG_STRICT_THRESHOLD (0.45)
    #  2. sess["stage"] == "clarifying" : user a répondu à la question de clarification
    #     mais le RAG ne trouve toujours pas de solution fiable
    #     → seuil = RAG_STRICT_THRESHOLD_AFTER_CLARI (0.60) — plus strict car l'user
    #       a déjà fourni toutes les infos : si conf < 0.60 → le problème n'est pas
    #       dans le dataset → transfert humain immédiat (évite la boucle infinie)
    current_stage = sess.get("stage")
    if current_stage == "responding":
        # Si le NLU était peu confiant (< seuil clarification) → problème potentiellement
        # hors dataset → exiger une confiance RAG plus élevée avant de répondre.
        # Ex : NLU=23%, RAG=51% → réponse fausse → transférer.
        NLU_MIN_CONF_CLARI = Config.NLU_MIN_CONFIDENCE_FOR_CLARI   # 0.35
        if ml_conf < NLU_MIN_CONF_CLARI:
            strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_LOW_NLU", 0.70)
        else:
            strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD", 0.45)
        if rag_conf < strict_threshold:
            rag_escalate = True
            logger.info(
                f"[{sid}] Seuil strict (hors-dataset) : "
                f"rag_conf={rag_conf:.3f} < {strict_threshold} "
                f"(ml_conf={ml_conf:.2f}) → escalade forcée"
            )
    elif current_stage == "clarifying":
        strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_AFTER_CLARI", 0.60)
        if rag_conf < strict_threshold:
            rag_escalate = True
            logger.info(
                f"[{sid}] Seuil strict (après-clarification) : "
                f"rag_conf={rag_conf:.3f} < {strict_threshold} → escalade forcée"
            )

    # Certains intents ne déclenchent jamais de transfert
    if rag_escalate:
        _chk_no_tr = (sess.get("pending_intent") or active_intent or "").strip()
        if _is_no_transfer_intent(_chk_no_tr):
            rag_escalate = False

    if rag_escalate:
        _chk_esc_intent = (sess.get("pending_intent") or active_intent or "").strip()
        _force_num_esc  = _is_ask_number_intent(_chk_esc_intent)

        # Réponse apprise ? → répondre directement (pour TOUS les intents, y compris
        # مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب)
        # Le bot a déjà appris la réponse → court-circuite le transfert ET la demande de numéro
        _orig_prob_p4 = (sess.get("original_problem") or
                         sess.get("last_transferred_problem") or user_text).strip()
        _learned_p4 = _find_session_learned_response(sess, _orig_prob_p4)
        if _learned_p4:
            bot_resp = _localize_response(_learned_p4, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] Réponse apprise (rag_escalate) — transfert évité")
            return jsonify({
                "bot_response": bot_resp, "transferred": False, "session_ended": False,
                "analysis": _build_analysis(nlu_result, {},
                                            collected_entities=sess.get("collected_entities")),
            })

        # 4 intents à numéro obligatoire → demander le numéro au lieu de transférer
        if _force_num_esc:
            _ask_num = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                               "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
            sess["stage"] = "waiting_for_request_number"
            if not sess.get("pending_intent"):
                sess["pending_intent"] = active_intent
            if not sess.get("original_problem"):
                sess["original_problem"] = user_text
            sess["history"].append(("bot", _ask_num))
            logger.info(f"[{sid}] {_chk_esc_intent} — demande numéro (rag_escalate)")
            return jsonify({"bot_response": _ask_num, "transferred": False,
                            "session_ended": False, "analysis": {}})

        sess["transferred"] = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        ticket   = transfer.create_ticket(
            session_id=sid, history=sess["history"],
            user_last_text=user_text, nlu_result=nlu_result,
            rag_confidence=rag_conf,
        )
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        logger.info(
            f"[{sid}] Transfert humain → intent='{active_intent}' "
            f"rag_conf={rag_conf:.3f}"
        )
        _low_nlu = (current_stage == "responding"
                    and ml_conf < Config.NLU_MIN_CONFIDENCE_FOR_CLARI)
        return jsonify({
            "bot_response": bot_resp, "transferred": True,
            "ticket_id":    ticket.get("ticket_id"),
            "analysis":     _build_analysis(nlu_result, rag_result,
                                            collected_entities=sess.get("collected_entities"),
                                            transferred=True, unknown_problem=_low_nlu),
        })

    # ── Choisir la réponse ────────────────────────────────────
    bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or ""
    if not bot_resp:
        bot_resp = Config.NOT_UNDERSTOOD_MSG

    # ── Intercept localisation : AVANT de retourner la réponse RAG ──────────────
    # Déclencheurs (OR) :
    #   A. Intent dans LOCATION_DEPENDENT_INTENTS → localisation toujours nécessaire
    #   B. Réponse RAG contient une wilaya hardcodée
    # "في تونس" géré séparément dans _localize_response.
    _ents_rag_chk   = sess.get("collected_entities", {})
    _chk_rag_intent = (sess.get("pending_intent") or active_intent or "").strip()
    _rag_needs_loc  = (
        _needs_location_intent(_chk_rag_intent)
        or _response_has_wilaya(bot_resp)
    )
    if _rag_needs_loc and _needs_location(_ents_rag_chk, _chk_rag_intent) and not _asked_full_loc:
        loc_q = Config.LOCATION_QUESTION
        sess["stage"] = "waiting_for_location"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        sess["history"].append(("bot", loc_q))
        logger.info(f"[{sid}] Localisation manquante (intent={_chk_rag_intent}) → demande wilaya+délégation")
        return jsonify({"bot_response": loc_q, "transferred": False,
                        "session_ended": False, "analysis": {}})
    elif _needs_delegation(_ents_rag_chk):
        # Tous intents — wilaya connue mais délégation manquante.
        # Garde _asked_deleg_loc supprimé : on redemande si l'user n'a pas répondu à clari.
        deleg_q = _build_delegation_question(_ents_rag_chk)
        sess["stage"] = "waiting_for_delegation"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        sess["history"].append(("bot", deleg_q))
        logger.info(f"[{sid}] Délégation manquante (wilaya={_ents_rag_chk.get('wilaya')}) → demande")
        return jsonify({"bot_response": deleg_q, "transferred": False,
                        "session_ended": False, "analysis": {}})

    bot_resp = response_eng._strip_emojis(
        _localize_response(bot_resp, sess.get("collected_entities"))
    )

    # ── Détection de boucle ───────────────────────────────────
    last_bot_resp = next(
        (t for role, t in reversed(sess.get("history", [])) if role == "bot"), ""
    )
    _chk_loop = (sess.get("pending_intent") or active_intent or "").strip()
    if last_bot_resp and bot_resp.strip() == last_bot_resp.strip() and not _is_no_transfer_intent(_chk_loop):
        _orig_prob_p5 = (sess.get("original_problem") or
                         sess.get("last_transferred_problem") or user_text).strip()
        _learned_p5 = _find_session_learned_response(sess, _orig_prob_p5)
        if _learned_p5:
            bot_resp = _localize_response(_learned_p5, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] Réponse apprise (loop detection) — transfert évité")
            return jsonify({"bot_response": bot_resp, "transferred": False,
                            "session_ended": False,
                            "analysis": _build_analysis(nlu_result, {},
                                                        collected_entities=sess.get("collected_entities"))})
        sess["transferred"] = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        ticket = transfer.create_ticket(
            session_id=sid, history=sess["history"],
            user_last_text=user_text, nlu_result=nlu_result,
            rag_confidence=rag_conf,
        )
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        logger.info(f"[{sid}] BOUCLE DÉTECTÉE → transfert")
        return jsonify({
            "bot_response": bot_resp, "transferred": True,
            "ticket_id":    ticket.get("ticket_id"),
            "analysis":     _build_analysis(nlu_result, rag_result,
                                            collected_entities=sess.get("collected_entities"),
                                            transferred=True),
        })

    sess["history"].append(("bot", bot_resp))

    # ── 4 intents à numéro obligatoire : forcer la demande si RAG ne l'a pas fait ──
    _force_num_rag = _is_ask_number_intent(
        (sess.get("pending_intent") or active_intent or "").strip()
    )
    if _force_num_rag and not _ASK_NUMBER_RE.search(bot_resp):
        _ask_num_rag = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                               "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
        if sess["history"] and sess["history"][-1][0] == "bot":
            sess["history"][-1] = ("bot", _ask_num_rag)
        sess["stage"] = "waiting_for_request_number"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        logger.info(f"[{sid}] Demande numéro forcée (RAG intercepté)")
        return jsonify({"bot_response": _ask_num_rag, "transferred": False,
                        "session_ended": False, "analysis": {}})

    if _ASK_NUMBER_RE.search(bot_resp):
        sess["stage"] = "waiting_for_request_number"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        logger.info(f"[{sid}] Bot a demandé le numéro → waiting_for_request_number")
    elif _CALLBACK_NUMBER_RE.search(bot_resp):
        sess["stage"] = "waiting_for_callback_number"
    else:
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True

    logger.info(
        f"[{sid}] ÉTAPE 2 → intent='{active_intent}' "
        f"rag_conf={rag_conf:.3f} response='{bot_resp[:50]}'"
    )

    return jsonify({
        "bot_response":  bot_resp,
        "clarifying":    False,
        "transferred":   False,
        "session_ended": False,
        "analysis":      _build_analysis(nlu_result, rag_result,
                                         collected_entities=sess.get("collected_entities")),
        "turn":          sess["turn"],
    })


# ════════════════════════════════════════════════════════════
#  ElevenLabs TTS
# ════════════════════════════════════════════════════════════

@app.route("/api/tts", methods=["POST"])
def tts_elevenlabs():
    """
    Génère l'audio du bot.
    Priorité :
      0. Coqui TTS  (open-source, arabe/fine-tuning tunisien) → si installé
      1. edge-tts   (voix neurale Microsoft ar-TN-ReemNeural)  → gratuit, hors-ligne
      2. ElevenLabs (voix masculine, haute qualité)            → si clé configurée
      3. gTTS       (voix arabe basique, fallback final)
    """
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Texte vide"}), 400

    api_key  = Config.ELEVENLABS_API_KEY
    voice_id = Config.ELEVENLABS_VOICE_ID

    # ── 0. Coqui TTS — open-source, arabe + fine-tuning tunisien ──
    # pip install TTS  (une seule fois dans le terminal)
    # Le modèle est téléchargé automatiquement au premier appel (~50 Mo)
    try:
        coqui = _get_coqui_tts()
        if coqui is not None:
            import tempfile, os as _os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            speaker  = getattr(Config, "COQUI_TTS_SPEAKER",  None)
            language = getattr(Config, "COQUI_TTS_LANGUAGE", None)
            kwargs = {}
            if speaker:
                kwargs["speaker"] = speaker
            if language:
                kwargs["language"] = language
            coqui.tts_to_file(text=text, file_path=wav_path, **kwargs)
            with open(wav_path, "rb") as f:
                wav_bytes = f.read()
            _os.unlink(wav_path)
            if wav_bytes:
                model_used = getattr(Config, "COQUI_TTS_CUSTOM_MODEL", "") or \
                             getattr(Config, "COQUI_TTS_MODEL", "coqui-ar")
                logger.info(f"TTS via Coqui TTS ({model_used})")
                return send_file(io.BytesIO(wav_bytes), mimetype="audio/wav",
                                 as_attachment=False, download_name="response.wav")
    except Exception as e:
        logger.warning(f"Coqui TTS synthesis error: {e} → fallback edge-tts")

    # ── 1. edge-tts — voix neurale Microsoft (ar-TN-ReemNeural) ──
    # Gratuit, aucune clé requise, voix tunisienne très naturelle.
    try:
        import edge_tts
        import asyncio

        edge_voice = getattr(Config, "EDGE_TTS_VOICE", "ar-TN-ReemNeural")

        async def _synthesize():
            communicate = edge_tts.Communicate(text, edge_voice)
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        # Compatibilité Windows / environnements sans event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("loop closed")
            mp3_bytes = loop.run_until_complete(_synthesize())
        except (RuntimeError, Exception):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            mp3_bytes = loop.run_until_complete(_synthesize())
            loop.close()

        if mp3_bytes:
            mp3_fp = io.BytesIO(mp3_bytes)
            mp3_fp.seek(0)
            logger.info(f"TTS via edge-tts ({edge_voice})")
            return send_file(mp3_fp, mimetype="audio/mpeg",
                             as_attachment=False, download_name="response.mp3")
    except ImportError:
        logger.debug("edge-tts non installé → ElevenLabs / gTTS")
    except Exception as e:
        logger.warning(f"edge-tts error: {e} → fallback ElevenLabs/gTTS")

    # ── 2. ElevenLabs (si clé configurée) ─────────────────────
    if api_key and api_key != "YOUR_API_KEY_HERE":
        try:
            import requests as req_lib
            url     = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "Accept":       "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key":   api_key,
            }
            payload = {
                "text":           text,
                "model_id":       Config.ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability":         Config.ELEVENLABS_STABILITY,
                    "similarity_boost":  Config.ELEVENLABS_SIMILARITY,
                    "style":             Config.ELEVENLABS_STYLE,
                    "use_speaker_boost": Config.ELEVENLABS_SPEAKER_BOOST,
                }
            }
            resp = req_lib.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                return send_file(
                    io.BytesIO(resp.content), mimetype="audio/mpeg",
                    as_attachment=False, download_name="response.mp3"
                )
            logger.warning(f"ElevenLabs {resp.status_code} → fallback gTTS")
        except Exception as e:
            logger.warning(f"ElevenLabs error: {e} → fallback gTTS")

    # ── 3. gTTS — fallback final (voix arabe basique) ─────────
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="ar", slow=False)
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        logger.info("TTS via gTTS (fallback)")
        return send_file(mp3_fp, mimetype="audio/mpeg",
                         as_attachment=False, download_name="response.mp3")
    except ImportError:
        return jsonify({"error": "gtts non installé — pip install gtts"}), 503
    except Exception as e:
        logger.error(f"Erreur gTTS: {e}")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  Voice (Whisper STT)
# ════════════════════════════════════════════════════════════

@app.route("/api/voice", methods=["POST"])
def voice():
    if not stt_model:
        return jsonify({"error": "Whisper non disponible"}), 503

    sid        = request.form.get("session_id", "default")
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "Pas de fichier audio"}), 400

    try:
        suffix = ".webm" if "webm" in (audio_file.content_type or "") else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        segments, _ = stt_model.transcribe(
            tmp_path,
            language=Config.STT_LANGUAGE,
            beam_size=Config.STT_BEAM_SIZE,
            vad_filter=Config.STT_VAD_FILTER,
            initial_prompt=Config.STT_INITIAL_PROMPT,
            temperature=Config.STT_TEMPERATURE,
            condition_on_previous_text=False,
            no_speech_threshold=Config.STT_NO_SPEECH_THRESHOLD,
            compression_ratio_threshold=2.4,
        )
        transcript = " ".join(s.text.strip() for s in segments).strip()
        os.unlink(tmp_path)

        if not transcript:
            return jsonify({"transcript": "", "bot_response": Config.NOT_UNDERSTOOD_MSG, "analysis": {}})

        # Utiliser le même flux que /api/chat
        sess  = get_session(sid)
        stage = sess.get("stage", "waiting_greeting")

        # Étape 0 : salutation vocale
        if stage == "waiting_greeting":
            sess["history"].append(("user", transcript))
            if _is_greeting(transcript):
                greeting = Config.GREETING_MESSAGE
                sess["history"].append(("bot", greeting))
                sess["stage"] = "initial"
                return jsonify({"transcript": transcript, "bot_response": greeting, "analysis": {}})
            else:
                hint = "مرحبا! قبل ما نبداو، قولي عسلامة"
                sess["history"].append(("bot", hint))
                return jsonify({"transcript": transcript, "bot_response": hint, "analysis": {}})

        # Remerciement vocal après solution
        if _is_thanks(transcript) and sess.get("solution_given"):
            sess["history"].append(("user", transcript))
            thanks_resp = Config.THANKS_MESSAGE
            sess["history"].append(("bot", thanks_resp))
            sess["stage"]          = "waiting_greeting"
            sess["solution_given"] = False
            return jsonify({"transcript": transcript, "bot_response": thanks_resp, "session_ended": True, "analysis": {}})

        nlu_result   = nlu.analyze(transcript)
        intent       = nlu_result.get("intent", "")
        service_type = nlu_result.get("entities", {}).get("service_type", "")
        _update_entities(sess, nlu_result, transcript)

        sess["turn"] += 1
        sess["history"].append(("user", transcript))

        # Étape 1 : question — double filtre (confiance sémantique + confiance NLU)
        CLARI_MIN_CONF     = Config.CLARIFICATION_CONFIDENCE_THRESHOLD   # 0.50
        NLU_MIN_CONF_CLARI = Config.NLU_MIN_CONFIDENCE_FOR_CLARI         # 0.35
        voice_ml_conf      = nlu_result.get("confidence", 0)

        if stage == "initial":
            # ── Apprentissage éphémère vocal : réponse déjà apprise dans cette session ──
            _force_num_init_v = _is_ask_number_intent(intent.strip())
            _session_resp_v = _find_session_learned_response(sess, transcript)
            if _session_resp_v and not _force_num_init_v:
                bot_resp_v = _localize_response(_session_resp_v, sess.get("collected_entities"))
                sess["history"].append(("bot", bot_resp_v))
                sess["solution_given"] = True
                logger.info(f"[{sid}] (vocal) Réponse éphémère (apprentissage session) utilisée")
                return jsonify({
                    "transcript":       transcript,
                    "bot_response":     bot_resp_v,
                    "transferred":      False,
                    "session_ended":    False,
                    "learned_response": True,
                    "analysis":         _build_analysis(
                        nlu_result,
                        {"confidence": 1.0, "escalate": False,
                         "issue_type": intent, "service_type": service_type,
                         "action": "تعلم من وكيل بشري"},
                        collected_entities=sess.get("collected_entities"),
                    ),
                })

            clari = response_eng.find_clarification_question(
                transcript, nlu_intent=intent, nlu_service=service_type
            )

            # ── Problème non reconnu (vocal) → transfert immédiat ──
            voice_intent_unknown = intent in ("غير محدد", "unknown", "")
            voice_rag_gate_failed = not clari["question"]

            if voice_intent_unknown and voice_rag_gate_failed:
                logger.info(
                    f"[{sid}] (vocal) Problème NON RECONNU "
                    f"(intent='{intent}' | clari_conf={clari['confidence']:.3f}) "
                    f"→ transfert humain immédiat"
                )
                sess["transferred"] = True
                sess["last_transferred_problem"] = transcript   # apprentissage session
                bot_resp_v = Config.TRANSFER_MESSAGE
                ticket = transfer.create_ticket(
                    session_id=sid, history=sess["history"],
                    user_last_text=transcript, nlu_result=nlu_result,
                    rag_confidence=clari["confidence"],
                )
                sess["history"].append(("bot", bot_resp_v))
                sess["stage"]          = "initial"
                sess["pending_intent"] = ""
                sess["solution_given"] = True
                return jsonify({
                    "transcript":   transcript,
                    "bot_response": bot_resp_v,
                    "transferred":  True,
                    "ticket_id":    ticket.get("ticket_id"),
                    "analysis":     _build_analysis(nlu_result, {},
                                                    unknown_problem=True),
                })

            # ── NOUVEAU (vocal) : clari confidence < seuil → problème HORS DATASET ──
            # Même si le NLU détecte un intent, si le RAG ne trouve pas de question
            # pertinente (conf < 0.50) → le problème n'est pas dans le dataset
            # → transfert immédiat (évite une réponse erronée du dataset)
            if clari["confidence"] < CLARI_MIN_CONF:
                logger.info(
                    f"[{sid}] (vocal) Problème HORS DATASET "
                    f"(clari_conf={clari['confidence']:.3f} < seuil={CLARI_MIN_CONF} | "
                    f"intent='{intent}' nlu_conf={voice_ml_conf:.2f}) "
                    f"→ transfert humain immédiat"
                )
                sess["transferred"] = True
                sess["last_transferred_problem"] = transcript   # apprentissage session
                bot_resp_v = Config.TRANSFER_MESSAGE
                ticket = transfer.create_ticket(
                    session_id=sid, history=sess["history"],
                    user_last_text=transcript, nlu_result=nlu_result,
                    rag_confidence=clari["confidence"],
                )
                sess["history"].append(("bot", bot_resp_v))
                sess["stage"]          = "initial"
                sess["pending_intent"] = ""
                sess["solution_given"] = True
                return jsonify({
                    "transcript":   transcript,
                    "bot_response": bot_resp_v,
                    "transferred":  True,
                    "ticket_id":    ticket.get("ticket_id"),
                    "analysis":     _build_analysis(nlu_result, {},
                                                    unknown_problem=True),
                })

            clari_ok = (
                clari["question"]
                and clari["confidence"] >= CLARI_MIN_CONF
                and voice_ml_conf >= NLU_MIN_CONF_CLARI
                and not voice_intent_unknown
            )
            if clari_ok:
                bot_resp = response_eng._strip_emojis(clari["question"])
                _ents_clari_v = sess.get("collected_entities", {})

                # Combiner clarification + question de localisation dans un seul message
                if _needs_location_intent(intent):
                    if _needs_delegation(_ents_clari_v):
                        bot_resp += "  " + _build_delegation_question(_ents_clari_v)
                        sess["location_in_clari"] = "delegation"
                    elif _needs_location(_ents_clari_v, intent):
                        bot_resp += "  " + Config.LOCATION_QUESTION
                        sess["location_in_clari"] = "full"
                elif _needs_delegation(_ents_clari_v):
                    # Intent non listé, mais l'user a mentionné une wilaya → demander la délégation
                    bot_resp += "  " + _build_delegation_question(_ents_clari_v)
                    sess["location_in_clari"] = "delegation"

                sess["stage"]            = "clarifying"
                sess["pending_intent"]   = clari.get("intent") or intent
                sess["original_problem"] = transcript
                sess["history"].append(("bot", bot_resp))
                return jsonify({
                    "transcript":   transcript,
                    "bot_response": bot_resp,
                    "analysis":     _build_analysis(nlu_result, {}, clarifying=True,
                                                    collected_entities=sess.get("collected_entities")),
                })
            # Seuil NLU bas mais clari trouvée → passer à l'étape 2 avec seuil strict
            logger.info(
                f"[{sid}] ÉTAPE 1 vocale ignorée (NLU bas) "
                f"(clari_conf={clari['confidence']:.3f} seuil={CLARI_MIN_CONF} | "
                f"nlu_conf={voice_ml_conf:.2f} seuil={NLU_MIN_CONF_CLARI}) "
                f"→ passage direct ÉTAPE 2 (seuil strict RAG appliqué)"
            )

        # Étape 2 : réponse
        active_intent = sess.get("pending_intent") or intent

        # ── Numéro de rappel reçu → clore la conversation (voice) ──────────
        if stage == "waiting_for_callback_number":
            bot_resp = Config.THANKS_MESSAGE
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "waiting_greeting"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            return jsonify({"transcript": transcript, "bot_response": bot_resp,
                            "transferred": False, "session_ended": True, "analysis": {}})

        # ── Localisation attendue (voice) ─────────────────────────────────
        if stage == "waiting_for_location":
            _ents_loc_v = sess.get("collected_entities", {})
            if not _ents_loc_v.get("wilaya") and not _ents_loc_v.get("delegation"):
                bot_resp = Config.LOCATION_QUESTION
                sess["history"].append(("bot", bot_resp))
                return jsonify({"transcript": transcript, "bot_response": bot_resp,
                                "transferred": False, "session_ended": False, "analysis": {}})
            elif _ents_loc_v.get("wilaya") and not _ents_loc_v.get("delegation"):
                bot_resp = _build_delegation_question(_ents_loc_v)
                sess["stage"] = "waiting_for_delegation"
                sess["history"].append(("bot", bot_resp))
                return jsonify({"transcript": transcript, "bot_response": bot_resp,
                                "transferred": False, "session_ended": False, "analysis": {}})
            else:
                sess["stage"] = "responding"
                stage         = "responding"

        # ── Délégation attendue (voice) ───────────────────────────────────
        if stage == "waiting_for_delegation":
            _ents_deleg_v = sess.get("collected_entities", {})
            if not _ents_deleg_v.get("delegation"):
                bot_resp = _build_delegation_question(_ents_deleg_v)
                sess["history"].append(("bot", bot_resp))
                return jsonify({"transcript": transcript, "bot_response": bot_resp,
                                "transferred": False, "session_ended": False, "analysis": {}})
            else:
                sess["stage"] = "responding"
                stage         = "responding"

        # ── Numéro de demande vocal reçu → réponse apprise OU transfert ──
        if stage == "waiting_for_request_number":
            _orig_prob_nr_v = (sess.get("original_problem") or
                               sess.get("last_transferred_problem") or "").strip()
            _learned_nr_v   = _find_session_learned_response(sess, _orig_prob_nr_v) if _orig_prob_nr_v else None
            if _learned_nr_v:
                bot_resp = _localize_response(_learned_nr_v, sess.get("collected_entities"))
                sess["history"].append(("bot", bot_resp))
                sess["stage"]          = "initial"
                sess["pending_intent"] = ""
                sess["solution_given"] = True
                logger.info(f"[{sid}] (vocal) Réponse apprise (waiting_for_request_number) — transfert évité")
                return jsonify({
                    "transcript":    transcript,
                    "bot_response":  bot_resp,
                    "transferred":   False,
                    "session_ended": False,
                    "analysis":      _build_analysis(nlu_result, {},
                                                     collected_entities=sess.get("collected_entities")),
                })
            sess["transferred"] = True
            sess["last_transferred_problem"] = sess.get("original_problem") or transcript
            bot_resp = Config.TRANSFER_MESSAGE
            ticket = transfer.create_ticket(
                session_id=sid, history=sess["history"],
                user_last_text=transcript, nlu_result=nlu_result,
                rag_confidence=0.0,
            )
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] (vocal) Numéro de demande reçu → transfert humain")
            _transfer_rag_v = {"confidence": 0.0, "escalate": True,
                               "issue_type": sess.get("pending_intent", ""),
                               "service_type": "", "action": "تحويل لوكيل بشري"}
            return jsonify({
                "transcript":   transcript,
                "bot_response": bot_resp,
                "transferred":  True,
                "ticket_id":    ticket.get("ticket_id"),
                "analysis":     _build_analysis(nlu_result, _transfer_rag_v,
                                                collected_entities=sess.get("collected_entities"),
                                                transferred=True),
            })

        # Détection de négation vocale : user répond "لا معنديش" à la clarification
        if stage == "clarifying" and _is_negation(transcript):
            bot_resp = Config.NEGATION_CLARIFICATION_RESPONSE
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] Négation vocale détectée → réponse alternative agence")
            _neg_rag = {"confidence": 1.0, "escalate": False,
                        "issue_type": "", "service_type": "", "action": ""}
            return jsonify({
                "transcript":   transcript,
                "bot_response": bot_resp,
                "analysis":     _build_analysis(nlu_result, _neg_rag,
                                                collected_entities=sess.get("collected_entities")),
            })

        # ── Check localisation avant RAG (voice) ──────────────────────────────
        _ents_step2_v    = sess.get("collected_entities", {})
        _intent_step2_v  = active_intent or intent
        _loc_in_clari_v  = sess.pop("location_in_clari", None)
        _asked_full_loc_v  = (_loc_in_clari_v == "full")
        _asked_deleg_loc_v = (_loc_in_clari_v == "delegation")

        if _loc_in_clari_v:
            _update_entities(sess, {}, transcript)
            _ents_step2_v = sess.get("collected_entities", {})

        if _needs_location(_ents_step2_v, _intent_step2_v) and not _asked_full_loc_v:
            bot_resp = Config.LOCATION_QUESTION
            sess["stage"] = "waiting_for_location"
            if not sess.get("original_problem"):
                sess["original_problem"] = transcript
            if not sess.get("pending_intent"):
                sess["pending_intent"] = _intent_step2_v
            sess["history"].append(("bot", bot_resp))
            return jsonify({"transcript": transcript, "bot_response": bot_resp,
                            "transferred": False, "session_ended": False, "analysis": {}})
        elif _needs_delegation(_ents_step2_v):
            # Tous intents — wilaya connue mais délégation manquante.
            # Garde _needs_location_intent et _asked_deleg_loc supprimés pour cohérence
            # avec le chat texte : la délégation est toujours demandée même si l'intent
            # n'est pas dans LOCATION_DEPENDENT_INTENTS, et même si déjà demandée dans clari.
            bot_resp = _build_delegation_question(_ents_step2_v)
            sess["stage"] = "waiting_for_delegation"
            if not sess.get("original_problem"):
                sess["original_problem"] = transcript
            if not sess.get("pending_intent"):
                sess["pending_intent"] = _intent_step2_v
            sess["history"].append(("bot", bot_resp))
            return jsonify({"transcript": transcript, "bot_response": bot_resp,
                            "transferred": False, "session_ended": False, "analysis": {}})

        # ── Apprentissage éphémère : check avant RAG (voice) ─────────────────
        # Si une réponse apprise existe → l'utiliser directement (TOUS les intents)
        # مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب inclus
        _force_num_s2_v  = _is_ask_number_intent(
            (sess.get("pending_intent") or active_intent or "").strip()
        )
        _orig_prob_s2_v  = (sess.get("original_problem") or
                            sess.get("last_transferred_problem") or transcript).strip()
        _learned_s2_v    = _find_session_learned_response(sess, _orig_prob_s2_v)
        if _learned_s2_v:
            bot_resp = _localize_response(_learned_s2_v, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] (vocal) Réponse apprise (step2) — transfert évité")
            return jsonify({"transcript": transcript, "bot_response": bot_resp,
                            "transferred": False, "session_ended": False,
                            "analysis": _build_analysis(nlu_result, {},
                                                        collected_entities=sess.get("collected_entities"))})

        enriched   = _build_enriched_query(sess, transcript)
        rag_result = response_eng.find_response(
            enriched, sess["history"], nlu_intent=active_intent)

        rag_conf     = rag_result.get("confidence", 0)
        rag_escalate = rag_result.get("escalate", False)

        # Seuil strict dans deux cas :
        #  1. stage == "responding" : étape 1 court-circuitée (hors-dataset) → seuil 0.45
        #  2. stage == "clarifying" : user a répondu, RAG ne résout pas → seuil 0.60
        #     Évite la boucle infinie (même question redemandée au tour suivant)
        current_stage_v = sess.get("stage")
        if current_stage_v == "responding":
            NLU_MIN_CONF_CLARI_V = Config.NLU_MIN_CONFIDENCE_FOR_CLARI   # 0.35
            voice_ml_conf_cur    = nlu_result.get("confidence", 0)
            if voice_ml_conf_cur < NLU_MIN_CONF_CLARI_V:
                strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_LOW_NLU", 0.70)
            else:
                strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD", 0.45)
            if rag_conf < strict_threshold:
                rag_escalate = True
                logger.info(
                    f"[{sid}] Seuil strict voice (hors-dataset) : "
                    f"rag_conf={rag_conf:.3f} < {strict_threshold} "
                    f"(ml_conf={voice_ml_conf_cur:.2f}) → escalade forcée"
                )
        elif current_stage_v == "clarifying":
            strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_AFTER_CLARI", 0.60)
            if rag_conf < strict_threshold:
                rag_escalate = True
                logger.info(
                    f"[{sid}] Seuil strict voice (après-clarification) : "
                    f"rag_conf={rag_conf:.3f} < {strict_threshold} → escalade forcée"
                )

        # Certains intents ne déclenchent jamais de transfert (voice)
        if rag_escalate:
            _chk_no_tr_v = (sess.get("pending_intent") or active_intent or "").strip()
            if _is_no_transfer_intent(_chk_no_tr_v):
                rag_escalate = False

        # Transfert humain si le RAG ne trouve pas de réponse fiable (voice)
        if rag_escalate:
            _chk_esc_v      = (sess.get("pending_intent") or active_intent or "").strip()
            _force_num_esc_v = _is_ask_number_intent(_chk_esc_v)

            # Réponse apprise ? → répondre directement (TOUS les intents)
            # Même pour مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب
            _orig_prob_v4 = (sess.get("original_problem") or
                             sess.get("last_transferred_problem") or transcript).strip()
            _learned_v4 = _find_session_learned_response(sess, _orig_prob_v4)
            if _learned_v4:
                bot_resp = _localize_response(_learned_v4, sess.get("collected_entities"))
                sess["history"].append(("bot", bot_resp))
                sess["stage"]          = "initial"
                sess["pending_intent"] = ""
                sess["solution_given"] = True
                logger.info(f"[{sid}] (vocal) Réponse apprise (rag_escalate) — transfert évité")
                return jsonify({
                    "transcript":    transcript,
                    "bot_response":  bot_resp,
                    "transferred":   False,
                    "session_ended": False,
                    "analysis":      _build_analysis(nlu_result, {},
                                                     collected_entities=sess.get("collected_entities")),
                })

            # 4 intents à numéro obligatoire → demander le numéro au lieu de transférer
            if _force_num_esc_v:
                _ask_num_v = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                     "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
                sess["stage"] = "waiting_for_request_number"
                if not sess.get("pending_intent"):
                    sess["pending_intent"] = active_intent
                if not sess.get("original_problem"):
                    sess["original_problem"] = transcript
                sess["history"].append(("bot", _ask_num_v))
                logger.info(f"[{sid}] (vocal) {_chk_esc_v} — demande numéro (rag_escalate)")
                return jsonify({"transcript": transcript, "bot_response": _ask_num_v,
                                "transferred": False, "session_ended": False, "analysis": {}})

            sess["transferred"] = True
            sess["last_transferred_problem"] = sess.get("original_problem") or transcript
            bot_resp = Config.TRANSFER_MESSAGE
            ticket   = transfer.create_ticket(
                session_id=sid, history=sess["history"],
                user_last_text=transcript, nlu_result=nlu_result,
                rag_confidence=rag_conf,
            )
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{sid}] (vocal) Transfert humain → rag_conf={rag_conf:.3f}")
            return jsonify({
                "transcript":   transcript,
                "bot_response": bot_resp,
                "transferred":  True,
                "ticket_id":    ticket.get("ticket_id"),
                "analysis":     _build_analysis(nlu_result, rag_result,
                                                collected_entities=sess.get("collected_entities"),
                                                transferred=True),
            })

        # قرار الذكاء الاصطناعي → حل تلقائي
        bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or Config.NOT_UNDERSTOOD_MSG

        # ── Intercept : réponse RAG contient une wilaya hardcodée + localisation incomplète ──
        _ents_rag_v = sess.get("collected_entities", {})
        if _response_has_wilaya(bot_resp) and _needs_location_intent(active_intent):
            if _needs_location(_ents_rag_v, active_intent):
                loc_q_v = Config.LOCATION_QUESTION
                sess["stage"] = "waiting_for_location"
                if not sess.get("pending_intent"):
                    sess["pending_intent"] = active_intent
                if not sess.get("original_problem"):
                    sess["original_problem"] = transcript
                sess["history"].append(("bot", loc_q_v))
                logger.info(f"[{sid}] (vocal) RAG wilaya hardcodée, localisation inconnue → demande")
                return jsonify({"transcript": transcript, "bot_response": loc_q_v,
                                "transferred": False, "session_ended": False, "analysis": {}})
            elif _needs_delegation(_ents_rag_v):
                deleg_q_v = _build_delegation_question(_ents_rag_v)
                sess["stage"] = "waiting_for_delegation"
                if not sess.get("pending_intent"):
                    sess["pending_intent"] = active_intent
                if not sess.get("original_problem"):
                    sess["original_problem"] = transcript
                sess["history"].append(("bot", deleg_q_v))
                logger.info(f"[{sid}] (vocal) RAG wilaya hardcodée, délégation manquante → demande")
                return jsonify({"transcript": transcript, "bot_response": deleg_q_v,
                                "transferred": False, "session_ended": False, "analysis": {}})

        bot_resp = response_eng._strip_emojis(
            _localize_response(bot_resp, sess.get("collected_entities"))
        )

        # ── Filet de sécurité : détection de boucle (voice) ──
        last_bot_resp_v = next(
            (t for role, t in reversed(sess.get("history", [])) if role == "bot"), ""
        )
        _chk_loop_v = (sess.get("pending_intent") or active_intent or "").strip()
        if (last_bot_resp_v and bot_resp.strip() == last_bot_resp_v.strip()
                and not _is_no_transfer_intent(_chk_loop_v)):
            _orig_prob_v5 = (sess.get("original_problem") or
                             sess.get("last_transferred_problem") or transcript).strip()
            _learned_v5 = _find_session_learned_response(sess, _orig_prob_v5)
            if _learned_v5:
                bot_resp = _localize_response(_learned_v5, sess.get("collected_entities"))
                sess["history"].append(("bot", bot_resp))
                sess["stage"]          = "initial"
                sess["pending_intent"] = ""
                sess["solution_given"] = True
                logger.info(f"[{sid}] (vocal) Réponse apprise (loop detection) — transfert évité")
                return jsonify({"transcript": transcript, "bot_response": bot_resp,
                                "transferred": False, "session_ended": False,
                                "analysis": _build_analysis(nlu_result, {},
                                                            collected_entities=sess.get("collected_entities"))})
            logger.info(f"[{sid}] BOUCLE DÉTECTÉE (voice) : même réponse → transfert forcé")
            sess["transferred"] = True
            sess["last_transferred_problem"] = sess.get("original_problem") or transcript
            bot_resp = Config.TRANSFER_MESSAGE
            ticket = transfer.create_ticket(
                session_id=sid, history=sess["history"],
                user_last_text=transcript, nlu_result=nlu_result,
                rag_confidence=rag_conf,
            )
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            return jsonify({
                "transcript":   transcript,
                "bot_response": bot_resp,
                "transferred":  True,
                "ticket_id":    ticket.get("ticket_id"),
                "analysis":     _build_analysis(nlu_result, rag_result,
                                                collected_entities=sess.get("collected_entities"),
                                                transferred=True),
            })

        sess["history"].append(("bot", bot_resp))

        # ── 4 intents à numéro obligatoire : forcer la demande si RAG ne l'a pas fait ──
        _force_num_rag_v = _is_ask_number_intent(
            (sess.get("pending_intent") or active_intent or "").strip()
        )
        if _force_num_rag_v and not _ASK_NUMBER_RE.search(bot_resp):
            _ask_num_rag_v = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                     "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
            if sess["history"] and sess["history"][-1][0] == "bot":
                sess["history"][-1] = ("bot", _ask_num_rag_v)
            sess["stage"] = "waiting_for_request_number"
            if not sess.get("pending_intent"):
                sess["pending_intent"] = active_intent
            if not sess.get("original_problem"):
                sess["original_problem"] = transcript
            logger.info(f"[{sid}] (vocal) Demande numéro forcée (RAG intercepté)")
            return jsonify({"transcript": transcript, "bot_response": _ask_num_rag_v,
                            "transferred": False, "session_ended": False, "analysis": {}})

        if _ASK_NUMBER_RE.search(bot_resp):
            sess["stage"] = "waiting_for_request_number"
            if not sess.get("pending_intent"):
                sess["pending_intent"] = active_intent
            if not sess.get("original_problem"):
                sess["original_problem"] = transcript
            logger.info(f"[{sid}] (vocal) Bot a demandé le numéro → waiting_for_request_number")
        elif _CALLBACK_NUMBER_RE.search(bot_resp):
            sess["stage"] = "waiting_for_callback_number"
        else:
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True   # ← active la détection de remerciement au prochain tour

        return jsonify({
            "transcript":   transcript,
            "bot_response": bot_resp,
            "analysis":     _build_analysis(nlu_result, rag_result,
                                            collected_entities=sess.get("collected_entities")),
        })

    except Exception as e:
        logger.error(f"Erreur voice: {e}")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
#  Apprentissage & Stats
# ════════════════════════════════════════════════════════════

@app.route("/api/human_response", methods=["POST"])
def human_response():
    data       = request.get_json()
    ticket_id  = data.get("ticket_id")
    response   = (data.get("response") or "").strip()
    sid        = data.get("session_id", "")
    if not response:
        return jsonify({"error": "Réponse vide"}), 400

    transfer.resolve_ticket(ticket_id, response)
    sess      = sessions.get(sid, {})
    history   = sess.get("history", [])
    last_user = next((t for r, t in reversed(history) if r == "user"), "")

    learning.learn_from_human(user_text=last_user, human_response=response, session_id=sid)
    if learning.should_retrain():
        response_eng.reload_index()
        learning.reset_counter()

    # ── Apprentissage éphémère (session uniquement, non persistant) ──────────
    # Stocké en mémoire → oublié dès la fermeture de session / redémarrage app.
    problem_text = sess.get("last_transferred_problem") or last_user
    if problem_text:
        _session_learn_store(sess, problem_text, response)
    else:
        logger.warning(
            f"[Session Learning] Impossible de mémoriser : problem_text vide "
            f"(last_transferred_problem='{sess.get('last_transferred_problem')}' "
            f"last_user='{last_user}')"
        )

    # Réinitialiser la session pour permettre de continuer la conversation et tester
    sess["solution_given"]   = False
    sess["transferred"]      = False
    sess["stage"]            = "initial"
    sess["pending_intent"]   = ""
    sess["original_problem"] = ""   # nettoyé : le prochain message est un nouveau problème

    # ── Transmettre la réponse à user_app.py (port 5001) ─────────────────────
    # CRITIQUE : user_app.py gère les sessions du bot mobile. Sans ce forward,
    # le bot ne reçoit jamais la réponse de l'agent → il ne l'apprend pas et
    # l'utilisateur ne la voit pas dans son interface mobile.
    import urllib.request, urllib.error as _ue
    _user_app_payload = json.dumps({
        "ticket_id":  ticket_id,
        "response":   response,
        "session_id": sid,
    }).encode("utf-8")
    try:
        _req = urllib.request.Request(
            "http://127.0.0.1:5001/api/internal/agent_reply",
            data=_user_app_payload,
            headers={
                "Content-Type":      "application/json",
                "X-Internal-Secret": "tt_backoffice_2026",
            },
            method="POST",
        )
        with urllib.request.urlopen(_req, timeout=8) as _r:
            _body = _r.read().decode("utf-8")
            logger.info(f"[human_response] Réponse transmise à user_app : {_body[:80]}")
    except _ue.HTTPError as _he:
        logger.warning(f"[human_response] user_app HTTP {_he.code} : {_he.read().decode()[:80]}")
    except Exception as _fe:
        logger.warning(f"[human_response] user_app non accessible : {_fe}")

    return jsonify({"success": True, "learned": True})


# ════════════════════════════════════════════════════════════
#  STT voix de l'AGENT humain — prompt optimisé réponses agent
#  Utilisé par le bouton mic dans la modal agent (index.html)
# ════════════════════════════════════════════════════════════

# Prompt STT spécialisé pour la voix de l'agent (solutions, instructions télécom)
# Couvre spécifiquement les 5 types de problèmes gérés par apprentissage :
#   تغيير الخدمة, مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب
_AGENT_STT_PROMPT = (
    "وكيل دعم فني في تليكوم تونس يشرح حل لمشكلة بالدارجة التونسية. "
    "الوكيل يعطي تعليمات وحلول واضحة. "
    # ── تغيير الخدمة ──────────────────────────────────────────
    "تغيير الخدمة: الطلب مسجل، راح يتغير الباقة، فريق التقني باش يتصل بيك. "
    # ── مشكلة في الدفع ────────────────────────────────────────
    "مشكلة الدفع: الدفع مسجل صح، العملية ناجحة، المبلغ تحصل، ما فماش مشكلة في الدفع. "
    # ── اعتراض على الفاتورة ───────────────────────────────────
    "اعتراض الفاتورة: الفاتورة صحيحة، المبلغ محسوب بالضبط، ما فماش خطأ في الفاتورة، "
    "هذا الاستهلاك تاعك الحقيقي، راح نفتح ملف اعتراض. "
    # ── انقطاع الانترنات ──────────────────────────────────────
    "انقطاع الانترنت: فريق التدخل التقني باش يجي، المشكل راح يتسوى في ظرف، "
    "ما فماش انقطاع في منطقتك، المنطقة تاعتك مغطاة، "
    "راح نعمل إعادة تشغيل على الخط تاعك. "
    # ── تأخير في التركيب ──────────────────────────────────────
    "تأخير التركيب: الطلب مسجل، التقني باش يجي في الموعد، "
    "ما فماش تأخير من عندنا، الموعد محدد. "
    # ── كلمات شائعة في ردود الوكلاء ─────────────────────────
    "الكلمات الشائعة: ياسر، برشا، مش مشكلة، حتى مشكلة، "
    "ربي يعطيك الصحة، مشكور، شكرن على صبرك. "
    "أسماء مدن: تونس، سوسة، صفاقس، المنستير، بنزرت، نابل، قابس."
)

@app.route("/api/voice_agent", methods=["POST"])
def voice_agent():
    """
    STT spécialisé pour la voix de l'AGENT HUMAIN.

    Différences par rapport à /api/voice (voix client) :
      - initial_prompt adapté aux réponses d'agent (solutions télécom en darija)
      - Couvre les 5 types de problèmes avec apprentissage
      - beam_size plus élevé (7) pour meilleure précision sur vocabulaire technique
      - no_speech_threshold plus bas (0.4) → capte mieux les voix d'agents (micro bureau)
      - temperature légèrement plus haute (0.1) → moins de troncature sur phrases longues

    Retourne : { "transcript": str }  — à injecter dans la textarea agent
    """
    if not stt_model:
        return jsonify({"error": "Whisper non disponible"}), 503

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "Pas de fichier audio"}), 400

    try:
        suffix = ".webm" if "webm" in (audio_file.content_type or "") else ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        # Paramètres STT optimisés pour la voix de l'agent
        segments, _ = stt_model.transcribe(
            tmp_path,
            language=Config.STT_LANGUAGE,          # "ar"
            beam_size=7,                            # Plus élevé → meilleure précision
            vad_filter=False,                       # DÉSACTIVÉ — évite la coupure agressive des segments
            initial_prompt=_AGENT_STT_PROMPT,       # Prompt spécialisé agent
            temperature=0.0,                        # Déterministe → transcription complète
            condition_on_previous_text=True,        # Continuité entre segments
            no_speech_threshold=0.8,                # Haute tolérance → Whisper ignore peu de segments
        )
        transcript = " ".join(s.text.strip() for s in segments).strip()
        os.unlink(tmp_path)

        logger.info(f"[voice_agent] STT agent → '{transcript[:80]}'")
        return jsonify({"transcript": transcript})

    except Exception as e:
        logger.error(f"Erreur voice_agent STT: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def stats():
    learned = learning.get_stats()
    # Déterminer le moteur TTS actif
    has_elevenlabs = (Config.ELEVENLABS_API_KEY not in ("", "YOUR_API_KEY_HERE"))
    try:
        import edge_tts as _et
        has_edge_tts = True
    except ImportError:
        has_edge_tts = False
    try:
        from gtts import gTTS as _gTTS
        has_gtts = True
    except ImportError:
        has_gtts = False
    try:
        from TTS.api import TTS as _CTTS   # noqa
        has_coqui = True
    except ImportError:
        has_coqui = False

    if has_coqui:
        custom = getattr(Config, "COQUI_TTS_CUSTOM_MODEL", "")
        model_lbl = os.path.basename(custom) if custom else getattr(Config, "COQUI_TTS_MODEL", "ar/css10/vits")
        tts_engine = f"Coqui TTS ({model_lbl})"
    elif has_edge_tts:
        tts_engine = f"edge-tts ({getattr(Config, 'EDGE_TTS_VOICE', 'ar-TN-ReemNeural')})"
    elif has_elevenlabs:
        tts_engine = "ElevenLabs"
    elif has_gtts:
        tts_engine = "gTTS"
    else:
        tts_engine = "navigateur"

    return jsonify({
        "ml_active":      ml_predictor.is_available,
        "ml_backend":     ml_predictor.backend_name,
        "whisper_active": stt_model is not None,
        "coqui_tts":      has_coqui,
        "elevenlabs":     has_elevenlabs,
        "gtts":           has_gtts,
        "tts_engine":     tts_engine,
        "dataset_size":   response_eng.index.ntotal if response_eng.index else 0,
        "learned":        learned,
        "sessions":       len(sessions),
        "embedding":      Config.EMBEDDING_MODEL.split("/")[-1],
    })


@app.route("/api/tickets", methods=["GET"])
def pending_tickets():
    return jsonify({"tickets": transfer.get_pending_tickets()})


# ════════════════════════════════════════════════════════════
#  BACK-OFFICE — Monitoring conversations utilisateurs
# ════════════════════════════════════════════════════════════

@app.route("/api/live_conversations", methods=["GET"])
def live_conversations():
    """
    Retourne les conversations recentes de TOUS les utilisateurs (back-office).
    Permet de monitorer en temps reel les echanges user_app ↔ bot dans app.py.
    """
    try:
        from firebase_config import conversations_get_all_recent
        limit = min(int(request.args.get("limit", 30)), 100)
        convs = conversations_get_all_recent(limit=limit)
        return jsonify({"conversations": convs, "total": len(convs)})
    except Exception as e:
        logger.error(f"[live_conversations] Erreur : {e}", exc_info=True)
        return jsonify({"conversations": [], "total": 0, "error": str(e)})


@app.route("/api/conv_messages/<conv_id>", methods=["GET"])
def conv_messages(conv_id: str):
    """
    Retourne les messages d'une conversation specifique (back-office).
    Inclut également le champ last_problem (problème signalé au transfert)
    et les données NLU par message utilisateur.
    """
    try:
        from firebase_config import messages_get_by_conversation, conversation_get
        msgs = messages_get_by_conversation(conv_id)
        # Serialiser les timestamps
        for m in msgs:
            for field in ("created_at",):
                v = m.get(field)
                if hasattr(v, "strftime"):
                    m[field] = v.strftime("%d/%m/%Y %H:%M")
                elif v:
                    m[field] = str(v)
        # Récupérer le texte du problème stocké lors du transfert
        last_problem = ""
        try:
            conv_doc = conversation_get(conv_id)
            if conv_doc:
                last_problem = conv_doc.get("last_problem", "")
        except Exception:
            pass
        return jsonify({"messages": msgs, "conv_id": conv_id,
                        "last_problem": last_problem})
    except Exception as e:
        logger.error(f"[conv_messages] Erreur : {e}", exc_info=True)
        return jsonify({"messages": [], "error": str(e)})


@app.route("/api/conv_nlu_analysis/<conv_id>", methods=["GET"])
def conv_nlu_analysis(conv_id: str):
    """
    Rejoue exactement la même logique NLU + RAG que le Test Bot sur une
    conversation back-office, en accumulant les entités sur tous les messages
    user (wilaya, delegation, service) comme le fait `_update_entities` en live.

    Retourne le même dict d'analyse que `/api/chat` (cf. `_build_analysis`) :
      intent, confidence_nlu, confidence_rag, sentiment, service_type,
      wilaya, delegation, action, decision, escalate.
    """
    try:
        from firebase_config import messages_get_by_conversation

        msgs = messages_get_by_conversation(conv_id)
        user_msgs = [m for m in msgs if m.get("role") == "user"]

        if not user_msgs:
            return jsonify({"analysis": None, "has_user_msg": False})

        # Mini-session : on accumule collected_entities comme user_app le fait
        mini_sess = {"collected_entities": {}, "history": []}

        last_nlu  = None
        last_rag  = None
        last_text = ""

        for m in user_msgs:
            text = m.get("content", "") or ""
            if not text.strip():
                continue
            try:
                nlu_res = nlu.analyze(text)
            except Exception as e:
                logger.warning(f"[conv_nlu_analysis] NLU error on msg: {e}")
                continue

            # Accumulation des entités — même règle que _update_entities (user_app.py)
            ents = nlu_res.get("entities", {}) or {}
            loc_explicit = ents.get("location_explicit", False)
            for k, v in ents.items():
                if k == "location_explicit" or not v:
                    continue
                if k in ("wilaya", "delegation"):
                    if loc_explicit:
                        mini_sess["collected_entities"][k] = v
                else:
                    mini_sess["collected_entities"][k] = v

            mini_sess["history"].append(("user", text))
            last_nlu  = nlu_res
            last_text = text

        if last_nlu is None:
            return jsonify({"analysis": None, "has_user_msg": False})

        # RAG sur le dernier message user (avec historique)
        try:
            last_rag = response_eng.find_response(
                last_text,
                mini_sess["history"],
                nlu_intent=last_nlu.get("intent", ""),
            )
        except Exception as e:
            logger.warning(f"[conv_nlu_analysis] RAG error: {e}")
            last_rag = {"confidence": 0, "escalate": False}

        # Transféré → décision = escalade (comme Test Bot)
        conv_transferred = False
        try:
            from firebase_config import conversation_get
            conv_doc = conversation_get(conv_id)
            if conv_doc and conv_doc.get("statut") == "transferee":
                conv_transferred = True
        except Exception:
            pass

        analysis = _build_analysis(
            last_nlu,
            last_rag,
            clarifying=False,
            collected_entities=mini_sess["collected_entities"],
            transferred=conv_transferred,
            unknown_problem=False,
        )
        return jsonify({
            "analysis":      analysis,
            "has_user_msg":  True,
            "last_user_text": last_text,
        })
    except Exception as e:
        logger.error(f"[conv_nlu_analysis] Erreur : {e}", exc_info=True)
        return jsonify({"analysis": None, "has_user_msg": False, "error": str(e)})


@app.route("/api/admin_stats", methods=["GET"])
def admin_stats_route():
    """
    Dashboard Admin : statistiques globales agrégées.
    Retourne :
      - total réclamations
      - répartition / pourcentages par statut
      - délai moyen de réponse, temps min. de résolution
    """
    try:
        from firebase_config import admin_stats
        return jsonify(admin_stats())
    except Exception as e:
        logger.error(f"[admin_stats] Erreur : {e}", exc_info=True)
        return jsonify({
            "total": 0,
            "counts": {"en_cours": 0, "resolue": 0, "transferee": 0, "fermee": 0},
            "percentages": {"en_cours": 0, "resolue": 0, "transferee": 0, "fermee": 0},
            "avg_response_sec": 0, "avg_response_str": "—",
            "min_response_sec": 0, "min_response_str": "—",
            "resolues_count": 0,
            "error": str(e),
        })


_USER_APP_INTERNAL_SECRET = "tt_backoffice_2026"   # doit correspondre à user_app.py

@app.route("/api/agent_reply", methods=["POST"])
def agent_reply_proxy():
    """
    Proxy back-office → user_app (port 5001) pour transmettre la réponse
    de l'agent humain et déclencher l'apprentissage de session.
    Utilise le endpoint interne /api/internal/agent_reply (sans login_required).
    """
    import urllib.request, urllib.error
    data = request.get_json(silent=True) or {}
    payload = json.dumps(data).encode("utf-8")
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:5001/api/internal/agent_reply",
            data=payload,
            headers={
                "Content-Type":     "application/json",
                "X-Internal-Secret": _USER_APP_INTERNAL_SECRET,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8")
            return body, resp.status, {"Content-Type": "application/json"}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.warning(f"[agent_reply_proxy] HTTPError {e.code} : {body[:200]}")
        return jsonify({"success": False, "error": f"HTTP {e.code}", "detail": body}), e.code
    except Exception as e:
        logger.error(f"[agent_reply_proxy] Erreur : {e}", exc_info=True)
        return jsonify({"success": False,
                        "error": "user_app non accessible (port 5001)",
                        "detail": str(e)}), 502


# ════════════════════════════════════════════════════════════
#  Utilitaires
# ════════════════════════════════════════════════════════════

def _build_analysis(nlu_result, rag_result, clarifying=False, collected_entities=None,
                    transferred=False, unknown_problem=False):
    """
    Construit le dict d'analyse pour le frontend.

    collected_entities : entités accumulées sur toute la session
    (wilaya, delegation, service détectés dans les tours précédents).
    Utilisées en fallback quand le message courant ne contient pas de localisation.

    transferred     : True → forcer قرار = تحويل لوكيل بشري.
    unknown_problem : True → problème non reconnu → tous les champs NLU = vides/nuls.
    """
    # Problème non reconnu : tous les champs NLU sont invalides → les vider
    if unknown_problem:
        return {
            "intent":         "",
            "confidence_nlu": 0,
            "confidence_rag": 0,
            "sentiment":      "",
            "service_type":   "",
            "wilaya":         "",
            "delegation":     "",
            "action":         "",
            "decision":       "escalade_agent_humain",
            "ml_used":        False,
            "ml_backend":     ml_predictor.backend_name,
            "escalate":       True,
            "clarifying":     False,
        }

    curr     = nlu_result.get("entities", {})
    acc      = collected_entities or {}

    # Fusionner : les entités accumulées (acc) ont priorité sur les entités
    # du tour courant (curr) pour wilaya/delegation, car le ML prédit souvent
    # "تونس" par défaut sur les messages courts (ex: "موبيل", "إيه").
    # Pour les autres champs (service_type, phone…) on prend le plus récent.
    def _pick(key):
        # Pour la localisation : préférer l'accumulé (détecté depuis le texte brut)
        if key in ("wilaya", "delegation"):
            return acc.get(key) or curr.get(key) or ""
        # Pour les autres : préférer le courant, fallback accumulé
        return curr.get(key) or acc.get(key) or ""

    # Wilaya / délégation : "غير محدد" si non détectées
    wilaya     = _pick("wilaya")     or "غير محدد"
    delegation = _pick("delegation") or "غير محدد"

    # قرار الذكاء الاصطناعي : تحويل لوكيل بشري si :
    #   - transferred=True (boucle détectée, seuil strict post-clarification…)
    #   - OU rag_result["escalate"] = True (RAG normal escalation)
    escalate = transferred or (rag_result or {}).get("escalate", False)
    decision = "escalade_agent_humain" if escalate else "reponse_automatique"

    return {
        "intent":           nlu_result.get("intent", ""),
        "confidence_nlu":   round(nlu_result.get("confidence", 0) * 100),
        "confidence_rag":   round((rag_result or {}).get("confidence", 0) * 100),
        "sentiment":        nlu_result.get("sentiment", "محايد"),
        "service_type":     _pick("service_type") or (rag_result or {}).get("service_type", ""),
        "wilaya":           wilaya,
        "delegation":       delegation,
        "action":           nlu_result.get("action") or (rag_result or {}).get("action", ""),
        "decision":         decision,
        "ml_used":          nlu_result.get("ml_used", False),
        "ml_backend":       nlu_result.get("backend", ml_predictor.backend_name),
        "escalate":         escalate,
        "clarifying":       clarifying,
    }


def _update_entities(sess: dict, nlu_result: dict, user_text: str = ""):
    """
    Accumule les entités sur plusieurs tours.

    Règle localisation :
      - wilaya / delegation ne sont mis à jour QUE si le NLU a trouvé la
        localisation EXPLICITEMENT dans le texte (location_explicit=True).
      - Fallback regex : si le NLU ne détecte pas de wilaya/délégation,
        on tente de les extraire directement depuis user_text.
    """
    if "collected_entities" not in sess:
        sess["collected_entities"] = {}

    entities = nlu_result.get("entities", {})
    loc_explicit = entities.get("location_explicit", False)
    collected = sess["collected_entities"]

    for k, v in entities.items():
        if k == "location_explicit":
            continue
        if not v:
            continue
        if k in ("wilaya", "delegation"):
            if loc_explicit:
                collected[k] = v
        else:
            collected[k] = v

    # Fallback regex : wilaya depuis le texte si NLU ne l'a pas trouvée
    if not collected.get("wilaya") and user_text:
        w = _extract_wilaya_from_text(user_text)
        if w:
            collected["wilaya"] = w

    # Fallback regex : délégation depuis le texte si NLU ne l'a pas trouvée
    if not collected.get("delegation") and user_text:
        d = _extract_delegation_from_text(user_text)
        if d:
            collected["delegation"] = d


def _build_enriched_query(sess: dict, current_text: str) -> str:
    """
    Construit la requête RAG pour l'étape 2.

    Stratégie : [problème_original] + [réponse_clarification]
    → parfaitement aligné sur la structure du dataset :
       user_problem + user_answer = ce qu'on a indexé dans le FAISS principal.

    On N'ajoute PAS l'intent NLU dans le texte (il est souvent faux
    avec TF-IDF et polluerait l'embedding).
    """
    original = sess.get("original_problem", "")

    if original and original != current_text:
        # Stage 2 : on a le problème original + la réponse à la clarification
        combined = f"{original} {current_text}".strip()
    else:
        # Stage 1 ou premier tour sans clarification
        history    = sess.get("history", [])
        user_turns = [t for r, t in history if r == "user"]
        combined   = " ".join(user_turns[-3:]).strip()

    return combined or current_text


def _is_stop(text):
    return bool(re.search("|".join(re.escape(k) for k in Config.STOP_KEYWORDS), text, re.IGNORECASE))


def _localize_response(text: str, entities: dict) -> str:
    """
    Localise une réponse RAG :
    1. Remplace les placeholders ([المنطقة], [الولاية], [المعتمدية]…) par la localisation.
    2. Remplace les noms de wilayas ÉTRANGÈRES (≠ wilaya du user) :
       • Si le user est à المنستير et la réponse dit "في المنستير" → on garde
       • Si le user est à المنستير et la réponse dit "في باجة" → remplacé par "في المنستير"
       • Si localisation inconnue → wilaya étrangère remplacée par "منطقتك"
    3. Remplace "في تونس" / "بتونس" / "بالعاصمة" (hardcodés dans beaucoup de réponses RAG)
       par la wilaya réelle de l'utilisateur quand celui-ci n'est pas dans le Grand Tunis.
       "تونس" est exclu de _WILAYA_RAW_DETECT (ambiguïté capitale/pays) mais traité ici.
    """
    if not text:
        return text
    entities = entities or {}
    user_wilaya = entities.get("wilaya", "")
    user_deleg  = entities.get("delegation", "")
    placeholder_loc = user_deleg or user_wilaya or "منطقتك"

    # Remplacer les placeholders textuels
    for placeholder in ["[المنطقة]", "[الولاية]", "[المعتمدية]", "المنطقة المحددة"]:
        text = text.replace(placeholder, placeholder_loc)

    # Remplacer les wilayas hardcodées (différentes de la wilaya du user)
    if _WILAYA_DETECT_RE.search(text):
        replacement = user_wilaya if user_wilaya else "منطقتك"
        def _replace_wilaya_smart(m: re.Match) -> str:
            found = m.group(0)
            if user_wilaya and found == user_wilaya:
                return found   # Ne pas remplacer la wilaya du user
            return replacement
        text = _WILAYA_DETECT_RE.sub(_replace_wilaya_smart, text)

    # Cas spécial "تونس" : remplacer dans les constructions locatives quand l'utilisateur
    # n'est pas dans le Grand Tunis (تونس / أريانة / بن عروس / منوبة).
    if user_wilaya and user_wilaya not in ("تونس", "أريانة", "بن عروس", "منوبة"):
        text = re.sub(r'في\s+تونس\b', f'في {user_wilaya}', text)
        text = re.sub(r'بتونس\b',     f'في {user_wilaya}', text)
        text = re.sub(r'بالعاصمة',    f'في {user_wilaya}', text)

    return text


def _build_delegation_question(entities: dict) -> str:
    """
    Construit la question de délégation personnalisée avec la wilaya si connue.
    Ex : "في أي معتمدية بالضبط في المنستير؟" ou "في أي معتمدية بالضبط؟"
    """
    wilaya = (entities or {}).get("wilaya", "").strip()
    if wilaya:
        tmpl = getattr(Config, "DELEGATION_QUESTION",
                       "في أي معتمدية بالضبط في {wilaya}؟")
        return tmpl.replace("{wilaya}", wilaya)
    return getattr(Config, "DELEGATION_ONLY_QUESTION", "في أي معتمدية بالضبط؟")


def _needs_delegation(collected_entities: dict) -> bool:
    """
    Retourne True si l'utilisateur a mentionné une wilaya mais
    pas de délégation spécifique (delegation absente ou == wilaya).

    Exemple :
      {"wilaya": "المنستير", "delegation": "المنستير"} → True  (capitale = non spécifique)
      {"wilaya": "المنستير", "delegation": "قصر هلال"} → False (délégation connue)
      {"wilaya": "", "delegation": ""}                  → False (aucune info)
    """
    w = (collected_entities or {}).get("wilaya", "")
    d = (collected_entities or {}).get("delegation", "")
    return bool(w) and (not d or d == w)


def _normalize_for_keyword_match(text: str) -> str:
    """
    Normalise le texte arabe pour la comparaison de mots-clés.
    - Supprime les diacritiques ajoutés par Whisper (ex: شُكْراً → شكرا)
    - Normalise les variantes de Alef
    """
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)   # diacritiques تشكيل
    text = re.sub(r'[إأآ]', 'ا', text)                   # alef variants
    return text


def _is_greeting(text):
    """Vérifie si le texte contient une salutation (avec normalisation Whisper)."""
    norm = _normalize_for_keyword_match(text)
    keys_norm = [_normalize_for_keyword_match(k) for k in Config.GREETING_KEYWORDS]
    return bool(re.search("|".join(re.escape(k) for k in keys_norm), norm, re.IGNORECASE))


def _is_thanks(text):
    """Vérifie si le texte contient un remerciement (avec normalisation Whisper)."""
    norm = _normalize_for_keyword_match(text)
    keys_norm = [_normalize_for_keyword_match(k) for k in Config.THANKS_KEYWORDS]
    return bool(re.search("|".join(re.escape(k) for k in keys_norm), norm, re.IGNORECASE))


def _is_negation(text):
    """
    Vérifie si le texte est une réponse négative (refus / absence d'info)
    à une question de clarification.

    Ex: "لا معنديش", "ماعنديش", "مانجمش", "non"…

    Stratégie en 2 passes :
      1. AFFIRMATION en premier : si l'user dit "إي"/"نعم"/"أيوا"…
         → return False immédiatement (il confirme, pas de négation).
         Évite le faux positif classique "إي نعم، لومبة لوس تشعل بالأحمر"
         où "بالأحمر" → "بالاحمر" après normalisation alef, et contient
         la sous-chaîne "لا" (ل+ا) sans être une vraie négation.

      2. NÉGATION avec word-boundary pour les mots courts (≤ 4 chars) :
         "لا" ne matche PAS à l'intérieur de "بالاحمر", "بلاصة", "غلا"…
         Les phrases longues sont matchées normalement (assez spécifiques).
    """
    norm = _normalize_for_keyword_match(text)

    # ── Passe 1 : affirmation → court-circuit ────────────────
    affirm_keys = [_normalize_for_keyword_match(k)
                   for k in getattr(Config, "AFFIRMATION_KEYWORDS", [])]
    if affirm_keys:
        pat_affirm = "|".join(re.escape(k) for k in affirm_keys if k)
        if pat_affirm and re.search(pat_affirm, norm, re.IGNORECASE):
            return False   # L'user a dit OUI → pas une négation

    # ── Passe 2 : négation ───────────────────────────────────
    # Séparateurs de mots en arabe/latin : espace, ponctuation, début/fin
    SEP = r'(?:^|[\s،؟\.!؛،\(\)\[\]\-،])'
    END = r'(?=$|[\s،؟\.!؛،\(\)\[\]\-،])'

    keys_norm = [_normalize_for_keyword_match(k) for k in Config.NEGATION_KEYWORDS]
    patterns = []
    for k in keys_norm:
        if not k:
            continue
        if len(k) <= 4:
            # Mot court : imposer les frontières de mot pour éviter les faux positifs
            patterns.append(SEP + re.escape(k) + END)
        else:
            # Phrase longue : pas de frontière nécessaire (assez spécifique)
            patterns.append(re.escape(k))

    if not patterns:
        return False
    return bool(re.search("|".join(patterns), norm, re.IGNORECASE))


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  🏢 VoiceBot Tunisie Telecom — Interface Web")
    print(f"  ML Backend : {ml_predictor.backend_name}")
    print("  Ouvre : http://localhost:5000")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
