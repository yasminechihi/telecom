#!/usr/bin/env python3
# ============================================================
#  user_app.py — Interface Espace Client Tunisie Telecom
#  Flask app séparée (port 5001) — Ne touche PAS à app.py
#
#  Fonctionnalités :
#    - Authentification : Sign In / Sign Up (MySQL EasyPHP)
#    - Chat avec le bot (même logique que app.py, sans détails NLU)
#    - Dashboard : historique des réclamations par client
#    - Design Tunisie Telecom (violet, blanc)
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
#  INITIALISATION BASE DE DONNÉES (création auto des tables)
# ══════════════════════════════════════════════════════════
from db_config import db_execute, init_db

logger.info("Initialisation base de données MySQL...")
_db_ok = init_db()
if not _db_ok:
    logger.critical("=" * 55)
    logger.critical("  ERREUR MySQL : vérifiez que EasyPHP est démarré")
    logger.critical("  et que le serveur MySQL tourne sur localhost:3306")
    logger.critical("=" * 55)

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
    """Décorateur : redirige vers login si non connecté."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Retourne les infos de l'utilisateur connecté."""
    if "user_id" not in session:
        return None
    return db_execute(
        "SELECT id, nom, prenom, email, telephone, avatar_color, created_at "
        "FROM users WHERE id = %s AND is_active = 1",
        (session["user_id"],), fetchone=True
    )


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
            "last_transferred_problem": "",
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


def _find_session_learned(sess: dict, user_text: str):
    """Cherche si un agent humain a déjà résolu ce problème dans la session."""
    if not sess.get("transferred"):
        return None
    return None  # Simplifié pour l'interface user


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

    # ── active_intent : intent du RECORD (fiable) ou NLU sinon ───
    active_intent = sess.get("pending_intent") or intent

    # ── Numéro de demande demandé → transfert immédiat ────
    if stage == "waiting_for_request_number":
        sess["transferred"] = True
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

        user = db_execute(
            "SELECT * FROM users WHERE email = %s AND is_active = 1",
            (email,), fetchone=True
        )
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]   = user["id"]
            session["user_nom"]  = user["nom"]
            session["user_prenom"] = user["prenom"]
            # Mettre à jour last_login
            db_execute(
                "UPDATE users SET last_login = NOW() WHERE id = %s",
                (user["id"],)
            )
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
            # Vérifier email unique
            existing = db_execute(
                "SELECT id FROM users WHERE email = %s", (email,), fetchone=True
            )
            if existing:
                error = "Cet email est déjà utilisé."
            else:
                pwd_hash = generate_password_hash(password)
                # Couleur avatar aléatoire parmi la palette TT
                colors   = ["#6B2FA0", "#00B4D8", "#E8002D", "#1B5E20", "#1565C0"]
                color    = colors[hash(email) % len(colors)]
                user_id  = db_execute(
                    "INSERT INTO users (nom, prenom, email, telephone, "
                    "password_hash, avatar_color) VALUES (%s,%s,%s,%s,%s,%s)",
                    (nom, prenom, email, telephone, pwd_hash, color),
                    lastrowid=True
                )
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
    data      = request.get_json()
    user_text = (data.get("message") or "").strip()
    conv_id_db = data.get("conversation_id")   # ID DB de la conversation

    if not user_text:
        return jsonify({"error": "Message vide"}), 400

    user_id = session["user_id"]

    # ── Récupérer ou créer la conversation en DB ──────────
    if conv_id_db:
        conv = db_execute(
            "SELECT * FROM conversations WHERE id = %s AND user_id = %s",
            (conv_id_db, user_id), fetchone=True
        )
    else:
        conv = None

    if not conv:
        # Nouvelle conversation
        new_session_id = str(uuid.uuid4())
        conv_id_db = db_execute(
            "INSERT INTO conversations (user_id, session_id, statut) "
            "VALUES (%s, %s, 'en_cours')",
            (user_id, new_session_id), lastrowid=True
        )
        conv = {"id": conv_id_db, "session_id": new_session_id,
                "statut": "en_cours", "sujet": None}

    session_id = conv["session_id"]

    # ── Sauvegarder message user ──────────────────────────
    db_execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
        (conv_id_db, "user", user_text), lastrowid=True
    )

    # ── Traitement bot ────────────────────────────────────
    try:
        result = process_user_message(session_id, user_text)
    except Exception as e:
        logger.error(f"Erreur bot : {e}", exc_info=True)
        result = {"bot_response": Config.NOT_UNDERSTOOD_MSG,
                  "session_ended": False, "transferred": False,
                  "statut": "en_cours"}

    bot_resp = result["bot_response"]

    # ── Sauvegarder réponse bot ───────────────────────────
    db_execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
        (conv_id_db, "bot", bot_resp), lastrowid=True
    )

    # ── Mettre à jour la conversation ────────────────────
    new_statut  = result.get("statut", "en_cours")
    new_sujet   = result.get("sujet") or conv.get("sujet")
    new_service = result.get("service_type") or conv.get("service_type")

    db_execute(
        "UPDATE conversations SET statut=%s, sujet=%s, service_type=%s, "
        "updated_at=NOW() WHERE id=%s",
        (new_statut, new_sujet, new_service, conv_id_db)
    )

    return jsonify({
        "bot_response":    bot_resp,
        "conversation_id": conv_id_db,
        "session_ended":   result.get("session_ended", False),
        "transferred":     result.get("transferred", False),
        "statut":          new_statut,
    })


