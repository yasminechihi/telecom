#!/usr/bin/env python3
# ============================================================
#  user_app.py — Interface Espace Client Tunisie Telecom
#  Flask app séparée (port 5001) — Ne touche PAS à app.py
#
#  Fonctionnalités :
#    - Authentification : Sign In / Sign Up (Firebase Firestore)
#    - Chat avec le bot (même logique que app.py, sans détails NLU)
#    - Dashboard : historique des réclamations par client
#    - Design Tunisie Telecom (violet, blanc)
#    - Transfert vers agent humain via Asterisk AMI (WSL)
# ============================================================

import os, sys, json, uuid, logging, re, types, importlib.util
import io, asyncio, tempfile
from datetime import datetime
from functools import wraps

from flask import (Flask, request, jsonify, render_template,
                   session, redirect, url_for, flash, send_file)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import config as Config

# ══════════════════════════════════════════════════════════
#  Import direct des modules bot (bypass modules/__init__.py)
#  ──────────────────────────────────────────────────────────
#  modules/__init__.py importe STTModule (sounddevice, numpy audio)
#  et TTSModule qui ne sont PAS nécessaires pour l'interface texte.
#  On charge uniquement les 4 modules utiles via importlib.
# ══════════════════════════════════════════════════════════

def _direct_import(dotted_name: str, file_path: str):
    """Charge un fichier .py directement sans passer par __init__.py."""
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]
    spec = importlib.util.spec_from_file_location(dotted_name, file_path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod

# Enregistrer le package 'modules' sans exécuter __init__.py
if "modules" not in sys.modules:
    _pkg = types.ModuleType("modules")
    _pkg.__path__    = [os.path.join(BASE_DIR, "modules")]
    _pkg.__package__ = "modules"
    _pkg.__file__    = os.path.join(BASE_DIR, "modules", "__init__.py")
    sys.modules["modules"] = _pkg

_MODS_DIR = os.path.join(BASE_DIR, "modules")

_ml_mod   = _direct_import("modules.ml_predictor",
                            os.path.join(_MODS_DIR, "ml_predictor.py"))
_nlu_mod  = _direct_import("modules.nlu",
                            os.path.join(_MODS_DIR, "nlu.py"))
_res_mod  = _direct_import("modules.response_engine",
                            os.path.join(_MODS_DIR, "response_engine.py"))
_ht_mod   = _direct_import("modules.human_transfer",
                            os.path.join(_MODS_DIR, "human_transfer.py"))
_lrn_mod  = _direct_import("modules.learning",
                            os.path.join(_MODS_DIR, "learning.py"))

MLPredictor           = _ml_mod.MLPredictor
NLUModule             = _nlu_mod.NLUModule
DELEGATION_WILAYA_MAP = _nlu_mod.DELEGATION_WILAYA_MAP
ResponseEngine        = _res_mod.ResponseEngine
HumanTransfer         = _ht_mod.HumanTransfer

# ── Toutes les localisations tunisiennes (pour _localize_response) ──
_ALL_TUNISIAN_LOCS = sorted(
    set(DELEGATION_WILAYA_MAP.keys()) | set(DELEGATION_WILAYA_MAP.values()),
    key=len, reverse=True
)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("user_app")

# ══════════════════════════════════════════════════════════
#  INITIALISATION FIREBASE FIRESTORE
# ══════════════════════════════════════════════════════════
from firebase_config import (
    init_firebase,
    user_create, user_get_by_email, user_get_by_id,
    user_update_last_login, user_update_profile,
    conversation_create, conversation_get, conversation_update,
    conversations_get_by_user,
    message_add, messages_get_by_conversation,
    user_stats, reclamations_get_by_user,
)

logger.info("Connexion Firebase Firestore...")
_db_ok = init_firebase()
if not _db_ok:
    logger.critical("=" * 60)
    logger.critical("  ERREUR Firebase : vérifiez serviceAccountKey.json")
    logger.critical("  Voir firebase_config.py pour les instructions setup")
    logger.critical("=" * 60)

# ── Intégration Asterisk AMI (appels via WSL) ─────────────
from asterisk_ami import originate_call as _asterisk_call, check_asterisk_available
import subprocess, threading, time as _time

def _auto_start_asterisk():
    """
    Demarre Asterisk dans WSL automatiquement au lancement de user_app.py.
    Fonctionne avec networkingMode=mirrored (localhost:5038 direct, sans netsh).
    S'execute en arriere-plan pour ne pas retarder Flask.
    """
    def _wsl(cmd_list, timeout=30):
        """Lance une commande dans WSL et retourne (stdout+stderr, returncode)."""
        try:
            r = subprocess.run(
                ["wsl", "-u", "root", "--"] + cmd_list,
                capture_output=True, text=True, timeout=timeout
            )
            return (r.stdout + r.stderr).strip(), r.returncode
        except FileNotFoundError:
            return "WSL introuvable", -1
        except subprocess.TimeoutExpired:
            return "timeout", -2
        except Exception as e:
            return str(e), -3

    def _run():
        logger.info("[Asterisk] Demarrage automatique via WSL...")

        # 1. Verifier que WSL est accessible
        out, rc = _wsl(["echo", "wsl_ok"])
        if "wsl_ok" not in out:
            logger.warning(f"[Asterisk] WSL inaccessible : {out}")
            return

        # 2. Verifier si Asterisk est installe
        out, rc = _wsl(["which", "asterisk"])
        if rc != 0 or not out.strip():
            logger.warning(
                "[Asterisk] Asterisk non installe dans WSL. "
                "Lancez d'abord : wsl bash setup_asterisk_wsl.sh"
            )
            return

        # 3. Demarrer le service
        out, rc = _wsl(["service", "asterisk", "start"])
        logger.info(f"[Asterisk] service start -> {out or 'OK'} (rc={rc})")

        # 4. Attendre que le processus soit pret
        _time.sleep(4)

        # 5. Verifier que le processus tourne
        out, rc = _wsl(["pgrep", "-x", "asterisk"])
        if rc != 0:
            # Tentative de demarrage direct
            logger.warning("[Asterisk] Service ne repond pas, demarrage direct...")
            _wsl(["bash", "-c", "nohup asterisk -f > /tmp/ast.log 2>&1 &"])
            _time.sleep(5)
            out2, rc2 = _wsl(["pgrep", "-x", "asterisk"])
            if rc2 != 0:
                logger.error(
                    "[Asterisk] Impossible de demarrer Asterisk. "
                    "Lancez WSL et tapez : sudo service asterisk start"
                )
                return

        pid = out.strip().split("\n")[0]
        logger.info(f"[Asterisk] Asterisk actif (PID={pid})")

        # 6. Verifier AMI sur localhost (networkingMode=mirrored)
        # Avec mirrored networking, localhost:5038 est accessible directement
        for attempt in range(5):
            _time.sleep(2)
            status = check_asterisk_available()
            if status["available"]:
                logger.info(f"[Asterisk] AMI disponible sur {status['host']}:5038")
                return
            logger.debug(f"[Asterisk] AMI pas encore pret (tentative {attempt+1}/5)...")

        # Dernier essai : essayer l'IP WSL directement en fallback
        try:
            wsl_ip_out, _ = _wsl(["hostname", "-I"])
            ips = wsl_ip_out.strip().split()
            if ips:
                import socket as _sock
                for ip in ips:
                    try:
                        s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
                        s.settimeout(2)
                        s.connect((ip.strip(), 5038))
                        s.close()
                        logger.info(f"[Asterisk] AMI accessible via IP WSL directe : {ip}:5038")
                        return
                    except Exception:
                        pass
        except Exception:
            pass

        logger.warning(
            "[Asterisk] AMI non accessible apres demarrage. "
            "Verifiez /etc/asterisk/manager.conf dans WSL. "
            "Conseil : relancez setup_microsip.ps1 en Admin."
        )

    t = threading.Thread(target=_run, daemon=True, name="asterisk-autostart")
    t.start()

# ══════════════════════════════════════════════════════════
#  APPRENTISSAGE EPHEMERE (session uniquement — identique à app.py)
#  Oublié dès le redémarrage du serveur (in-memory uniquement).
# ══════════════════════════════════════════════════════════

# Store global partagé entre toutes les sessions user_app
# (oublié au redémarrage — comportement identique à app.py)
_global_learned_responses: list = []


def _session_learn_store(sess: dict, problem_text: str, response_text: str):
    """
    Stocke une réponse apprise à deux niveaux :
      1. Store global (_global_learned_responses) — partagé, oublié au restart
      2. Store session (sess["session_learned_responses"]) — compatibilité
    Identique à app.py _session_learn_store().
    """
    global _global_learned_responses

    entry = {
        "problem_text":  problem_text.strip(),
        "response_text": response_text.strip(),
        "embedding":     None,
    }

    # Tenter de calculer l'embedding si le modèle est disponible
    try:
        if response_eng.model is not None:
            entry["embedding"] = response_eng.model.encode([problem_text])[0]
            logger.info(f"[Learning] Embedding calculé pour '{problem_text[:50]}'")
    except Exception as _e:
        logger.warning(f"[Learning] Embedding échoué (texte seul) : {_e}")

    _global_learned_responses.append(entry)
    sess.setdefault("session_learned_responses", []).append(entry)
    logger.info(
        f"[Learning] Réponse mémorisée (total global: {len(_global_learned_responses)}) : "
        f"'{problem_text[:50]}' → '{response_text[:50]}'"
    )


def _find_session_learned(sess: dict, query_text: str):
    """
    Cherche si query_text correspond à un problème déjà résolu par un agent
    humain dans cette session (ou dans le store global de la session courante).
    Identique à app.py _find_session_learned_response().
    Retourne la réponse apprise ou None.
    """
    global _global_learned_responses

    learned = _global_learned_responses or sess.get("session_learned_responses", [])
    if not learned:
        return None

    logger.info(f"[Learning] Vérification : {len(learned)} réponse(s) pour '{query_text[:50]}'")

    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        has_numpy = False

    # Pré-calculer embedding de la requête
    q_emb = None
    try:
        if has_numpy and response_eng.model is not None:
            q_emb = response_eng.model.encode([query_text])[0]
    except Exception:
        pass

    best_score, best_resp = 0.0, None

    for entry in learned:
        problem = entry.get("problem_text", "").strip()
        resp    = entry.get("response_text", "")
        if not problem or not resp:
            continue

        score = 0.0

        # Couche 1 : correspondance exacte
        if query_text.strip() == problem:
            score = 1.0
        # Couche 2 : sous-chaîne
        elif problem in query_text or query_text in problem:
            score = 0.92
        else:
            # Couche 3 : recoupement de mots-clés
            q_words = set(w for w in query_text.split() if len(w) > 2)
            p_words = set(w for w in problem.split()    if len(w) > 2)
            common  = q_words & p_words
            if len(common) >= 2:
                kw_score = len(common) / max(len(q_words), len(p_words), 1)
                score = min(0.90, kw_score * 1.1)

            # Couche 4 : similarité cosinus
            if has_numpy and q_emb is not None:
                emb = entry.get("embedding")
                if emb is not None:
                    try:
                        import numpy as np
                        norm = (float(np.linalg.norm(q_emb)) *
                                float(np.linalg.norm(emb))) + 1e-9
                        cos  = float(np.dot(q_emb, emb)) / norm
                        if cos > score:
                            score = cos
                    except Exception:
                        pass

        if score > best_score:
            best_score = score
            best_resp  = resp

    MIN_SCORE = 0.62
    if best_score >= MIN_SCORE and best_resp:
        logger.info(f"[Learning] Réponse trouvée (score={best_score:.3f}) pour '{query_text[:50]}'")
        return best_resp

    return None


# Démarrage automatique Asterisk dès le lancement de user_app.py
_auto_start_asterisk()

# ── Flask app ─────────────────────────────────────────────
app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.secret_key = "tt_user_espace_2026"
app.config["JSON_AS_ASCII"] = False

# ── Chargement modules bot ────────────────────────────────
logger.info("Chargement modules bot...")
ml_predictor = MLPredictor(Config)
nlu          = NLUModule(Config, ml_predictor=ml_predictor)
response_eng = ResponseEngine(Config)
transfer     = HumanTransfer(Config)
logger.info(f"ML Backend : {ml_predictor.backend_name}")

# ── État des conversations en mémoire (par session_id) ────
user_conv_state: dict = {}


# ══════════════════════════════════════════════════════════
#  HELPERS AUTHENTIFICATION
# ══════════════════════════════════════════════════════════

def login_required(f):
    """Décorateur : redirige vers login si non connecté ou session invalide."""
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if uid is None:
            return redirect(url_for("login"))
        # Ancien user_id MySQL (entier) → session invalide → re-login
        if isinstance(uid, int) or (isinstance(uid, str) and uid.isdigit()):
            session.clear()
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Retourne les infos de l'utilisateur connecté depuis Firebase."""
    if "user_id" not in session:
        return None
    uid = session["user_id"]
    # Vider la session si c'est un ancien user_id MySQL (entier)
    if isinstance(uid, int) or (isinstance(uid, str) and uid.isdigit()):
        session.clear()
        return None
    return user_get_by_id(uid)


# ══════════════════════════════════════════════════════════
#  HELPERS BOT (reproduction fidèle de app.py, côté user)
# ══════════════════════════════════════════════════════════

def _get_conv_state(conv_session_id: str) -> dict:
    if conv_session_id not in user_conv_state:
        user_conv_state[conv_session_id] = {
            "stage": "waiting_greeting",
            "turn":  0,
            "history": [],
            "collected_entities": {},
            "pending_intent": "",
            "original_problem": "",
            "solution_given": False,
            "transferred": False,
            "last_transferred_problem": "",   # problème qui a déclenché le dernier transfert
            "session_learned_responses": [],  # réponses apprises dans cette session (éphémères)
        }
    return user_conv_state[conv_session_id]


def _is_greeting(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in Config.GREETING_KEYWORDS)


def _is_thanks(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in Config.THANKS_KEYWORDS)


def _is_stop(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in Config.STOP_KEYWORDS)


def _is_negation(text: str) -> bool:
    t = text.lower().strip()
    # Vérifier affirmation d'abord
    if any(kw in t for kw in Config.AFFIRMATION_KEYWORDS):
        return False
    for kw in Config.NEGATION_KEYWORDS:
        if len(kw) <= 3:
            if re.search(r'\b' + re.escape(kw) + r'\b', t):
                return True
        else:
            if kw in t:
                return True
    return False


def _update_entities(sess: dict, nlu_result: dict):
    ents = nlu_result.get("entities", {})
    collected = sess.setdefault("collected_entities", {})
    for k, v in ents.items():
        if v:
            collected[k] = v


def _needs_delegation(entities: dict) -> bool:
    if not entities:
        return False
    wilaya = entities.get("wilaya", "")
    deleg  = entities.get("delegation", "")
    return bool(wilaya) and not bool(deleg)


def _localize_response(text: str, entities: dict) -> str:
    if not entities or not text:
        return text
    loc = entities.get("delegation") or entities.get("wilaya", "")
    if not loc:
        return text
    for placeholder in ["[المنطقة]", "[الولاية]", "[المعتمدية]",
                        "المنطقة المحددة", "منطقتك"]:
        text = text.replace(placeholder, loc)
    return text




# ══════════════════════════════════════════════════════════
#  LOGIQUE CHAT PRINCIPALE
# ══════════════════════════════════════════════════════════

def _build_enriched_query(sess: dict, current_text: str) -> str:
    """
    Construit la requête RAG pour l'étape 2.
    Même logique que app.py : problème original + réponse clarification.
    """
    original = sess.get("original_problem", "")
    if original and original != current_text:
        combined = f"{original} {current_text}".strip()
    else:
        history    = sess.get("history", [])
        user_turns = [t for r, t in history if r == "user"]
        combined   = " ".join(user_turns[-3:]).strip()
    return combined or current_text


def process_user_message(conv_session_id: str, user_text: str) -> dict:
    """
    Traite un message utilisateur et retourne la réponse du bot.
    Même logique que app.py mais sans retourner les détails NLU.
    """
    sess  = _get_conv_state(conv_session_id)
    stage = sess.get("stage", "waiting_greeting")

    # ── Salutation ────────────────────────────────────────
    if stage == "waiting_greeting":
        sess["history"].append(("user", user_text))
        if _is_greeting(user_text):
            bot_resp = Config.GREETING_MESSAGE
            sess["history"].append(("bot", bot_resp))
            sess["stage"] = "initial"
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours"}
        else:
            hint = "مرحبا! قبل ما نبداو، قولي عسلامة"
            sess["history"].append(("bot", hint))
            return {"bot_response": hint, "session_ended": False,
                    "transferred": False, "statut": "en_cours"}

    # ── Remerciement ──────────────────────────────────────
    if _is_thanks(user_text) and sess.get("solution_given"):
        sess["history"].append(("user", user_text))
        bot_resp = Config.THANKS_MESSAGE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "waiting_greeting"
        sess["solution_given"] = False
        return {"bot_response": bot_resp, "session_ended": True,
                "transferred": False, "statut": "resolue"}

    # ── Arrêt ────────────────────────────────────────────
    if _is_stop(user_text):
        sess["history"].append(("user", user_text))
        bot_resp = Config.FAREWELL_MESSAGE
        sess["history"].append(("bot", bot_resp))
        return {"bot_response": bot_resp, "session_ended": True,
                "transferred": False, "statut": "fermee"}

    sess["turn"] += 1
    sess["history"].append(("user", user_text))

    # ── NLU ───────────────────────────────────────────────
    nlu_result   = nlu.analyze(user_text)
    intent       = nlu_result.get("intent", "")
    ml_conf      = nlu_result.get("confidence", 0)
    service_type = nlu_result.get("entities", {}).get("service_type", "")
    _update_entities(sess, nlu_result)
    # Stocker le dernier résultat NLU dans la session pour le chat endpoint
    sess["last_nlu"] = {
        "intent":       intent,
        "confidence":   round(float(ml_conf) * 100) if ml_conf <= 1 else int(ml_conf),
        "sentiment":    nlu_result.get("sentiment", ""),
        "service_type": service_type,
    }

    # ── active_intent : intent du RECORD (fiable) ou NLU sinon ───
    active_intent = sess.get("pending_intent") or intent

    # ── Numéro de demande demandé → transfert immédiat ────
    if stage == "waiting_for_request_number":
        sess["transferred"] = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=0)
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    # ── ÉTAPE 1 : Poser une question de clarification ─────
    if stage == "initial":
        # ── Apprentissage éphémère : vérifier si ce problème a déjà été
        # résolu par un agent humain dans cette session ou dans la session courante ──
        _learned_resp = _find_session_learned(sess, user_text)
        if _learned_resp:
            bot_resp = _localize_response(_learned_resp, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["solution_given"] = True
            logger.info(f"[{conv_session_id}] Réponse apprise (session learning) utilisée")
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "resolue",
                    "sujet": active_intent, "service_type": service_type}

        clari = response_eng.find_clarification_question(
            user_text, nlu_intent=intent, nlu_service=service_type
        )
        CLARI_MIN_CONF     = Config.CLARIFICATION_CONFIDENCE_THRESHOLD
        NLU_MIN_CONF_CLARI = Config.NLU_MIN_CONFIDENCE_FOR_CLARI

        clari_ok = (
            clari["question"]
            and clari["confidence"] >= CLARI_MIN_CONF
            and ml_conf >= NLU_MIN_CONF_CLARI
        )

        if clari_ok:
            bot_resp = response_eng._strip_emojis(clari["question"])
            if _needs_delegation(sess.get("collected_entities")):
                w = sess["collected_entities"].get("wilaya", "")
                bot_resp += "  " + Config.DELEGATION_QUESTION.format(wilaya=w)
            sess["stage"]            = "clarifying"
            sess["pending_intent"]   = clari.get("intent") or intent
            sess["original_problem"] = user_text
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": intent, "service_type": service_type}

        # Problème non reconnu → transfert
        intent_unknown  = intent in ("غير محدد", "unknown", "")
        rag_gate_failed = not clari["question"]
        if intent_unknown and rag_gate_failed:
            bot_resp = Config.TRANSFER_MESSAGE
            transfer.create_ticket(session_id=conv_session_id,
                                   history=sess["history"],
                                   user_last_text=user_text,
                                   nlu_result=nlu_result,
                                   rag_confidence=clari["confidence"])
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["transferred"]    = True
            sess["last_transferred_problem"] = sess.get("original_problem") or user_text
            sess["solution_given"] = True
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": True, "statut": "transferee"}

        if clari["confidence"] < CLARI_MIN_CONF:
            bot_resp = Config.TRANSFER_MESSAGE
            transfer.create_ticket(session_id=conv_session_id,
                                   history=sess["history"],
                                   user_last_text=user_text,
                                   nlu_result=nlu_result,
                                   rag_confidence=clari["confidence"])
            sess["history"].append(("bot", bot_resp))
            sess["transferred"]    = True
            sess["last_transferred_problem"] = sess.get("original_problem") or user_text
            sess["solution_given"] = True
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": True, "statut": "transferee"}

        # NLU bas mais clari trouvée → passer direct à l'étape 2 (seuil strict)
        sess["stage"]            = "responding"
        sess["pending_intent"]   = clari.get("intent") or intent
        sess["original_problem"] = user_text

    # ── Négation sur clarification ────────────────────────
    if stage == "clarifying" and _is_negation(user_text):
        bot_resp = Config.NEGATION_CLARIFICATION_RESPONSE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": False, "statut": "resolue"}

    # ── ÉTAPE 2 : Réponse finale (clarifying ou responding) ─
    enriched_query = _build_enriched_query(sess, user_text)
    rag_result     = response_eng.find_response(
        enriched_query,
        sess["history"],
        nlu_intent=active_intent
    )

    rag_conf     = rag_result.get("confidence", 0)
    rag_escalate = rag_result.get("escalate", False)

    # Seuils stricts selon le stage
    current_stage = sess.get("stage")
    if current_stage == "responding":
        NLU_MIN_CONF_CLARI = Config.NLU_MIN_CONFIDENCE_FOR_CLARI
        if ml_conf < NLU_MIN_CONF_CLARI:
            strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_LOW_NLU", 0.70)
        else:
            strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD", 0.45)
        if rag_conf < strict_threshold:
            rag_escalate = True
    elif current_stage == "clarifying":
        strict_threshold = getattr(Config, "RAG_STRICT_THRESHOLD_AFTER_CLARI", 0.60)
        if rag_conf < strict_threshold:
            rag_escalate = True

    if rag_escalate:
        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=rag_conf)
        sess["history"].append(("bot", bot_resp))
        sess["transferred"]    = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or ""
    if not bot_resp:
        bot_resp = Config.NOT_UNDERSTOOD_MSG

    bot_resp = response_eng._strip_emojis(
        _localize_response(bot_resp, sess.get("collected_entities"))
    )

    # Détection de boucle : éviter de répéter la même réponse
    last_bot = next(
        (t for role, t in reversed(sess.get("history", [])) if role == "bot"), ""
    )
    if last_bot and bot_resp.strip() == last_bot.strip():
        sess["transferred"] = True
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=rag_conf)
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    sess["history"].append(("bot", bot_resp))

    if "اعطيني رقم المطلب" in bot_resp:
        sess["stage"] = "waiting_for_request_number"
    else:
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True

    return {"bot_response": bot_resp, "session_ended": False,
            "transferred": False, "statut": "resolue",
            "sujet": active_intent, "service_type": service_type}


