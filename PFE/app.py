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

# ── Sessions ──────────────────────────────────────────────────
sessions = {}

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
        }
    return sessions[sid]

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

    # Mettre à jour les entités collectées
    _update_entities(sess, nlu_result)

    # ══════════════════════════════════════════════════════════
    #  DIALOGUE EN 2 ÉTAPES (fidèle au dataset)
    # ══════════════════════════════════════════════════════════

    # ── ÉTAPE 1 : Première plainte → poser une QUESTION ──────
    if stage == "initial":
        # Chercher la question dans le dataset via similarité sémantique pure
        clari = response_eng.find_clarification_question(
            user_text, nlu_intent=intent, nlu_service=service_type
        )

        if clari["question"]:
            bot_resp = response_eng._strip_emojis(clari["question"])

            # Si la délégation n'est pas encore connue → la demander
            # en complément de la question de clarification (un seul tour)
            if _needs_delegation(sess.get("collected_entities")):
                w = sess["collected_entities"].get("wilaya", "")
                bot_resp += "  " + Config.DELEGATION_QUESTION.format(wilaya=w)

            sess["stage"] = "clarifying"

            # CRUCIAL : on stocke l'intent du RECORD trouvé (fiable à 100%)
            # et NON l'intent NLU (TF-IDF, souvent faux sur le darija mixte)
            record_intent = clari.get("intent") or intent
            sess["pending_intent"]   = record_intent
            sess["original_problem"] = user_text   # Sauvegarder le problème original

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

        # Pas de question trouvée → répondre directement
        sess["stage"]          = "responding"
        sess["pending_intent"] = intent

    # ── ÉTAPE 2 : Réponse finale (après clarification) ───────
    # active_intent = intent du RECORD (fiable) ou NLU si pas de record
    active_intent = sess.get("pending_intent") or intent

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

    # Transférer uniquement si vraiment pas de réponse fiable
    # et qu'on a déjà posé la question de clarification
    should_transfer = (
        rag_escalate
        and active_intent in ("غير محدد", "unknown", "")
        and sess["turn"] >= Config.ESCALATION_ATTEMPTS
    )

    if should_transfer:
        sess["transferred"] = True
        bot_resp = Config.TRANSFER_MESSAGE
        ticket   = transfer.create_ticket(
            session_id=sid, history=sess["history"],
            user_last_text=user_text, nlu_result=nlu_result,
            rag_confidence=rag_conf,
        )
        sess["history"].append(("bot", bot_resp))
        return jsonify({
            "bot_response": bot_resp,
            "transferred":  True,
            "ticket_id":    ticket.get("ticket_id"),
            "analysis":     _build_analysis(nlu_result, rag_result,
                                            collected_entities=sess.get("collected_entities")),
        })

    # ── Choisir la réponse ────────────────────────────────────
    bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or ""
    if not bot_resp:
        bot_resp = Config.NOT_UNDERSTOOD_MSG

    # Remplacer toute localisation du dataset par la localisation réelle de l'user
    bot_resp = _localize_response(bot_resp, sess.get("collected_entities"))

    sess["history"].append(("bot", bot_resp))
    # Remettre en mode initial pour le prochain problème dans la même session
    # et marquer qu'une solution a été fournie (attend un éventuel remerciement)
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
      1. ElevenLabs (voix masculine, meilleure qualité)  → si clé configurée
      2. gTTS       (voix arabe, gratuite, serveur-side) → fallback automatique
    """
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Texte vide"}), 400

    api_key  = Config.ELEVENLABS_API_KEY
    voice_id = Config.ELEVENLABS_VOICE_ID

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
        _update_entities(sess, nlu_result)

        sess["turn"] += 1
        sess["history"].append(("user", transcript))

        # Étape 1 : question
        if stage == "initial" and intent not in ("غير محدد", "unknown", ""):
            clari = response_eng.find_clarification_question(
                transcript, nlu_intent=intent, nlu_service=service_type
            )
            if clari["question"]:
                bot_resp = response_eng._strip_emojis(clari["question"])

                # Si la délégation n'est pas encore connue → la demander en même temps
                if _needs_delegation(sess.get("collected_entities")):
                    w = sess["collected_entities"].get("wilaya", "")
                    bot_resp += "  " + Config.DELEGATION_QUESTION.format(wilaya=w)

                sess["stage"]          = "clarifying"
                sess["pending_intent"] = intent
                sess["history"].append(("bot", bot_resp))
                return jsonify({
                    "transcript":   transcript,
                    "bot_response": bot_resp,
                    "analysis":     _build_analysis(nlu_result, {}, clarifying=True,
                                                    collected_entities=sess.get("collected_entities")),
                })

        # Étape 2 : réponse
        active_intent  = sess.get("pending_intent") or intent
        enriched       = _build_enriched_query(sess, transcript)
        rag_result     = response_eng.find_response(
            enriched, sess["history"], nlu_intent=active_intent)
        bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or Config.NOT_UNDERSTOOD_MSG

        # Remplacer toute localisation du dataset par la localisation réelle de l'user
        bot_resp = _localize_response(bot_resp, sess.get("collected_entities"))

        sess["history"].append(("bot", bot_resp))
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

    return jsonify({"success": True, "learned": True})


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

    if has_edge_tts:
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
#  Utilitaires
# ════════════════════════════════════════════════════════════

def _build_analysis(nlu_result, rag_result, clarifying=False, collected_entities=None):
    """
    Construit le dict d'analyse pour le frontend.

    collected_entities : entités accumulées sur toute la session
    (wilaya, delegation, service détectés dans les tours précédents).
    Utilisées en fallback quand le message courant ne contient pas de localisation.
    """
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

    return {
        "intent":           nlu_result.get("intent", ""),
        "confidence_nlu":   round(nlu_result.get("confidence", 0) * 100),
        "confidence_rag":   round((rag_result or {}).get("confidence", 0) * 100),
        "sentiment":        nlu_result.get("sentiment", "محايد"),
        "service_type":     _pick("service_type") or (rag_result or {}).get("service_type", ""),
        "wilaya":           _pick("wilaya"),
        "delegation":       _pick("delegation"),
        "action":           nlu_result.get("action") or (rag_result or {}).get("action", ""),
        "decision":         nlu_result.get("decision", "reponse_automatique"),
        "ml_used":          nlu_result.get("ml_used", False),
        "ml_backend":       nlu_result.get("backend", ml_predictor.backend_name),
        "escalate":         (rag_result or {}).get("escalate", False),
        "clarifying":       clarifying,
    }


def _update_entities(sess: dict, nlu_result: dict):
    """
    Accumule les entités sur plusieurs tours.

    Règle localisation :
      - wilaya / delegation ne sont mis à jour QUE si le NLU a trouvé la
        localisation EXPLICITEMENT dans le texte (location_explicit=True).
      - Cela évite que les valeurs par défaut du ML ("تونس", "مارث"…)
        écrasent une localisation correcte détectée sur un tour précédent.
    """
    if "collected_entities" not in sess:
        sess["collected_entities"] = {}

    entities = nlu_result.get("entities", {})
    loc_explicit = entities.get("location_explicit", False)

    for k, v in entities.items():
        if k == "location_explicit":
            continue   # champ interne, ne pas stocker
        if not v:
            continue   # ignorer les valeurs vides / None
        # Localisation : ne mettre à jour que si détectée dans le texte
        if k in ("wilaya", "delegation"):
            if loc_explicit:
                sess["collected_entities"][k] = v
            # Sinon : garder la valeur accumulée (ne pas écraser)
        else:
            sess["collected_entities"][k] = v


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


def _localize_response(response: str, collected_entities: dict) -> str:
    """
    Remplace tout nom de localisation tunisienne dans la réponse du bot
    par la localisation réelle de l'utilisateur.

    Exemple :  "فما ضغط كبير حالياً في قفصة"
             → "فما ضغط كبير حالياً في المنستير"
    si collected_entities = {"wilaya": "المنستير", "delegation": "قصر هلال"}

    Stratégie :
      - Parcourt la liste triée (plus longs d'abord) pour éviter
        les faux positifs partiels (ex: "سوسة" avant "بوسوسة").
      - Remplace par la wilaya de l'user (le dataset répond
        au niveau wilaya : "في قفصة", "في سوسة"…).
      - S'arrête au premier remplacement (une seule localisation par réponse).
    """
    if not response:
        return response

    user_wilaya = (collected_entities or {}).get("wilaya", "")
    user_deleg  = (collected_entities or {}).get("delegation", "")

    if not user_wilaya:
        return response   # Localisation inconnue → rien à remplacer

    # Ne pas remplacer la localisation de l'utilisateur elle-même
    user_locs = {l for l in (user_wilaya, user_deleg) if l}

    for loc in _ALL_TUNISIAN_LOCS:
        if loc in user_locs:
            continue
        if loc in response:
            response = response.replace(loc, user_wilaya)
            break   # Un seul remplacement de localisation par réponse

    return response


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


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  🏢 VoiceBot Tunisie Telecom — Interface Web")
    print(f"  ML Backend : {ml_predictor.backend_name}")
    print("  Ouvre : http://localhost:5000")
    print("="*55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