# ══════════════════════════════════════════════════════════
#  API HISTORIQUE
# ══════════════════════════════════════════════════════════

@app.route("/api/user/history")
@login_required
def api_history():
    user_id = session["user_id"]
    reclamations = db_execute(
        "SELECT reclamation_id, sujet, service_type, statut, created_at, "
        "updated_at, nb_messages, apercu "
        "FROM v_user_reclamations "
        "WHERE user_id = %s "
        "ORDER BY created_at DESC "
        "LIMIT 50",
        (user_id,), fetchall=True
    )
    # Sérialiser datetime
    for r in reclamations:
        if r.get("created_at"):
            r["created_at"] = r["created_at"].strftime("%d/%m/%Y %H:%M")
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].strftime("%d/%m/%Y %H:%M")
    return jsonify({"reclamations": reclamations})


@app.route("/api/user/conversation/<int:conv_id>")
@login_required
def api_conversation_detail(conv_id):
    user_id = session["user_id"]
    # Vérifier que cette conversation appartient à l'user
    conv = db_execute(
        "SELECT * FROM conversations WHERE id = %s AND user_id = %s",
        (conv_id, user_id), fetchone=True
    )
    if not conv:
        return jsonify({"error": "Non trouvé"}), 404

    messages = db_execute(
        "SELECT role, content, timestamp FROM messages "
        "WHERE conversation_id = %s ORDER BY timestamp ASC",
        (conv_id,), fetchall=True
    )
    for m in messages:
        if m.get("timestamp"):
            m["timestamp"] = m["timestamp"].strftime("%d/%m/%Y %H:%M:%S")

    # Sérialiser conv
    if conv.get("created_at"):
        conv["created_at"] = conv["created_at"].strftime("%d/%m/%Y %H:%M")
    if conv.get("updated_at"):
        conv["updated_at"] = conv["updated_at"].strftime("%d/%m/%Y %H:%M")

    return jsonify({"conversation": dict(conv), "messages": messages})


@app.route("/api/user/new_conversation", methods=["POST"])
@login_required
def api_new_conversation():
    user_id = session["user_id"]
    new_session_id = str(uuid.uuid4())
    conv_id = db_execute(
        "INSERT INTO conversations (user_id, session_id, statut) "
        "VALUES (%s, %s, 'en_cours')",
        (user_id, new_session_id), lastrowid=True
    )
    # Réinitialiser l'état mémoire
    if new_session_id in user_conv_state:
        del user_conv_state[new_session_id]

    return jsonify({"conversation_id": conv_id, "session_id": new_session_id})


@app.route("/api/user/profile")
@login_required
def api_profile():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Non trouvé"}), 404
    if user.get("created_at"):
        user["created_at"] = user["created_at"].strftime("%d/%m/%Y")
    return jsonify({"user": dict(user)})


@app.route("/api/user/stats")
@login_required
def api_stats():
    user_id = session["user_id"]
    total = db_execute(
        "SELECT COUNT(*) AS total FROM conversations WHERE user_id=%s",
        (user_id,), fetchone=True
    )
    resolues = db_execute(
        "SELECT COUNT(*) AS cnt FROM conversations "
        "WHERE user_id=%s AND statut='resolue'",
        (user_id,), fetchone=True
    )
    transferees = db_execute(
        "SELECT COUNT(*) AS cnt FROM conversations "
        "WHERE user_id=%s AND statut='transferee'",
        (user_id,), fetchone=True
    )
    en_cours = db_execute(
        "SELECT COUNT(*) AS cnt FROM conversations "
        "WHERE user_id=%s AND statut='en_cours'",
        (user_id,), fetchone=True
    )
    return jsonify({
        "total":      total["total"]       if total else 0,
        "resolues":   resolues["cnt"]      if resolues else 0,
        "transferees": transferees["cnt"]  if transferees else 0,
        "en_cours":   en_cours["cnt"]      if en_cours else 0,
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