# ══════════════════════════════════════════════════════════
#  ROUTES AUTHENTIFICATION
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = user_get_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]    = user["id"]
            session["user_nom"]   = user["nom"]
            session["user_prenom"] = user["prenom"]
            user_update_last_login(user["id"])
            return redirect(url_for("dashboard"))
        else:
            error = "Email ou mot de passe incorrect."

    return render_template("user_login.html", error=error, mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        nom       = request.form.get("nom", "").strip()
        prenom    = request.form.get("prenom", "").strip()
        email     = request.form.get("email", "").strip().lower()
        telephone = request.form.get("telephone", "").strip()
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")

        # Validations
        if not all([nom, prenom, email, telephone, password]):
            error = "Tous les champs sont obligatoires."
        elif password != confirm:
            error = "Les mots de passe ne correspondent pas."
        elif len(password) < 6:
            error = "Le mot de passe doit contenir au moins 6 caractères."
        else:
            # Vérifier email unique dans Firebase
            existing = user_get_by_email(email)
            if existing:
                error = "Cet email est déjà utilisé."
            else:
                pwd_hash = generate_password_hash(password)
                colors   = ["#6B2FA0", "#00B4D8", "#E8002D", "#1B5E20", "#1565C0"]
                color    = colors[hash(email) % len(colors)]
                user_id  = user_create(nom, prenom, email, pwd_hash, telephone, color)
                session["user_id"]    = user_id
                session["user_nom"]   = nom
                session["user_prenom"] = prenom
                return redirect(url_for("dashboard"))

    return render_template("user_login.html", error=error, mode="register")


@app.route("/logout")
def logout():
    # Nettoyer les états de conversation
    user_id = session.get("user_id")
    session.clear()
    return redirect(url_for("login"))


# ══════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    return render_template("user_dashboard.html", user=user)


# ══════════════════════════════════════════════════════════
#  API CHAT
# ══════════════════════════════════════════════════════════

@app.route("/api/user/chat", methods=["POST"])
@login_required
def api_chat():
    data       = request.get_json()
    user_text  = (data.get("message") or "").strip()
    conv_id_db = data.get("conversation_id")   # ID Firebase de la conversation

    if not user_text:
        return jsonify({"error": "Message vide"}), 400

    user_id = session["user_id"]

    # ── Récupérer ou créer la conversation dans Firebase ──
    conv = None
    if conv_id_db:
        conv = conversation_get(conv_id_db)
        # Vérifier que la conversation appartient bien à cet user
        if conv and conv.get("user_id") != user_id:
            conv = None

    if not conv:
        # Nouvelle conversation — l'ID Firebase sert de session_id bot
        conv_id_db = conversation_create(user_id)
        conv = {"id": conv_id_db, "user_id": user_id,
                "statut": "en_cours", "sujet": "", "service_type": ""}

    # L'ID Firebase de la conversation est utilisé comme clé d'état bot
    session_id = conv_id_db

    # ── Sauvegarder le message utilisateur (NLU ajouté après traitement) ──
    # Le message est sauvegardé d'abord sans NLU, puis mis à jour après
    # le traitement bot (pour avoir les données NLU disponibles).
    # Alternative simple : sauvegarder après process_user_message.

    # ── Traitement bot ────────────────────────────────────
    try:
        result = process_user_message(session_id, user_text)
    except Exception as e:
        logger.error(f"Erreur bot : {e}", exc_info=True)
        result = {"bot_response": Config.NOT_UNDERSTOOD_MSG,
                  "session_ended": False, "transferred": False,
                  "statut": "en_cours"}

    bot_resp = result["bot_response"]

    # ── Récupérer le résultat NLU stocké par process_user_message ──
    _sess_state = user_conv_state.get(session_id, {})
    _nlu_data   = _sess_state.get("last_nlu", None)

    # ── Sauvegarder le message utilisateur (avec NLU si disponible) ──
    message_add(conv_id_db, user_id, "user", user_text, nlu_data=_nlu_data)

    # ── Sauvegarder la réponse bot ────────────────────────
    message_add(conv_id_db, user_id, "bot", bot_resp)

    # ── Mettre à jour la conversation Firebase ───────────
    new_statut  = result.get("statut", "en_cours")
    new_sujet   = result.get("sujet")   or conv.get("sujet",        "")
    new_service = result.get("service_type") or conv.get("service_type", "")

    conversation_update(conv_id_db,
                        statut=new_statut,
                        sujet=new_sujet,
                        service_type=new_service)

    # ── Transfert vers agent humain → appel Asterisk ─────
    ami_called         = False
    asterisk_available = False
    ami_reason         = ""          # Explication lisible pour le badge JS

    if result.get("transferred"):
        user_info = get_current_user() or {}
        phone     = (user_info.get("telephone") or "").strip()
        u_name    = f"{user_info.get('prenom','')} {user_info.get('nom','')}".strip()
        ticket_id = conv_id_db[:8]

        logger.info(
            f"[Asterisk] Transfert detecte — user={session.get('user_id')} "
            f"phone='{phone}' name='{u_name}'"
        )

        # Récupérer le texte du problème qui a déclenché le transfert
        _transfer_sess = user_conv_state.get(session_id, {})
        problem_text   = _transfer_sess.get("last_transferred_problem", "")

        # Stocker le problème dans Firebase pour que le back-office puisse l'afficher
        if problem_text:
            try:
                conversation_update(conv_id_db, last_problem=problem_text)
            except Exception as _cp_err:
                logger.warning(f"[Asterisk] Echec stockage last_problem : {_cp_err}")

        if not phone:
            # Pas de numero → pas d'appel, pas besoin de tester l'AMI
            ami_reason         = "no_phone"
            asterisk_available = False
            logger.warning(
                f"[Asterisk] Transfert ignore : numero manquant pour "
                f"user {session.get('user_id')}"
            )
        else:
            # Appel direct — originate_call() fait lui-meme le check AMI
            # (evite la double-connexion TCP qui perturbait le banner Asterisk)
            ami_result         = _asterisk_call(
                caller_number=phone,
                ticket_id=ticket_id,
                user_name=u_name,
                problem_text=problem_text,
            )
            ami_called         = ami_result.get("success", False)
            asterisk_available = ami_called   # True seulement si l'AMI a repondu

            if ami_called:
                ami_reason = "ok"
            else:
                msg = ami_result.get("message", "").lower()
                ami_reason = (
                    "no_phone"   if "manquant" in msg or "phone" in msg
                    else "ami_down"
                )
            logger.info(f"[Asterisk] {ami_result.get('message', str(ami_result))}")

    return jsonify({
        "bot_response":       bot_resp,
        "conversation_id":    conv_id_db,
        "session_ended":      result.get("session_ended", False),
        "transferred":        result.get("transferred", False),
        "ami_called":         ami_called,          # True si appel Asterisk initie
        "asterisk_available": asterisk_available,  # Etat AMI au moment du transfert
        "ami_reason":         ami_reason,          # 'ok'|'no_phone'|'ami_down'|'originate_failed'
        "statut":             new_statut,
    })


# ══════════════════════════════════════════════════════════
#  API RÉPONSE AGENT HUMAIN — apprentissage de session
# ══════════════════════════════════════════════════════════

@app.route("/api/user/human_response", methods=["POST"])
@login_required
def api_user_human_response():
    """
    Reçoit la réponse fournie par l'agent humain après un transfert.
    Stocke la réponse dans la mémoire éphémère de session (_global_learned_responses)
    afin que le bot puisse l'utiliser lors des prochaines interactions.

    Body JSON :
        ticket_id  : identifiant du ticket créé lors du transfert
        response   : texte de la réponse de l'agent
        session_id : identifiant de la session de conversation (conv_session_id)
    """
    data      = request.get_json(silent=True) or {}
    ticket_id = data.get("ticket_id", "")
    response  = (data.get("response") or "").strip()
    sid       = data.get("session_id", "")

    if not response:
        return jsonify({"error": "Réponse vide"}), 400

    # Résoudre le ticket côté Firestore
    try:
        transfer.resolve_ticket(ticket_id, response)
    except Exception as e:
        logger.warning(f"[human_response] Erreur resolve_ticket({ticket_id}) : {e}")

    # Récupérer la session de conversation
    sess = user_conv_state.get(sid, {})

    # Déterminer le texte du problème (ce qui avait déclenché le transfert)
    history      = sess.get("history", [])
    last_user    = next((t for r, t in reversed(history) if r == "user"), "")
    problem_text = sess.get("last_transferred_problem") or last_user

    # Stocker la réponse dans la mémoire éphémère
    learned = False
    if problem_text:
        _session_learn_store(sess, problem_text, response)
        learned = True
        logger.info(
            f"[human_response] Appris : '{problem_text[:60]}' → '{response[:60]}'"
        )

    # Remettre la session en état initial pour que l'utilisateur puisse continuer
    sess["solution_given"]           = False
    sess["transferred"]              = False
    sess["stage"]                    = "initial"
    sess["pending_intent"]           = ""
    sess["last_transferred_problem"] = ""

    return jsonify({"success": True, "learned": learned})


# ══════════════════════════════════════════════════════════
#  API INTERNE — Réponse agent (appelée par app.py back-office)
#  Pas de login_required : accès par secret interne uniquement
# ══════════════════════════════════════════════════════════

_INTERNAL_SECRET = "tt_backoffice_2026"   # partagé avec app.py

@app.route("/api/internal/agent_reply", methods=["POST"])
def api_internal_agent_reply():
    """
    Endpoint interne (non authentifié) pour recevoir la réponse de l'agent
    humain depuis le back-office app.py.
    Vérifie le header X-Internal-Secret avant traitement.

    Body JSON :
        ticket_id  : identifiant Firebase de la conversation
        response   : texte de la réponse de l'agent
        session_id : identifiant de la session (= conv_id Firebase)
    """
    # Vérification secret interne
    if request.headers.get("X-Internal-Secret") != _INTERNAL_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data      = request.get_json(silent=True) or {}
    ticket_id = data.get("ticket_id", "")
    response  = (data.get("response") or "").strip()
    sid       = data.get("session_id", "")

    if not response:
        return jsonify({"error": "Réponse vide"}), 400

    # Résoudre le ticket côté Firestore
    try:
        transfer.resolve_ticket(ticket_id, response)
    except Exception as e:
        logger.warning(f"[internal_agent_reply] Erreur resolve_ticket({ticket_id}) : {e}")

    # Récupérer la session de conversation en mémoire
    sess = user_conv_state.get(sid, {})

    # Déterminer le texte du problème
    history      = sess.get("history", [])
    last_user    = next((t for r, t in reversed(history) if r == "user"), "")
    problem_text = sess.get("last_transferred_problem") or last_user

    # Stocker la réponse apprise en mémoire éphémère
    learned = False
    if problem_text:
        _session_learn_store(sess, problem_text, response)
        learned = True
        logger.info(
            f"[internal_agent_reply] Appris : '{problem_text[:60]}' → '{response[:60]}'"
        )
    else:
        logger.info(
            f"[internal_agent_reply] Session {sid!r} introuvable en mémoire — "
            "réponse stockée dans le store global uniquement"
        )
        # Même si la session n'est plus en mémoire, stocker dans le store global
        _session_learn_store({}, ticket_id or "unknown", response)
        learned = True

    # Remettre la session en état initial
    if sess:
        sess["solution_given"]           = False
        sess["transferred"]              = False
        sess["stage"]                    = "initial"
        sess["pending_intent"]           = ""
        sess["last_transferred_problem"] = ""

    # Mettre à jour le statut Firebase
    try:
        conversation_update(ticket_id, statut="resolue")
    except Exception as _e:
        logger.warning(f"[internal_agent_reply] Echec mise à jour statut : {_e}")

    return jsonify({"success": True, "learned": learned, "session_found": bool(sess)})


# ══════════════════════════════════════════════════════════
#  API HISTORIQUE
# ══════════════════════════════════════════════════════════

@app.route("/api/user/history")
@login_required
def api_history():
    try:
        user_id = session["user_id"]
        reclamations = reclamations_get_by_user(user_id, limit=50)
        return jsonify({"reclamations": reclamations})
    except Exception as e:
        logger.error(f"[api_history] Erreur Firebase : {e}", exc_info=True)
        return jsonify({"reclamations": [], "error": str(e)}), 500


@app.route("/api/user/conversation/<conv_id>")
@login_required
def api_conversation_detail(conv_id):
    try:
        user_id = session["user_id"]

        conv = conversation_get(conv_id)
        if not conv or conv.get("user_id") != user_id:
            return jsonify({"error": "Non trouvé"}), 404

        msgs_raw = messages_get_by_conversation(conv_id)

        messages = []
        for m in msgs_raw:
            created = m.get("created_at")
            ts = ""
            if hasattr(created, "strftime"):
                ts = created.strftime("%d/%m/%Y %H:%M:%S")
            elif created:
                ts = str(created)
            messages.append({
                "role":      m.get("role", ""),
                "content":   m.get("content", ""),
                "timestamp": ts,
            })

        # Sérialiser les dates de la conversation
        c = dict(conv)
        for field in ("created_at", "updated_at"):
            v = c.get(field)
            if hasattr(v, "strftime"):
                c[field] = v.strftime("%d/%m/%Y %H:%M")
            elif v:
                c[field] = str(v)

        return jsonify({"conversation": c, "messages": messages})
    except Exception as e:
        logger.error(f"[api_conversation_detail] Erreur Firebase : {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/new_conversation", methods=["POST"])
@login_required
def api_new_conversation():
    user_id = session["user_id"]
    conv_id = conversation_create(user_id)

    # Réinitialiser l'état mémoire du bot pour cette conversation
    if conv_id in user_conv_state:
        del user_conv_state[conv_id]

    return jsonify({"conversation_id": conv_id})


@app.route("/api/user/profile")
@login_required
def api_profile():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Non trouvé"}), 404
    u = dict(user)
    created = u.get("created_at")
    if hasattr(created, "strftime"):
        u["created_at"] = created.strftime("%d/%m/%Y")
    elif created:
        u["created_at"] = str(created)
    return jsonify({"user": u})


@app.route("/api/user/stats")
@login_required
def api_stats():
    try:
        stats = user_stats(session["user_id"])
        return jsonify(stats)
    except Exception as e:
        logger.error(f"[api_stats] Erreur Firebase : {e}", exc_info=True)
        return jsonify({"total": 0, "resolues": 0, "transferees": 0, "en_cours": 0, "error": str(e)}), 500


@app.route("/api/user/asterisk_status")
@login_required
def api_asterisk_status():
    """Vérifie si Asterisk est disponible (pour l'interface admin/debug)."""
    status = check_asterisk_available()
    return jsonify(status)


@app.route("/api/user/ami_debug")
@login_required
def api_ami_debug():
    """
    Endpoint de diagnostic complet AMI + profil utilisateur.
    Ouvrir dans le navigateur : http://localhost:5001/api/user/ami_debug
    Montre exactement pourquoi l'appel AMI echoue ou reussit.
    """
    from asterisk_ami import get_wsl_ip
    import socket

    user_info = get_current_user() or {}
    phone     = (user_info.get("telephone") or "").strip()
    u_name    = f"{user_info.get('prenom','')} {user_info.get('nom','')}".strip()

    ami_host  = get_wsl_ip()
    ami_port  = 5038

    # Test 1 : connexion TCP port 5038
    tcp_ok    = False
    tcp_error = ""
    banner    = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((ami_host, ami_port))
        banner = s.recv(256).decode(errors="replace").strip()
        s.close()
        tcp_ok = True
    except Exception as e:
        tcp_error = str(e)

    # Test 2 : login AMI
    ami_login_ok    = False
    ami_login_error = ""
    if tcp_ok:
        try:
            from asterisk_ami import AmiClient, AMI_USER, AMI_SECRET
            with AmiClient(ami_host) as ami:
                ami_login_ok = ami.connect()
                if not ami_login_ok:
                    ami_login_error = "Login refusé (vérifiez manager.conf)"
        except Exception as e:
            ami_login_error = str(e)

    return jsonify({
        "user": {
            "id":        session.get("user_id", "?"),
            "name":      u_name or "—",
            "telephone": phone or "MANQUANT — profil sans numéro !",
            "phone_ok":  bool(phone),
        },
        "asterisk": {
            "wsl_ip":        ami_host,
            "ami_port":      ami_port,
            "tcp_reachable": tcp_ok,
            "tcp_error":     tcp_error or None,
            "ami_banner":    banner or None,
            "login_ok":      ami_login_ok,
            "login_error":   ami_login_error or None,
        },
        "conclusion": (
            "✅ Tout est OK — l'appel devrait fonctionner"
            if (tcp_ok and ami_login_ok and phone)
            else (
                "❌ Numéro de téléphone MANQUANT dans le profil Firebase"
                if not phone
                else (
                    "❌ Port AMI 5038 inaccessible — Asterisk ne tourne pas dans WSL"
                    if not tcp_ok
                    else "❌ Login AMI échoué — vérifiez manager.conf (ttadmin / TT@2026)"
                )
            )
        ),
    })


# ══════════════════════════════════════════════════════════
#  API VOCAL — STT (Speech-to-Text via Whisper)
# ══════════════════════════════════════════════════════════

# Modèle Whisper chargé une seule fois (lazy)
_whisper_model = None

def _get_whisper():
    """Charge le modèle Whisper une seule fois."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info(f"Chargement Whisper '{Config.STT_MODEL}'…")
        _whisper_model = WhisperModel(
            Config.STT_MODEL,
            device=Config.STT_DEVICE,
            compute_type="int8",
        )
        logger.info("Whisper chargé.")
    return _whisper_model


@app.route("/api/user/stt", methods=["POST"])
@login_required
def api_stt():
    """
    Reçoit un fichier audio (WebM/WAV/MP4) depuis le navigateur,
    le transcrit avec Whisper et renvoie le texte.
    """
    if "audio" not in request.files:
        return jsonify({"error": "Fichier audio manquant"}), 400

    audio_file = request.files["audio"]
    suffix = ".webm"
    ct = audio_file.content_type or ""
    if "wav"  in ct: suffix = ".wav"
    elif "mp4" in ct or "mp4a" in ct: suffix = ".mp4"
    elif "ogg" in ct: suffix = ".ogg"

    tmp_path = None
    try:
        # Sauvegarder dans un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        model = _get_whisper()
        segments, _ = model.transcribe(
            tmp_path,
            language=Config.STT_LANGUAGE,
            beam_size=Config.STT_BEAM_SIZE,
            vad_filter=Config.STT_VAD_FILTER,
            initial_prompt=Config.STT_INITIAL_PROMPT,
        )
        text = " ".join(seg.text for seg in segments).strip()
        logger.info(f"[STT] Transcription : '{text[:80]}'")
        return jsonify({"text": text})

    except ImportError:
        logger.warning("faster-whisper non installé → STT indisponible")
        return jsonify({"error": "STT non disponible", "fallback": True}), 503
    except Exception as e:
        logger.error(f"[STT] Erreur : {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except: pass


# ══════════════════════════════════════════════════════════
#  API VOCAL — TTS (Text-to-Speech via edge-tts)
# ══════════════════════════════════════════════════════════

async def _tts_generate_async(text: str, voice: str) -> bytes:
    """Génère l'audio TTS via edge-tts (async)."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return audio_data


def _tts_generate(text: str, voice: str) -> bytes:
    """Wrapper synchrone pour edge-tts."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_tts_generate_async(text, voice))
    finally:
        loop.close()


@app.route("/api/user/tts", methods=["POST"])
@login_required
def api_tts():
    """
    Reçoit du texte, génère l'audio TTS (edge-tts)
    et le renvoie comme fichier audio/mpeg.
    """
    data  = request.get_json()
    text  = (data.get("text") or "").strip()
    voice = data.get("voice") or Config.EDGE_TTS_VOICE

    if not text:
        return jsonify({"error": "Texte vide"}), 400

    try:
        audio_bytes = _tts_generate(text, voice)
        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=False,
            download_name="response.mp3",
        )
    except ImportError:
        logger.warning("edge-tts non installé → TTS indisponible")
        return jsonify({"error": "TTS non disponible"}), 503
    except Exception as e:
        logger.error(f"[TTS] Erreur : {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/check_capabilities")
@login_required
def api_check_capabilities():
    """Vérifie quelles capacités vocales sont disponibles côté serveur."""
    stt_ok = False
    tts_ok = False
    try:
        import faster_whisper
        stt_ok = True
    except ImportError:
        pass
    try:
        import edge_tts
        tts_ok = True
    except ImportError:
        pass
    return jsonify({"stt": stt_ok, "tts": tts_ok})


# ══════════════════════════════════════════════════════════
#  LANCEMENT
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  Espace Client TT — http://localhost:5001")
    logger.info("=" * 55)
    app.run(host="0.0.0.0", port=5001, debug=False)
