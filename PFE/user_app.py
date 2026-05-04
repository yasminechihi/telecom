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
    conversations_get_by_user, conversation_rate,
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
#  MAPPING INTENT → SUGGESTED_ACTION (14 types du dataset)
#  Clés = intents retournés par NLU (INTENT_PATTERNS dans nlu.py)
#  Valeurs = suggested_action correspondant dans le dataset
#
#  Utilisé lors du transfert agent :
#    - Si le problème est connu  → TTS dit l'action suggérée + numéro/texte du dernier message
#    - Si le problème est inconnu → TTS lit directement le message client en arabe
# ══════════════════════════════════════════════════════════

INTENT_TO_ACTION: dict = {
    # ── Graphie dataset (sortie modèle ML, avec ة) ──────────
    "عطل في الشبكة":            "تثبت من حالة الشبكة",
    "بطء في الانترنات":          "اختبار سرعة التدفق",
    "انقطاع الانترنات":          "تشخيص تقني",
    "مشكلة في إشارة الويفي":    "تقديم نصيحة تقنية",
    "مشكلة في الدفع":            "إعادة تفعيل الخط",
    "اعتراض على الفاتورة":       "استخراج تفاصيل الفاتورة",
    "استفسار عن الرصيد":         "تقديم كود USSD",
    "استفسار عن العروض":         "تقديم معلومات عن العروض",
    "مشكلة في التجوال":          "تثبت من حالة التجوال",
    "تأخير في التركيب":          "متابعة حالة الطلب",
    "تبديل شريحة":               "مد الحريف بموقع فرع",
    "تغيير الخدمة":              "تحويل نوع الخدمة",
    "عطب في الجهاز":             "تبديل المودم",
    "استفسار عن التغطية":        "تثبت من تغطية الفيبر",
    # ── Graphie INTENT_PATTERNS NLU (fallback regex, avec ه) ─
    "عطل في الشبكه":             "تثبت من حالة الشبكة",
    "بطء في الانترنت":           "اختبار سرعة التدفق",
    "انقطاع الانترنت":           "تشخيص تقني",
    "مشكله في اشاره الويفي":     "تقديم نصيحة تقنية",
    "مشكله في الدفع":            "إعادة تفعيل الخط",
    "اعتراض على الفاتوره":       "استخراج تفاصيل الفاتورة",
    "مشكله في الجوال":           "تثبت من حالة التجوال",
    "تاخير في التركيب":          "متابعة حالة الطلب",
    "تبديل شريحه":               "مد الحريف بموقع فرع",
    "تغيير الخدمه":              "تحويل نوع الخدمة",
    "استفسار عن التغطيه":        "تثبت من تغطية الفيبر",
}

# Table normalisée (ة→ه, أإآ→ا) pour lookup tolérant aux variantes orthographiques
def _norm_intent_key(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('ة', 'ه').replace('ت', 'ت')   # ة → ه
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')  # alef variants
    return s

_INTENT_ACTION_NORM: dict = {_norm_intent_key(k): v for k, v in INTENT_TO_ACTION.items()}

# Intents traités ENTIÈREMENT par le bot (RAG) — ne doivent JAMAIS déclencher un
# transfert vers agent humain ni un appel MicroSIP.
_NO_TRANSFER_INTENTS_NORM: frozenset = frozenset(
    _norm_intent_key(k) for k in {
        "استفسار عن التغطية",   # Couverture fibre → réponse informative directe
        "استفسار عن التغطيه",
    }
)

def _is_no_transfer_intent(intent: str) -> bool:
    """True si cet intent ne doit jamais déclencher un transfert vers l'agent humain."""
    return bool(intent and _norm_intent_key(intent.strip()) in _NO_TRANSFER_INTENTS_NORM)

# Intents qui nécessitent TOUJOURS de demander le numéro de demande avant de
# répondre ou transférer. Ils suivent exactement la même logique que تغيير الخدمة :
#   clarification → demande du numéro → réponse apprise (si connue) OU transfert.
# Le RAG peut retourner une réponse directe pour ces types — on l'intercepte et
# on demande le numéro quand même pour garantir un flux cohérent.
_ASK_NUMBER_INTENTS_NORM: frozenset = frozenset(
    _norm_intent_key(k) for k in {
        "مشكلة في الدفع",
        "مشكله في الدفع",
        "اعتراض على الفاتورة",
        "اعتراض على الفاتوره",
        "انقطاع الانترنات",
        "انقطاع الانترنت",
        "تأخير في التركيب",
        "تاخير في التركيب",
        "مشكلة في التجوال",
        "مشكله في التجوال",
    }
)

def _is_ask_number_intent(intent: str) -> bool:
    """True si cet intent doit TOUJOURS passer par la demande du numéro de demande."""
    return bool(intent and _norm_intent_key(intent.strip()) in _ASK_NUMBER_INTENTS_NORM)


# Valeurs d'intent considérées comme "inconnues / invalides".
# Python `or` ne distingue pas '' de 'غير محدد' (les deux sont truthy/falsy différemment),
# ce qui fait que '"غير محدد" or "تأخير في التركيب"' retourne "غير محدد" — incorrect.
_UNKNOWN_INTENT_SET: frozenset = frozenset({"", "غير محدد", "unknown", "غير_محدد"})


def _resolve_intent(stored: str, fallback: str) -> str:
    """
    Retourne `stored` s'il est sémantiquement valide (non-vide, non-inconnu),
    sinon retourne `fallback`.

    Exemple :
      'غير محدد' or 'تأخير في التركيب'  →  'غير محدد'   ← INCORRECT (Python or)
      _resolve_intent('غير محدد', 'تأخير في التركيب')  →  'تأخير في التركيب'  ← CORRECT
    """
    s = (stored or "").strip()
    return s if s not in _UNKNOWN_INTENT_SET else (fallback or "").strip()


# Détecte toutes les formulations "donne-moi un numéro" dans les réponses du dataset :
#   "اعطيني الرقم"  / "اعطيني رقم المطلب" / "اعطيني رقمك"
#   "أعطيني رقم الخط" / "أعطيني رقم المطلب"  (avec hamza)
_ASK_NUMBER_RE = re.compile(r'[اأ]عطيني\s*(الرقم|رقم)', re.UNICODE)

# Détecte les demandes de numéro de RAPPEL dans les réponses du dataset :
#   "خليلي رقمك" / "خلّيلي رقمك" / "خليني رقمك"   (استفسار عن التغطية)
# Différent de _ASK_NUMBER_RE : ici le bot note le numéro pour rappeler le client,
# pas pour déclencher un ticket de transfert vers agent humain.
_CALLBACK_NUMBER_RE = re.compile(r'خلّ?[يا][لن]ي\s*رقمك', re.UNICODE)


def _lookup_action(intent: str) -> str:
    """Cherche l'action pour un intent, d'abord exact puis normalisé."""
    action = INTENT_TO_ACTION.get(intent, "")
    if not action:
        action = _INTENT_ACTION_NORM.get(_norm_intent_key(intent), "")
    return action


def _build_tts_text(sess: dict) -> str:
    """
    Construit le texte qui sera lu par TTS à l'agent lors du transfert.

    Règle basée sur le flag is_unknown_problem (positionné aux 5 points de transfert) :

      • is_unknown_problem = False  → Problème CONNU (dans les 14 types du dataset)
            TTS = suggested_action  +  dernier message du client
            Ex : "تثبت من حالة الشبكة — 20240115"

      • is_unknown_problem = True   → Problème INCONNU (hors dataset)
            TTS = dernier message du client tel quel (arabe brut)
            Pas de suggested_action.
    """
    # Dernier message utilisateur (avant transfert)
    history   = sess.get("history", [])
    last_user = next((t for r, t in reversed(history) if r == "user"), "").strip()

    # Problème original qui a déclenché le transfert (fallback)
    original  = (sess.get("original_problem") or last_user or "").strip()

    # Utiliser le flag explicite positionné lors du transfert
    # Défaut False : si absent (session initialisée avec False dans _get_conv_state)
    is_unknown = sess.get("is_unknown_problem", False)

    # ── Intents invalides — à filtrer dans TOUTES les sources ──────────────────
    _INVALID_INTENTS = {"غير محدد", "unknown", "غير_محدد", ""}

    if not is_unknown:
        # Problème CONNU → chercher la suggested_action
        # Priorité : pending_intent (intent de la réclamation originale, fiable)
        #            puis last_nlu["intent"] (peut être pollué par le dernier message,
        #            ex. si l'utilisateur a tapé un numéro de demande)
        pending = (sess.get("pending_intent") or "").strip()
        # Filtrer pending si invalide (évite "غير محدد" comme intent principal)
        if pending in _INVALID_INTENTS:
            pending = ""
        nlu_int = (sess.get("last_nlu", {}).get("intent") or "").strip()
        # Filtrer les intents invalides (ex: "غير محدد" = dernier msg était un numéro)
        if nlu_int in _INVALID_INTENTS:
            nlu_int = ""
        intent = pending or nlu_int          # pending_intent a priorité
        action = _lookup_action(intent)
        # Fallback : si l'intent principal n'a pas d'action, tenter l'autre source
        if not action and nlu_int and nlu_int != intent:
            action = _lookup_action(nlu_int)
        if not action and pending and pending != intent:
            action = _lookup_action(pending)
        if action:
            sep = " — " if last_user else ""
            return f"{action}{sep}{last_user}"
        # Aucune action trouvée → fallback message brut
        logger.warning(
            f"[TTS] is_unknown=False mais aucune action trouvée "
            f"(pending='{pending}' nlu_int='{nlu_int}') → message brut"
        )
        return original or last_user
    else:
        # Problème INCONNU → dernier message du client uniquement, pas de suggested_action
        return last_user or original


# ══════════════════════════════════════════════════════════
#  APPRENTISSAGE EPHEMERE (session uniquement — identique à app.py)
#  Oublié dès le redémarrage du serveur (in-memory uniquement).
# ══════════════════════════════════════════════════════════

# ── Store global d'apprentissage — partagé entre toutes les sessions ─────────
# COMPORTEMENT VOULU : mémoire volatile.
#   • Toutes les sessions ACTIVES bénéficient des réponses apprises (global).
#   • Au redémarrage du serveur → liste vide → état initial garanti.
#   • La fonction _load_learned_responses() existe mais n'est PAS appelée
#     au démarrage : c'est intentionnel pour respecter le reset-on-restart.
_global_learned_responses: list = []

# Chemin du fichier de trace (utilisé pour audit/debug uniquement, jamais rechargé)
_LEARN_PERSIST_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "bot_learned_responses.json"
)


def _load_learned_responses() -> None:
    """
    [NON APPELÉE AU DÉMARRAGE — INTENTIONNEL]
    Chargement des réponses depuis le fichier JSON persistant.
    Cette fonction existe pour les scénarios de migration / import manuel.
    Elle n'est PAS appelée au démarrage afin de garantir que le bot
    repart toujours d'un état vierge à chaque redémarrage du serveur.
    Pour activer la persistance, appeler cette fonction dans le bloc
    if __name__ == "__main__" (et accepter que le reset-on-restart ne soit plus garanti).
    """
    global _global_learned_responses
    if not os.path.exists(_LEARN_PERSIST_FILE):
        logger.info("[Learning] Pas de fichier persistant → apprentissage vide au démarrage.")
        return
    try:
        with open(_LEARN_PERSIST_FILE, "r", encoding="utf-8") as f:
            records = json.load(f)
        if not isinstance(records, list):
            records = []
        loaded = 0
        for rec in records:
            pt = (rec.get("problem_text") or "").strip()
            rt = (rec.get("response_text") or "").strip()
            if not pt or not rt:
                continue
            entry = {"problem_text": pt, "response_text": rt, "embedding": None}
            # Recalculer l'embedding si le modèle est disponible
            try:
                if response_eng.model is not None:
                    entry["embedding"] = response_eng.model.encode([pt])[0]
            except Exception:
                pass
            _global_learned_responses.append(entry)
            loaded += 1
        logger.info(
            f"[Learning] {loaded} réponse(s) chargée(s) depuis {_LEARN_PERSIST_FILE}"
        )
    except Exception as _e:
        logger.warning(f"[Learning] Echec chargement persistance : {_e}")


def _save_learned_responses() -> None:
    """
    Sauvegarde _global_learned_responses dans le fichier JSON persistant.
    Appelé après chaque nouvel apprentissage pour garantir la persistance.
    """
    global _global_learned_responses
    try:
        os.makedirs(os.path.dirname(_LEARN_PERSIST_FILE), exist_ok=True)
        records = [
            {
                "problem_text":  e.get("problem_text", ""),
                "response_text": e.get("response_text", ""),
                "learned_at":    e.get("learned_at", ""),
            }
            for e in _global_learned_responses
            if e.get("problem_text") and e.get("response_text")
        ]
        with open(_LEARN_PERSIST_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[Learning] {len(records)} réponse(s) sauvegardée(s) → {_LEARN_PERSIST_FILE}"
        )
    except Exception as _e:
        logger.warning(f"[Learning] Echec sauvegarde persistance : {_e}")


def _session_learn_store(sess: dict, problem_text: str, response_text: str,
                         intent: str = ""):
    """
    Stocke une réponse apprise en mémoire volatile.

    Niveaux de stockage :
      1. Store global (_global_learned_responses) — en mémoire RAM uniquement.
         Partagé entre toutes les sessions tant que le serveur tourne.
         REMIS À ZÉRO au redémarrage du serveur (comportement voulu).
      2. Fichier JSON (_LEARN_PERSIST_FILE) — trace audit/debug uniquement.
         N'est JAMAIS rechargé au démarrage → n'affecte pas le reset-on-restart.
      3. Store session (sess["session_learned_responses"]) — compatibilité interne.

    Le champ `intent` est essentiel pour deux raisons :
      A. force_num : savoir si une demande de numéro est requise à la récupération
         (même si le NLU courant classifie différemment la nouvelle plainte).
      B. intent-boost : améliore le matching en donnant un score de 0.80 quand
         l'intent NLU courant correspond à l'intent stocké (évite les faux-négatifs
         dus à des formulations différentes de la même plainte).
    """
    global _global_learned_responses
    import datetime as _dt

    entry = {
        "problem_text":  problem_text.strip(),
        "response_text": response_text.strip(),
        "intent":        (intent or "").strip(),
        "embedding":     None,
        "learned_at":    _dt.datetime.now().isoformat(),
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

    # ── Persistance immédiate sur disque ──────────────────────────────────────
    _save_learned_responses()

    logger.info(
        f"[Learning] Réponse mémorisée (total global: {len(_global_learned_responses)}) : "
        f"'{problem_text[:50]}' → '{response_text[:50]}'"
    )


def _find_session_learned_pair(sess: dict, query_text: str,
                               cur_intent: str = "") -> tuple:
    """
    Cherche si query_text correspond à un problème déjà résolu par un agent humain.

    Retourne (response_text, stored_intent) si trouvé, ou (None, "") sinon.

    Couches de matching (du plus précis au plus flou) :
      1. Correspondance exacte                       → score 1.00
      2. Sous-chaîne                                 → score 0.92
      3. Recoupement ≥ 2 mots-clés (> 2 chars)      → score ≤ 0.90
      4. Similarité cosinus (embeddings)             → score = cosine
      5. Intent-boost : si cur_intent correspond à
         l'intent stocké (deux intents non-vides)   → score = max(score, 0.82)
         Cela permet de trouver des correspondances pour des plaintes formulées
         différemment mais classifiées au même intent NLU
         (ex : "التركيب مانجاش" vs "عندي شهر نستنى التركيب" → تأخير في التركيب).
    """
    global _global_learned_responses

    learned = _global_learned_responses or sess.get("session_learned_responses", [])
    if not learned:
        return None, ""

    logger.info(
        f"[Learning] Vérification : {len(learned)} réponse(s) pour "
        f"'{query_text[:50]}' (intent='{cur_intent}')"
    )

    try:
        import numpy as np
        has_numpy = True
    except ImportError:
        has_numpy = False

    # Pré-calculer embedding de la requête (réutilisé pour chaque entrée)
    q_emb = None
    try:
        if has_numpy and response_eng.model is not None:
            q_emb = response_eng.model.encode([query_text])[0]
    except Exception:
        pass

    # Normaliser l'intent courant pour la comparaison
    _cur_int_norm = _norm_intent_key(cur_intent) if cur_intent else ""
    _unknown_intents = {"", "غير محدد", "unknown", "غير_محدد"}

    best_score, best_resp, best_intent = 0.0, None, ""
    best_entry  = None    # référence vers l'entrée gagnante (pour mise à jour intent)
    best_problem = ""

    for entry in learned:
        problem        = entry.get("problem_text", "").strip()
        resp           = entry.get("response_text", "")
        stored_intent  = (entry.get("intent") or "").strip()
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
            # Couche 3 : recoupement de mots-clés (≥ 2 mots > 2 chars)
            q_words = set(w for w in query_text.split() if len(w) > 2)
            p_words = set(w for w in problem.split()    if len(w) > 2)
            common  = q_words & p_words
            if len(common) >= 2:
                kw_score = len(common) / max(len(q_words), len(p_words), 1)
                score = min(0.90, kw_score * 1.1)

            # Couche 4 : similarité cosinus (embeddings)
            if has_numpy and q_emb is not None:
                emb = entry.get("embedding")
                if emb is not None:
                    try:
                        norm = (float(np.linalg.norm(q_emb)) *
                                float(np.linalg.norm(emb))) + 1e-9
                        cos  = float(np.dot(q_emb, emb)) / norm
                        if cos > score:
                            score = cos
                    except Exception:
                        pass

            # Couche 5 : intent-boost
            # Si le NLU courant identifie le MÊME intent que celui stocké lors de
            # l'apprentissage (et que les deux sont des intents connus), on monte
            # le score à 0.82 pour dépasser le seuil de 0.62 même si les textes
            # sont formulés différemment.
            if (
                _cur_int_norm
                and _cur_int_norm not in _unknown_intents
                and stored_intent
                and _norm_intent_key(stored_intent) not in _unknown_intents
                and _cur_int_norm == _norm_intent_key(stored_intent)
            ):
                score = max(score, 0.82)
                logger.info(
                    f"[Learning] Intent-boost appliqué : "
                    f"intent='{cur_intent}' ↔ stored='{stored_intent}' "
                    f"→ score={score:.3f}"
                )

        if score > best_score:
            best_score   = score
            best_resp    = resp
            best_intent  = stored_intent
            best_entry   = entry
            best_problem = problem

    MIN_SCORE = 0.62
    if best_score >= MIN_SCORE and best_resp:
        # ── Couche 6 : inférence intent manquant ou sémantiquement invalide ────
        # Si l'entrée gagnante a un intent vide OU "غير محدد" / "unknown"
        # (ex. quand l'apprentissage a reçu l'intent NLU du numéro saisi = "غير محدد"),
        # tenter d'inférer l'intent correct via NLU sur le TEXTE DU PROBLÈME STOCKÉ,
        # puis mettre à jour l'entrée en mémoire pour tous les appels suivants.
        if (not best_intent or best_intent in _UNKNOWN_INTENT_SET) \
                and best_entry is not None and best_problem:
            try:
                _inferred_nlu = nlu.analyze(best_problem)
                _inferred_int = (_inferred_nlu.get("intent") or "").strip()
                if _inferred_int and _inferred_int not in _unknown_intents:
                    best_intent = _inferred_int
                    best_entry["intent"] = _inferred_int   # mise à jour en mémoire
                    logger.info(
                        f"[Learning] Intent inféré du problème stocké : "
                        f"'{best_problem[:50]}' → '{_inferred_int}' "
                        f"(entrée mise à jour en mémoire)"
                    )
            except Exception:
                pass

        logger.info(
            f"[Learning] Réponse trouvée (score={best_score:.3f}, "
            f"intent='{best_intent}') pour '{query_text[:50]}'"
        )
        return best_resp, best_intent

    return None, ""


def _find_session_learned(sess: dict, query_text: str, cur_intent: str = "") -> str | None:
    """
    Wrapper de compatibilité sur _find_session_learned_pair.
    Retourne uniquement le texte de la réponse apprise (ou None).
    Utiliser _find_session_learned_pair directement quand on a besoin de l'intent stocké.
    """
    resp, _ = _find_session_learned_pair(sess, query_text, cur_intent=cur_intent)
    return resp


# Démarrage automatique Asterisk dès le lancement de user_app.py
_auto_start_asterisk()

# ── Flask app ─────────────────────────────────────────────
app = Flask(__name__,
            template_folder="templates",
            static_folder="static")
app.secret_key = "tt_user_espace_2026"
app.config["JSON_AS_ASCII"] = False

# ── CORS — autorise l'application Flutter (web + mobile) ──
def _is_allowed_origin(origin: str) -> bool:
    """
    Autorise localhost/127.0.0.1 (Flutter Web) et les IPs du réseau local
    (192.168.x.x, 10.x.x.x, 172.16-31.x.x) pour les tests sur téléphone physique.
    En production, remplace cette logique par une liste fixe.
    """
    if not origin:
        return True   # Flutter mobile n'envoie pas d'Origin → toujours autorisé
    import re
    return bool(re.match(
        r'https?://'
        r'(localhost|127\.0\.0\.1'
        r'|192\.168\.\d{1,3}\.\d{1,3}'
        r'|10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        r'|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}'
        r')(:\d+)?$',
        origin
    ))

def _apply_cors(response_or_headers, origin: str):
    if _is_allowed_origin(origin):
        response_or_headers["Access-Control-Allow-Origin"]      = origin
        response_or_headers["Access-Control-Allow-Credentials"] = "true"
        response_or_headers["Access-Control-Allow-Methods"]     = "GET, POST, PUT, DELETE, OPTIONS"
        response_or_headers["Access-Control-Allow-Headers"]     = "Content-Type, Authorization, Cookie, X-Requested-With, X-User-ID"

@app.before_request
def _handle_preflight():
    """
    Intercepte TOUS les préflight OPTIONS avant le routage Flask.
    Sans ça, les POST JSON de Flutter Web déclenchent un 405 OPTIONS.
    """
    if request.method == "OPTIONS":
        resp = app.make_default_options_response()
        _apply_cors(resp.headers, request.headers.get("Origin", ""))
        return resp

@app.after_request
def _add_cors_headers(response):
    _apply_cors(response.headers, request.headers.get("Origin", ""))
    return response

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
            "is_unknown_problem": False,      # True = hors dataset → TTS lit le message brut
            "session_learned_responses": [],  # réponses apprises dans cette session (éphémères)
            "user_id": "",                    # stocké pour message_add dans api_internal_agent_reply
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


def _extract_wilaya_from_text(text: str) -> str:
    """
    Détecte un nom de wilaya directement dans le texte de l'utilisateur.
    Utilisé comme fallback quand le NLU ne l'extrait pas en tant qu'entité.
    """
    if not text:
        return ""
    m = _WILAYA_DETECT_RE.search(text)
    return m.group(0) if m else ""


def _extract_delegation_from_text(text: str) -> str:
    """
    Tente d'extraire la معتمدية depuis le texte utilisateur.
    1. Cherche les patterns "في [lieu]" où le lieu n'est pas un nom de wilaya connu.
    2. Fallback : vérifie si le texte (ou un mot) correspond directement à une معتمدية
       connue dans DELEGATION_WILAYA_MAP (ex: user dit juste "الحمامات" ou "المرسى").
    """
    if not text:
        return ""
    import re as _re
    # ── Passe 1 : pattern "في X" ─────────────────────────────────────────────
    candidates = _re.findall(r'في\s+([\u0600-\u06FF\s\-]{2,30}?)(?:\s*[،,\.\!؟]|$)', text)
    for cand in candidates:
        cand = cand.strip()
        if not cand:
            continue
        if not _WILAYA_DETECT_RE.fullmatch(cand):
            return cand
    # ── Passe 2 : lookup direct dans DELEGATION_WILAYA_MAP ───────────────────
    # Couvre le cas où l'user répond juste "الحمامات" sans "في" (stage waiting_for_delegation).
    text_clean = text.strip()
    if text_clean in DELEGATION_WILAYA_MAP and not _WILAYA_DETECT_RE.fullmatch(text_clean):
        return text_clean
    for token in text_clean.split():
        token = token.strip()
        if token in DELEGATION_WILAYA_MAP and not _WILAYA_DETECT_RE.fullmatch(token):
            return token
    return ""


def _update_entities(sess: dict, nlu_result: dict, user_text: str = ""):
    """
    Met à jour les entités collectées depuis le résultat NLU.
    Si le NLU ne détecte pas de wilaya/délégation, tente de les extraire
    directement depuis le texte de l'utilisateur (regex).

    RÈGLE ANTI-ÉCRASEMENT : si le NLU n'a pas trouvé de localisation
    explicite dans le texte courant (location_explicit=False), on ne
    remplace JAMAIS une wilaya/délégation déjà correctement collectée
    lors d'un tour précédent. Cela évite que le modèle ML écrase
    "تطاوين" (extrait du 1er message) par "تونس" (valeur par défaut ML)
    quand l'user répond juste "فيكس" ou un chiffre.
    """
    ents = nlu_result.get("entities", {})
    collected = sess.setdefault("collected_entities", {})

    # Détecter si la localisation a été trouvée EXPLICITEMENT dans le texte courant
    # (flag positionné par NLU._fix_location_from_text)
    location_explicit = ents.get("location_explicit")  # True / False / None (absent)

    for k, v in ents.items():
        if k == "location_explicit":
            continue   # flag interne — ne pas stocker dans collected_entities
        # Pour wilaya et délégation : ne pas écraser une valeur déjà collectée
        # si la localisation n'est PAS explicite dans le tour courant.
        if k in ("wilaya", "delegation"):
            if location_explicit is False and collected.get(k):
                # On préserve la localisation correcte accumulée
                continue
        if v:
            collected[k] = v

    # Fallback regex : extraire wilaya depuis le texte si NLU ne l'a pas trouvée
    if not collected.get("wilaya") and user_text:
        w = _extract_wilaya_from_text(user_text)
        if w:
            collected["wilaya"] = w

    # Fallback regex : extraire معتمدية depuis le texte si NLU ne l'a pas trouvée
    if not collected.get("delegation") and user_text:
        d = _extract_delegation_from_text(user_text)
        if d:
            collected["delegation"] = d


def _needs_delegation(entities: dict) -> bool:
    """
    Retourne True quand la wilaya est connue mais que la معتمدية doit encore être demandée.

    CAS SPÉCIAL : le NLU's _fix_location_from_text (passe 2 — capitales de wilaya) positionne
    delegation == wilaya quand l'user mentionne une capitale (ex "المنستير", "سوسة", "القيروان").
    Dans ce cas, la délégation n'est PAS vraiment renseignée — c'est juste le nom de la wilaya
    utilisé comme proxy.  On doit donc redemander la معتمدية spécifique.
    """
    if not entities:
        return False
    wilaya = entities.get("wilaya", "")
    deleg  = entities.get("delegation", "")
    # delegation vide OU delegation = wilaya (capitale proxy → pas une vraie معتمدية)
    return bool(wilaya) and (not bool(deleg) or deleg == wilaya)


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


def _needs_location_intent(intent: str) -> bool:
    """Retourne True si l'intent est sensible à la localisation (indépendamment des entités)."""
    if not intent:
        return False
    loc_intents = getattr(Config, "LOCATION_DEPENDENT_INTENTS", set())
    if not loc_intents:
        return False
    intent_norm = _norm_intent_key(intent)
    return intent_norm in {_norm_intent_key(i) for i in loc_intents}


def _needs_location(entities: dict, intent: str = "") -> bool:
    """
    Retourne True quand l'intent nécessite une localisation ET
    que ni wilaya ni délégation ne sont encore connues dans la session.
    Utilise LOCATION_DEPENDENT_INTENTS de config (comparaison normalisée).
    """
    if not intent:
        return False
    loc_intents = getattr(Config, "LOCATION_DEPENDENT_INTENTS", set())
    if not loc_intents:
        return False
    # Normalisation tolérante (ة→ه, variantes alef) pour comparaison robuste
    intent_norm = _norm_intent_key(intent)
    loc_intents_norm = {_norm_intent_key(i) for i in loc_intents}
    if intent_norm not in loc_intents_norm:
        return False
    # Si wilaya OU délégation déjà connue → pas besoin de poser la question
    if not entities:
        return True
    wilaya = entities.get("wilaya", "")
    deleg  = entities.get("delegation", "")
    return not bool(wilaya) and not bool(deleg)


# ── Noms de wilayas tunisiennes pour détection dans les réponses RAG ──────────
# Triés par longueur décroissante pour éviter les remplacements partiels.
# "تونس" exclu : trop ambigu (capitale vs pays).
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
    """Retourne True si la réponse RAG contient un nom de wilaya tunisienne hardcodé."""
    return bool(text and _WILAYA_DETECT_RE.search(text))


def _localize_response(text: str, entities: dict) -> str:
    """
    Localise une réponse RAG :
    1. Remplace les placeholders ([المنطقة], [الولاية], [المعتمدية]…) par la localisation.
    2. Remplace les noms de wilayas ÉTRANGÈRES (≠ wilaya du user) :
       • Si le user est à المنستير et la réponse dit "في المنستير" → on garde
       • Si le user est à المنستير et la réponse dit "في باجة" → remplacé par "في المنستير"
       • Si localisation inconnue → wilaya étrangère remplacée par "منطقتك"
    3. Remplace "في تونس" (hardcodé dans la plupart des réponses RAG) par la wilaya
       réelle de l'utilisateur quand celui-ci n'est pas à تونس.
       "تونس" est exclu de _WILAYA_RAW_DETECT (ambiguïté capitale/pays) mais on
       le gère ici explicitement avec une regex contextuelle.
    """
    if not text:
        return text
    entities = entities or {}
    user_wilaya = entities.get("wilaya", "")
    user_deleg  = entities.get("delegation", "")

    # Placeholder → utiliser la délégation si connue, sinon la wilaya
    placeholder_loc = user_deleg or user_wilaya or "منطقتك"
    for placeholder in ["[المنطقة]", "[الولاية]", "[المعتمدية]", "المنطقة المحددة"]:
        text = text.replace(placeholder, placeholder_loc)

    # Remplacement des noms de wilaya hardcodés dans la réponse RAG
    # Règle : si la wilaya dans le texte = wilaya du user → on la garde telle quelle
    #          si c'est une autre wilaya → on remplace par la wilaya du user (ou "منطقتك")
    if _WILAYA_DETECT_RE.search(text):
        replacement = user_wilaya if user_wilaya else "منطقتك"
        def _replace_wilaya_smart(m: re.Match) -> str:
            found = m.group(0)
            # Garder si c'est la wilaya de l'utilisateur
            if user_wilaya and found == user_wilaya:
                return found
            # Remplacer les autres wilayas
            return replacement
        text = _WILAYA_DETECT_RE.sub(_replace_wilaya_smart, text)

    # Cas spécial "تونس" : exclu de _WILAYA_RAW_DETECT car ambigu (capitale vs pays).
    # On le remplace explicitement UNIQUEMENT dans les constructions locatives
    # "في تونس" / "بتونس" / "بالعاصمة تونس" quand l'utilisateur n'est pas à تونس.
    if user_wilaya and user_wilaya not in ("تونس", "أريانة", "بن عروس", "منوبة"):
        loc_replacement = user_wilaya
        # "في تونس" / "ف تونس" → "في [wilaya user]"
        text = re.sub(r'في\s+تونس\b', f'في {loc_replacement}', text)
        text = re.sub(r'بتونس\b',     f'في {loc_replacement}', text)
        text = re.sub(r'بالعاصمة',    f'في {loc_replacement}', text)

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

    # ── Salutation reçue hors stage waiting_greeting ─────────────────────────
    # Cas : l'app mobile (ou le web) envoie "عسلامة" alors que le stage est
    # "initial" ou autre — cela arrive quand :
    #   1. L'app mobile affiche le greeting local sans l'envoyer au serveur,
    #      puis l'utilisateur tape lui-même "عسلامة".
    #   2. L'utilisateur re-salue en milieu ou début de session.
    # Sans ce guard, NLU traite "عسلامة" → intent inconnu → transfert injustifié.
    if stage in ("initial",) and _is_greeting(user_text) and not sess.get("transferred"):
        sess["history"].append(("user", user_text))
        bot_resp = Config.GREETING_MESSAGE
        sess["history"].append(("bot", bot_resp))
        # On reste en "initial" : l'utilisateur peut enchaîner avec son problème
        return {"bot_response": bot_resp, "session_ended": False,
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

    # ── Suivi court après solution (ex: "65", numéro de demande) ──────────
    # Quand une solution a déjà été donnée et l'user envoie un message court
    # (chiffres ou ≤ 6 caractères), traiter comme acquittement et clore proprement.
    import re as _re_sol
    _is_number_followup = bool(_re_sol.match(r'^\d[\d\s]*$', user_text.strip()))
    if sess.get("solution_given") and (_is_number_followup or len(user_text.strip()) <= 6):
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
    _update_entities(sess, nlu_result, user_text)
    logger.info(f"[DEBUG-LOC] stage={stage} intent={intent} conf={ml_conf:.2f} "
                f"entities={sess.get('collected_entities')} "
                f"needs_deleg={_needs_delegation(sess.get('collected_entities',{}))}")
    # Stocker le dernier résultat NLU dans la session pour le chat endpoint
    sess["last_nlu"] = {
        "intent":       intent,
        "confidence":   round(float(ml_conf) * 100) if ml_conf <= 1 else int(ml_conf),
        "sentiment":    nlu_result.get("sentiment", ""),
        "service_type": service_type,
        # Entités étendues (renseignées dans la Live Conv. — style Test Bot)
        "wilaya":       nlu_result.get("entities", {}).get("wilaya", "")
                        or sess.get("collected_entities", {}).get("wilaya", ""),
        "delegation":   nlu_result.get("entities", {}).get("delegation", "")
                        or sess.get("collected_entities", {}).get("delegation", ""),
        "action":       nlu_result.get("action", ""),
        "ml_used":      nlu_result.get("ml_used", False),
        "backend":      nlu_result.get("backend", ""),
    }

    # ── active_intent : intent du RECORD (fiable) ou NLU sinon ───
    active_intent = sess.get("pending_intent") or intent

    # ── Numéro de rappel reçu (ex: استفسار عن التغطية) → clore la conversation ──
    # Le bot avait demandé "خليلي رقمك" pour rappeler le client.
    # L'user vient de donner son numéro → remercier et fermer, SANS aucun transfert.
    if stage == "waiting_for_callback_number":
        bot_resp = Config.THANKS_MESSAGE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "waiting_greeting"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": True,
                "transferred": False, "statut": "resolue"}

    # ── Numéro de demande demandé ────────────────────────────
    if stage == "waiting_for_request_number":
        # Vérifier d'abord si une réponse apprise existe pour ce problème.
        # Si oui : le bot répond directement avec la solution mémorisée (pas de transfert).
        # La clé de recherche = le problème ORIGINAL (pas le numéro que l'user vient d'envoyer).
        _orig_prob_nr    = (sess.get("original_problem") or
                             sess.get("last_transferred_problem") or "").strip()
        _pending_nr      = (sess.get("pending_intent") or active_intent or "").strip()
        _learned_nr, _stored_intent_nr = (
            _find_session_learned_pair(sess, _orig_prob_nr, cur_intent=_pending_nr)
            if _orig_prob_nr else (None, "")
        )
        if _learned_nr:
            bot_resp = _localize_response(_learned_nr, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{conv_session_id}] Réponse apprise (waiting_for_request_number) — transfert évité")
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "resolue",
                    "sujet": _stored_intent_nr or active_intent, "service_type": service_type}

        sess["transferred"]        = True
        sess["is_unknown_problem"] = False   # problème connu — intent identifié
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=0,
                               original_problem=(sess.get("original_problem") or user_text))
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        # NE PAS effacer pending_intent ici : _build_tts_text() en a besoin
        # pour construire "suggested_action — numéro_demande".
        # Il sera effacé plus tard lors de la réponse de l'agent
        # (api_internal_agent_reply / api_reset_transfer).
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    # ── Localisation attendue ─────────────────────────────────
    # L'user vient de répondre à "من أي ولاية ومعتمدية أنت؟"
    # NLU + _update_entities ont déjà capturé la wilaya/délégation.
    if stage == "waiting_for_location":
        _ents_loc = sess.get("collected_entities", {})
        if not _ents_loc.get("wilaya") and not _ents_loc.get("delegation"):
            # L'user n'a toujours pas donné sa localisation → reposer la question
            bot_resp = Config.LOCATION_QUESTION
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": active_intent, "service_type": service_type}
        elif _ents_loc.get("wilaya") and not _ents_loc.get("delegation"):
            # L'user a donné la wilaya mais pas la معتمدية → demander la معتمدية
            bot_resp = _build_delegation_question(_ents_loc)
            sess["stage"] = "waiting_for_delegation"
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": active_intent, "service_type": service_type}
        else:
            # Wilaya ET délégation connues → continuer vers l'étape 2
            sess["stage"] = "responding"
            stage         = "responding"

    # ── Délégation attendue ───────────────────────────────────
    # L'user vient de répondre à "في أي معتمدية بالضبط؟"
    # NLU + _update_entities ont déjà capturé la délégation.
    if stage == "waiting_for_delegation":
        _ents_deleg = sess.get("collected_entities", {})
        if not _ents_deleg.get("delegation"):
            # Toujours pas de délégation → reposer la question (personnalisée avec wilaya)
            bot_resp = _build_delegation_question(_ents_deleg)
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": active_intent, "service_type": service_type}
        else:
            # Délégation reçue → continuer vers l'étape 2
            sess["stage"] = "responding"
            stage         = "responding"

    # ── ÉTAPE 1 : Poser une question de clarification ─────
    if stage == "initial":
        # ── Réponse apprise : vérifier AVANT la question de clarification ────
        # Si le bot a déjà appris une réponse via un agent humain (tous intents
        # connus ou inconnus), court-circuiter la clarification et répondre
        # directement.  Pour les intents nécessitant un numéro de demande,
        # demander le numéro en premier (2 tours au total).
        # IMPORTANT : on utilise l'intent STOCKÉ (pas le NLU courant) pour le
        # check force_num — évite les faux-négatifs quand le NLU classifie
        # différemment la nouvelle plainte (ex : confiance faible → intent="").
        _learned_init_m, _stored_intent_init_m = _find_session_learned_pair(
            sess, user_text, cur_intent=intent
        )
        _eff_intent_init = _resolve_intent(_stored_intent_init_m, intent)
        _force_num_init_m = _is_ask_number_intent(_eff_intent_init)
        if _learned_init_m and not _force_num_init_m:
            bot_resp = _learned_init_m
            sess["stage"]            = "initial"
            sess["solution_given"]   = True
            sess["original_problem"] = user_text
            sess["history"].append(("bot", bot_resp))
            logger.info(
                f"[{conv_session_id}] Réponse apprise (initial, tous intents) : "
                f"'{user_text[:50]}' → '{bot_resp[:60]}'"
            )
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "resolue",
                    "sujet": _eff_intent_init or sess.get("pending_intent", ""),
                    "service_type": service_type}

        elif _learned_init_m and _force_num_init_m:
            # Réponse apprise mais l'intent nécessite le numéro de demande.
            # Sauter la clarification et demander directement le numéro (2e appel, intents connus).
            _ask_num_init = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                    "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
            sess["stage"]            = "waiting_for_request_number"
            sess["pending_intent"]   = _eff_intent_init or intent
            sess["original_problem"] = user_text
            sess["history"].append(("bot", _ask_num_init))
            logger.info(
                f"[{conv_session_id}] Réponse apprise (initial, force_num) → "
                f"demande numéro immédiate pour '{user_text[:50]}'"
            )
            return {"bot_response": _ask_num_init, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": _eff_intent_init or sess.get("pending_intent", ""),
                    "service_type": service_type}

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
            _ents_clari = sess.get("collected_entities", {})
            logger.info(f"[DEBUG-LOC] clari_ok=True clari_q={clari['question'][:40]} "
                        f"_ents_clari={_ents_clari} "
                        f"needs_loc_intent={_needs_location_intent(intent)} "
                        f"needs_deleg={_needs_delegation(_ents_clari)}")
            # ── Toujours combiner clarification + question localisation ──────
            if _needs_location_intent(intent):
                if _needs_delegation(_ents_clari):
                    # Wilaya connue, معتمدية manquante
                    bot_resp += "  " + _build_delegation_question(_ents_clari)
                    sess["location_in_clari"] = "delegation"
                elif _needs_location(_ents_clari, intent):
                    # Ni wilaya ni معتمدية
                    bot_resp += "  " + Config.LOCATION_QUESTION
                    sess["location_in_clari"] = "full"
                # Si les deux sont déjà connues → pas de question de localisation
            elif _needs_delegation(_ents_clari):
                # Intent non listé dans LOCATION_DEPENDENT_INTENTS, mais l'user a déjà
                # mentionné une wilaya → compléter avec la délégation manquante.
                # Essentiel pour l'analyse NLU et la qualité des réponses RAG localisées.
                bot_resp += "  " + _build_delegation_question(_ents_clari)
                sess["location_in_clari"] = "delegation"
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

        # ── Vérifier si ce problème a déjà été résolu par un agent humain ──────
        # Pour les cas inconnus (ou RAG trop faible), avant de transférer à nouveau,
        # on cherche dans le store global si une réponse apprise correspond.
        # Cela évite un transfert inutile pour des problèmes déjà vus et résolus.
        if intent_unknown or rag_gate_failed:
            _learned_unknown, _stored_intent_unk = _find_session_learned_pair(
                sess, user_text, cur_intent=intent
            )
            _eff_intent_unk    = _resolve_intent(_stored_intent_unk, intent)
            _force_num_unk_mob = _is_ask_number_intent(_eff_intent_unk)
            if _learned_unknown and not _force_num_unk_mob:
                bot_resp = _learned_unknown
                sess["stage"]          = "initial"
                sess["solution_given"] = True
                sess["history"].append(("bot", bot_resp))
                logger.info(
                    f"[{conv_session_id}] Réponse apprise (cas inconnu évité) : "
                    f"'{user_text[:50]}' → '{bot_resp[:60]}'"
                )
                return {"bot_response": bot_resp, "session_ended": False,
                        "transferred": False, "statut": "resolue",
                        "sujet": _eff_intent_unk or sess.get("pending_intent", ""),
                        "service_type": service_type}
            elif _learned_unknown and _force_num_unk_mob:
                # Réponse apprise mais numéro requis → demander d'abord le numéro
                _ask_num_unk_mob = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                           "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
                sess["stage"]            = "waiting_for_request_number"
                sess["pending_intent"]   = _eff_intent_unk or intent
                sess["original_problem"] = user_text
                sess["history"].append(("bot", _ask_num_unk_mob))
                logger.info(
                    f"[{conv_session_id}] Réponse apprise (cas inconnu) mais numéro requis → demande numéro"
                )
                return {"bot_response": _ask_num_unk_mob, "session_ended": False,
                        "transferred": False, "statut": "en_cours",
                        "sujet": intent or sess.get("pending_intent", ""),
                        "service_type": service_type}

        if intent_unknown and rag_gate_failed:
            bot_resp = Config.TRANSFER_MESSAGE
            transfer.create_ticket(session_id=conv_session_id,
                                   history=sess["history"],
                                   user_last_text=user_text,
                                   nlu_result=nlu_result,
                                   rag_confidence=clari["confidence"],
                                   original_problem=(sess.get("original_problem") or user_text))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]       = "initial"
            sess["transferred"] = True
            # P2 : intent NLU inconnu + RAG vide. MAIS en conversation multi-tour,
            # pending_intent peut être déjà positionné (problème connu au tour précédent).
            # Si pending_intent est connu → conserver is_unknown_problem=False.
            _p2_existing = (sess.get("pending_intent") or "").strip()
            _p2_known = bool(
                _p2_existing
                and _p2_existing not in ("غير محدد", "unknown", "غير_محدد")
                and _lookup_action(_p2_existing)
            )
            sess["is_unknown_problem"] = not _p2_known   # False si intent connu hérité
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
                                   rag_confidence=clari["confidence"],
                                   original_problem=(sess.get("original_problem") or user_text))
            sess["history"].append(("bot", bot_resp))
            sess["transferred"]        = True
            # P3 : RAG confidence faible.
            # On fait confiance UNIQUEMENT à pending_intent s'il a été positionné
            # dans un tour précédent (via clari_ok=True) — il est fiable.
            # L'intent NLU du tour courant est EXCLU : trop risqué de confondre
            # un problème inconnu avec un intent NLU mal classifié
            # (ex : "عيب" → NLU classe à tort comme "عطب في الجهاز").
            _p3_pending = (sess.get("pending_intent") or "").strip()
            _p3_known   = bool(
                _p3_pending
                and _p3_pending not in ("غير محدد", "unknown", "غير_محدد")
                and _lookup_action(_p3_pending)
            )
            sess["is_unknown_problem"] = not _p3_known
            sess["last_transferred_problem"] = sess.get("original_problem") or user_text
            sess["solution_given"] = True
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": True, "statut": "transferee"}

        # NLU bas mais clari trouvée → passer direct à l'étape 2 (seuil strict)
        sess["stage"]            = "responding"
        sess["pending_intent"]   = clari.get("intent") or intent
        sess["original_problem"] = user_text
        # Si intent sensible à la localisation et localisation inconnue → demander d'abord
        if _needs_location(sess.get("collected_entities"), intent):
            # Ni wilaya ni délégation → demander les deux
            bot_resp = Config.LOCATION_QUESTION
            sess["stage"] = "waiting_for_location"
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": intent, "service_type": service_type}
        elif _needs_delegation(sess.get("collected_entities")):
            # Wilaya connue mais délégation manquante → demander la délégation (tous intents)
            bot_resp = _build_delegation_question(sess.get("collected_entities"))
            sess["stage"] = "waiting_for_delegation"
            sess["history"].append(("bot", bot_resp))
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": intent, "service_type": service_type}

    # ── Négation sur clarification ────────────────────────
    if stage == "clarifying" and _is_negation(user_text):
        bot_resp = Config.NEGATION_CLARIFICATION_RESPONSE
        sess["history"].append(("bot", bot_resp))
        sess["stage"]            = "initial"
        sess["pending_intent"]   = ""
        sess["original_problem"] = ""   # Fix TTS : l'user repart de zéro
        sess["solution_given"]   = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": False, "statut": "resolue"}

    # ── ÉTAPE 2 : Réponse finale (clarifying ou responding) ─

    # ── Check localisation avant RAG ────────────────────────────────────────────
    # Avant d'appeler le RAG, vérifier si on a besoin d'une localisation.
    # Deux cas possibles :
    #   1. Ni wilaya ni معتمدية → demander les deux (LOCATION_QUESTION)
    #   2. Wilaya connue mais معتمدية manquante → demander la معتمدية seule
    _ents_step2   = sess.get("collected_entities", {})
    _intent_step2 = active_intent or intent
    _loc_in_clari = sess.pop("location_in_clari", None)  # question déjà posée ?
    # Sémantique des guards :
    #   _loc_in_clari = "full"       → on a déjà demandé WILAYA + DÉLÉGATION ensemble
    #   _loc_in_clari = "delegation" → on a déjà demandé la DÉLÉGATION seule
    #
    # Règle :
    #   • Ne pas redemander les DEUX (wilaya+délégation) si déjà demandées ("full")
    #   • Ne pas redemander la DÉLÉGATION SEULE si elle a déjà été spécifiquement demandée
    #   • MAIS : si l'user a donné UNIQUEMENT la wilaya en réponse à la question "full",
    #     on doit quand même demander la délégation (question partielle non satisfaite).
    _asked_full_loc  = (_loc_in_clari == "full")
    _asked_deleg_loc = (_loc_in_clari == "delegation")

    if _loc_in_clari:
        # L'user vient de répondre à la question combinée → ré-extraire sa localisation
        _update_entities(sess, {}, user_text)   # extraction regex sur la réponse actuelle
        _ents_step2 = sess.get("collected_entities", {})

    if _needs_location(_ents_step2, _intent_step2) and not _asked_full_loc:
        # Cas 1 : ni wilaya ni معتمدية — demander les deux.
        # Ne pas redemander si "full" a déjà été posée (éviter boucle infinie).
        bot_resp = Config.LOCATION_QUESTION
        sess["stage"] = "waiting_for_location"
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        if not sess.get("pending_intent"):
            sess["pending_intent"] = _intent_step2
        sess["history"].append(("bot", bot_resp))
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": _intent_step2, "service_type": service_type}
    elif _needs_delegation(_ents_step2):
        # Cas 2 : wilaya connue mais معتمدية manquante.
        # Déclenché QUEL QUE SOIT l'intent (pas seulement LOCATION_DEPENDENT_INTENTS) car :
        #   - le NLU peut mal classifier l'intent (ex. réseau → تغيير الخدمة)
        #   - la délégation est essentielle pour la qualité de la réponse ET l'analyse NLU
        # On demande la délégation :
        #   • _loc_in_clari = None       → premier tour, user a mentionné la wilaya dès le début
        #   • _loc_in_clari = "full"     → user a répondu avec SEULEMENT la wilaya → suivi délégation
        #   • _loc_in_clari = "delegation" → user n'a pas répondu à la délégation combinée
        #                                   → on la redemande en question seule (stage dédié)
        bot_resp = _build_delegation_question(_ents_step2)
        sess["stage"] = "waiting_for_delegation"
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        if not sess.get("pending_intent"):
            sess["pending_intent"] = _intent_step2
        sess["history"].append(("bot", bot_resp))
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": _intent_step2, "service_type": service_type}

    # ── Apprentissage éphémère : check prioritaire avant RAG ────────────────────
    # Si l'agent humain a déjà résolu ce problème, on retourne directement la réponse
    # apprise sans interroger le RAG ni transférer.
    # EXCEPTION (implémentée) : les 4 intents _is_ask_number_intent() doivent passer
    # par la demande du numéro (waiting_for_request_number) même si une réponse est
    # apprise — le check appris s'effectue après que l'user fournit son numéro.
    _step2_intent    = (sess.get("pending_intent") or active_intent or "").strip()
    _orig_prob_step2 = (sess.get("original_problem") or
                        sess.get("last_transferred_problem") or user_text).strip()
    _learned_step2, _stored_intent_step2 = _find_session_learned_pair(
        sess, _orig_prob_step2, cur_intent=_step2_intent
    )
    _eff_intent_step2 = _resolve_intent(_stored_intent_step2, _step2_intent)
    _force_num_step2  = _is_ask_number_intent(_eff_intent_step2)
    if _learned_step2 and not _force_num_step2:
        # Réponse apprise disponible ET aucun numéro requis → répondre directement
        bot_resp = _localize_response(_learned_step2, sess.get("collected_entities"))
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["pending_intent"] = ""
        sess["solution_given"] = True
        logger.info(
            f"[{conv_session_id}] Réponse apprise (step2) — "
            f"transfert évité pour '{_orig_prob_step2[:40]}'"
        )
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": False, "statut": "resolue",
                "sujet": active_intent, "service_type": service_type}
    elif _learned_step2 and _force_num_step2:
        # Réponse apprise mais numéro requis → demander le numéro d'abord
        # (la réponse apprise sera donnée à waiting_for_request_number)
        _ask_num_step2 = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                 "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
        sess["stage"] = "waiting_for_request_number"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = _eff_intent_step2 or _step2_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        sess["history"].append(("bot", _ask_num_step2))
        logger.info(
            f"[{conv_session_id}] Réponse apprise (step2) mais numéro requis → "
            f"demande numéro pour '{_orig_prob_step2[:40]}'"
        )
        return {"bot_response": _ask_num_step2, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": active_intent, "service_type": service_type}

    enriched_query = _build_enriched_query(sess, user_text)
    rag_result     = response_eng.find_response(
        enriched_query,
        sess["history"],
        nlu_intent=active_intent
    )

    rag_conf     = rag_result.get("confidence", 0)
    rag_escalate = rag_result.get("escalate", False)

    # Mémoriser le résultat RAG dans last_nlu pour affichage back-office
    if "last_nlu" in sess:
        sess["last_nlu"]["confidence_rag"] = round(float(rag_conf) * 100) if rag_conf <= 1 else int(rag_conf)
        # action de secours depuis RAG si pas fournie par NLU
        if not sess["last_nlu"].get("action"):
            sess["last_nlu"]["action"] = rag_result.get("action", "")

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

    # Certains intents (ex: استفسار عن التغطية) sont résolus entièrement par le bot
    # → bloquer ici le transfert même si le RAG a une confiance trop faible
    if rag_escalate:
        _chk_no_tr = (sess.get("pending_intent") or active_intent or "").strip()
        if _is_no_transfer_intent(_chk_no_tr):
            rag_escalate = False

    if rag_escalate:
        # Réponse apprise ? → répondre directement SAUF pour les 4 intents à numéro obligatoire.
        # Pour مشكلة في الدفع, اعتراض على الفاتورة, انقطاع الانترنات, تأخير في التركيب :
        # demander le numéro d'abord → la réponse apprise est donnée à waiting_for_request_number.
        _chk_esc_intent = (sess.get("pending_intent") or active_intent or "").strip()

        _orig_prob_p4 = (sess.get("original_problem") or
                         sess.get("last_transferred_problem") or user_text).strip()
        _learned_p4, _stored_intent_p4 = _find_session_learned_pair(
            sess, _orig_prob_p4, cur_intent=_chk_esc_intent
        )
        _eff_intent_p4 = _resolve_intent(_stored_intent_p4, _chk_esc_intent)
        _force_num_esc = _is_ask_number_intent(_eff_intent_p4)
        if _learned_p4 and not _force_num_esc:
            # Réponse apprise disponible ET aucun numéro requis → répondre directement
            bot_resp = _localize_response(_learned_p4, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{conv_session_id}] Réponse apprise (rag_escalate) — transfert évité")
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "resolue",
                    "sujet": active_intent, "service_type": service_type}

        # Pour les 4 intents à numéro obligatoire : demander le numéro d'abord
        # (la réponse apprise sera donnée à waiting_for_request_number)
        if _force_num_esc:
            _ask_num = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                               "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
            sess["stage"] = "waiting_for_request_number"
            if not sess.get("pending_intent"):
                sess["pending_intent"] = active_intent
            if not sess.get("original_problem"):
                sess["original_problem"] = user_text
            sess["history"].append(("bot", _ask_num))
            logger.info(
                f"[{conv_session_id}] {_chk_esc_intent} — demande numéro "
                f"(rag_escalate intercepté, flux forcé)"
            )
            return {"bot_response": _ask_num, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": active_intent, "service_type": service_type}

        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=rag_conf,
                               original_problem=(sess.get("original_problem") or user_text))
        sess["history"].append(("bot", bot_resp))
        sess["transferred"]        = True
        # Déterminer si le problème est CONNU (dans les 14 types du dataset).
        # Priorité : pending_intent (issu de la clarification)
        # Fallback  : last_nlu["intent"] (NLU direct, fiable si clarification non déclenchée)
        _p4 = (sess.get("pending_intent") or "").strip()
        if not _p4:
            _p4 = (sess.get("last_nlu", {}).get("intent") or "").strip()
        _known_p4 = bool(_p4 and _lookup_action(_p4))
        sess["is_unknown_problem"] = not _known_p4
        if _known_p4:
            # S'assurer que pending_intent est positionné pour _build_tts_text()
            if not sess.get("pending_intent"):
                sess["pending_intent"] = _p4
        else:
            sess["pending_intent"] = ""
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        sess["stage"]          = "initial"
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    bot_resp = rag_result.get("response") or nlu_result.get("ml_response") or ""
    if not bot_resp:
        bot_resp = Config.NOT_UNDERSTOOD_MSG

    # ── Intercept localisation : intercepte AVANT de retourner la réponse RAG ──────────
    # Déclencheurs (deux conditions indépendantes, en OR) :
    #   A. L'intent est dans LOCATION_DEPENDENT_INTENTS  → localisation toujours nécessaire
    #   B. La réponse RAG contient une wilaya hardcodée  → empêcher une wilaya erronée
    # Note : "في تونس" est géré séparément dans _localize_response (hors _WILAYA_RAW_DETECT).
    #
    # Cas 1 : ni wilaya ni délégation → demander les deux.
    # Cas 2 : wilaya connue mais délégation manquante → demander la délégation seule.
    _ents_rag_chk   = sess.get("collected_entities", {})
    _chk_rag_intent = (sess.get("pending_intent") or active_intent or "").strip()
    _rag_needs_loc  = (
        _needs_location_intent(_chk_rag_intent)   # A : intent location-dépendant
        or _response_has_wilaya(bot_resp)           # B : réponse RAG contient une wilaya
    )
    if _rag_needs_loc and _needs_location(_ents_rag_chk, _chk_rag_intent) and not _asked_full_loc:
        # Cas 1 : aucune localisation connue
        loc_q = Config.LOCATION_QUESTION
        sess["stage"] = "waiting_for_location"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        sess["history"].append(("bot", loc_q))
        logger.info(
            f"[{conv_session_id}] Localisation manquante (intent={_chk_rag_intent}) "
            f"→ demande wilaya+délégation"
        )
        return {"bot_response": loc_q, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": active_intent, "service_type": service_type}
    elif _needs_delegation(_ents_rag_chk):
        # Cas 2 : wilaya connue mais délégation manquante — TOUS les intents.
        # Le NLU peut mal classifier (ex. réseau → تغيير الخدمة) ; on demande
        # la délégation dès que l'user a mentionné une wilaya, pour la qualité
        # de la réponse et l'analyse NLU.
        # Garde _asked_deleg_loc supprimé : on redemande si l'user n'a pas répondu dans clari.
        deleg_q = _build_delegation_question(_ents_rag_chk)
        sess["stage"] = "waiting_for_delegation"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        sess["history"].append(("bot", deleg_q))
        logger.info(
            f"[{conv_session_id}] Délégation manquante (wilaya={_ents_rag_chk.get('wilaya')}) "
            f"→ demande délégation seule"
        )
        return {"bot_response": deleg_q, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": active_intent, "service_type": service_type}

    bot_resp = response_eng._strip_emojis(
        _localize_response(bot_resp, sess.get("collected_entities"))
    )

    # Détection de boucle : éviter de répéter la même réponse
    last_bot = next(
        (t for role, t in reversed(sess.get("history", [])) if role == "bot"), ""
    )
    _chk_loop = (sess.get("pending_intent") or active_intent or "").strip()
    if last_bot and bot_resp.strip() == last_bot.strip() and not _is_no_transfer_intent(_chk_loop):
        # Réponse apprise ? → répondre directement, pas de transfert (Point 5)
        _orig_prob_p5  = (sess.get("original_problem") or
                          sess.get("last_transferred_problem") or user_text).strip()
        _learned_p5, _stored_intent_p5 = _find_session_learned_pair(
            sess, _orig_prob_p5, cur_intent=_chk_loop
        )
        _eff_intent_p5 = _resolve_intent(_stored_intent_p5, _chk_loop)
        _force_num_p5  = _is_ask_number_intent(_eff_intent_p5)
        if _learned_p5 and not _force_num_p5:
            bot_resp = _localize_response(_learned_p5, sess.get("collected_entities"))
            sess["history"].append(("bot", bot_resp))
            sess["stage"]          = "initial"
            sess["pending_intent"] = ""
            sess["solution_given"] = True
            logger.info(f"[{conv_session_id}] Réponse apprise (loop detection) — transfert évité")
            return {"bot_response": bot_resp, "session_ended": False,
                    "transferred": False, "statut": "resolue",
                    "sujet": active_intent, "service_type": service_type}
        elif _learned_p5 and _force_num_p5:
            # Réponse apprise mais numéro requis → demander d'abord le numéro
            _ask_num_p5_mob = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                                      "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
            sess["stage"] = "waiting_for_request_number"
            if not sess.get("pending_intent"):
                sess["pending_intent"] = _eff_intent_p5 or active_intent
            if not sess.get("original_problem"):
                sess["original_problem"] = user_text
            sess["history"].append(("bot", _ask_num_p5_mob))
            logger.info(f"[{conv_session_id}] Réponse apprise (loop detection) mais numéro requis → demande numéro")
            return {"bot_response": _ask_num_p5_mob, "session_ended": False,
                    "transferred": False, "statut": "en_cours",
                    "sujet": active_intent, "service_type": service_type}

        sess["transferred"]        = True
        # Déterminer si le problème est CONNU (dans les 14 types du dataset).
        # Priorité : pending_intent (issu de la clarification)
        # Fallback  : last_nlu["intent"] (NLU direct, fiable si clarification non déclenchée)
        _p5 = (sess.get("pending_intent") or "").strip()
        if not _p5:
            _p5 = (sess.get("last_nlu", {}).get("intent") or "").strip()
        _known_p5 = bool(_p5 and _lookup_action(_p5))
        sess["is_unknown_problem"] = not _known_p5
        if _known_p5:
            # S'assurer que pending_intent est positionné pour _build_tts_text()
            if not sess.get("pending_intent"):
                sess["pending_intent"] = _p5
        else:
            sess["pending_intent"] = ""
        sess["last_transferred_problem"] = sess.get("original_problem") or user_text
        bot_resp = Config.TRANSFER_MESSAGE
        transfer.create_ticket(session_id=conv_session_id,
                               history=sess["history"],
                               user_last_text=user_text,
                               nlu_result=nlu_result,
                               rag_confidence=rag_conf,
                               original_problem=(sess.get("original_problem") or user_text))
        sess["history"].append(("bot", bot_resp))
        sess["stage"]          = "initial"
        sess["solution_given"] = True
        return {"bot_response": bot_resp, "session_ended": False,
                "transferred": True, "statut": "transferee"}

    sess["history"].append(("bot", bot_resp))

    # Pour les 4 intents à numéro obligatoire : si le RAG n'a pas déjà demandé un
    # numéro dans sa réponse, on remplace la réponse par la question du numéro.
    # Cela garantit que le flux est IDENTIQUE à تغيير الخدمة dans tous les cas.
    _force_num_rag = _is_ask_number_intent(
        (sess.get("pending_intent") or active_intent or "").strip()
    )
    if _force_num_rag and not _ASK_NUMBER_RE.search(bot_resp):
        _ask_num_rag = getattr(Config, "ASK_REQUEST_NUMBER_MSG",
                               "أعطيني رقم الطلب أو المعاملة باش نكمل معك.")
        # Remplacer la réponse RAG déjà ajoutée dans l'historique par la demande de numéro
        if sess["history"] and sess["history"][-1][0] == "bot":
            sess["history"][-1] = ("bot", _ask_num_rag)
        else:
            sess["history"].append(("bot", _ask_num_rag))
        sess["stage"] = "waiting_for_request_number"
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
        logger.info(
            f"[{conv_session_id}] {sess.get('pending_intent') or active_intent} "
            f"— demande numéro forcée (réponse RAG interceptée)"
        )
        return {"bot_response": _ask_num_rag, "session_ended": False,
                "transferred": False, "statut": "en_cours",
                "sujet": active_intent, "service_type": service_type}

    if _ASK_NUMBER_RE.search(bot_resp):
        # Le bot demande un numéro (transaction, demande, ligne…)
        # → attendre le numéro de l'utilisateur avant transfert
        sess["stage"] = "waiting_for_request_number"
        # Fix TTS : s'assurer que pending_intent est positionné pour _build_tts_text()
        # (peut ne pas être set si le bot a répondu directement sans passer par clarifying)
        if not sess.get("pending_intent"):
            sess["pending_intent"] = active_intent
        # Fix TTS : s'assurer que original_problem est positionné (fallback pour TTS)
        if not sess.get("original_problem"):
            sess["original_problem"] = user_text
    elif _CALLBACK_NUMBER_RE.search(bot_resp):
        # Le bot demande le numéro de rappel du client (ex: خليلي رقمك)
        # → quand l'user répond avec son numéro, on dit juste au revoir (aucun transfert)
        sess["stage"] = "waiting_for_callback_number"
        # pending_intent conservé pour cohérence mais aucun appel ne sera déclenché
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

        try:
            user = user_get_by_email(email)
        except Exception as e:
            logger.error(f"[login] Erreur Firebase : {e}")
            error = "Service temporairement indisponible. Réessayez dans quelques instants."
            return render_template("user_login.html", error=error, mode="login")

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]    = user["id"]
            session["user_nom"]   = user["nom"]
            session["user_prenom"] = user["prenom"]
            try:
                user_update_last_login(user["id"])
            except Exception:
                pass  # Non bloquant
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
            try:
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
            except Exception as e:
                logger.error(f"[register] Erreur Firebase : {e}")
                error = "Service temporairement indisponible. Réessayez dans quelques instants."

    return render_template("user_login.html", error=error, mode="register")


@app.route("/logout")
def logout():
    # Nettoyer les états de conversation
    user_id = session.get("user_id")
    session.clear()
    # Support JSON (Flutter mobile) + redirect (web)
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"success": True})
    return redirect(url_for("login"))


# ══════════════════════════════════════════════════════════
#  API MOBILE — Authentification JSON (Flutter)
#  Routes séparées qui acceptent application/json
#  et renvoient du JSON (pas de redirect HTML)
# ══════════════════════════════════════════════════════════

@app.route("/api/mobile/login", methods=["POST"])
def api_mobile_login():
    """Connexion pour l'application Flutter (JSON)."""
    data     = request.get_json(silent=True) or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"success": False, "error": "Email et mot de passe requis."}), 400

    try:
        user = user_get_by_email(email)
    except Exception as e:
        logger.error(f"[api_mobile_login] Firebase error: {e}")
        return jsonify({"success": False, "error": "Service temporairement indisponible."}), 503

    if not user or not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"success": False, "error": "Email ou mot de passe incorrect."}), 401

    session["user_id"]     = user["id"]
    session["user_nom"]    = user.get("nom", "")
    session["user_prenom"] = user.get("prenom", "")
    try:
        user_update_last_login(user["id"])
    except Exception:
        pass

    return jsonify({
        "success": True,
        "user": {
            "uid":       user["id"],
            "email":     user.get("email", email),
            "nom":       user.get("nom", ""),
            "prenom":    user.get("prenom", ""),
            "telephone": user.get("telephone", ""),
        }
    })


@app.route("/api/mobile/register", methods=["POST"])
def api_mobile_register():
    """Inscription pour l'application Flutter (JSON)."""
    data      = request.get_json(silent=True) or {}
    nom       = data.get("nom", "").strip()
    prenom    = data.get("prenom", "").strip()
    email     = data.get("email", "").strip().lower()
    telephone = data.get("telephone", "").strip()
    password  = data.get("password", "")

    if not all([nom, prenom, email, telephone, password]):
        return jsonify({"success": False, "error": "Tous les champs sont obligatoires."}), 400
    if len(password) < 6:
        return jsonify({"success": False, "error": "Le mot de passe doit contenir au moins 6 caractères."}), 400

    try:
        existing = user_get_by_email(email)
        if existing:
            return jsonify({"success": False, "error": "Cet email est déjà utilisé."}), 409

        pwd_hash = generate_password_hash(password)
        colors   = ["#6B2FA0", "#00B4D8", "#E8002D", "#1B5E20", "#1565C0"]
        color    = colors[hash(email) % len(colors)]
        user_id  = user_create(nom, prenom, email, pwd_hash, telephone, color)
    except Exception as e:
        logger.error(f"[api_mobile_register] Firebase error: {e}")
        return jsonify({"success": False, "error": "Service temporairement indisponible."}), 503

    session["user_id"]     = user_id
    session["user_nom"]    = nom
    session["user_prenom"] = prenom

    return jsonify({
        "success": True,
        "user": {
            "uid":       user_id,
            "email":     email,
            "nom":       nom,
            "prenom":    prenom,
            "telephone": telephone,
        }
    })


# ══════════════════════════════════════════════════════════
#  API MOBILE — Données utilisateur (sans session Flask)
#  Toutes ces routes acceptent {"user_id": "..."} en JSON
#  ou le header X-User-ID.  Pas de cookie requis.
# ══════════════════════════════════════════════════════════

def _mobile_user_id() -> str | None:
    """Récupère le user_id depuis le JSON body ou le header X-User-ID."""
    uid = request.headers.get("X-User-ID", "").strip()
    if not uid:
        data = request.get_json(silent=True) or {}
        uid = data.get("user_id", "").strip()
    return uid or None


@app.route("/api/mobile/profile", methods=["GET", "POST"])
def api_mobile_profile():
    uid = _mobile_user_id()
    if not uid:
        return jsonify({"error": "user_id requis"}), 400
    try:
        user = user_get_by_id(uid)
        if not user:
            return jsonify({"error": "Utilisateur introuvable"}), 404
        return jsonify({
            "uid":       uid,
            "email":     user.get("email", ""),
            "nom":       user.get("nom", ""),
            "prenom":    user.get("prenom", ""),
            "telephone": user.get("telephone", ""),
            "created_at": str(user.get("created_at", "")),
        })
    except Exception as e:
        logger.error(f"[api_mobile_profile] {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/mobile/stats", methods=["GET", "POST"])
def api_mobile_stats():
    uid = _mobile_user_id()
    if not uid:
        return jsonify({"error": "user_id requis"}), 400
    try:
        s = user_stats(uid)
        return jsonify({
            "total_conversations":      s.get("total", 0),
            "resolved_conversations":   s.get("resolues", 0),
            "transferred_conversations": s.get("transferees", 0),
            "en_cours":                 s.get("en_cours", 0),
            "avg_rating":               s.get("avg_rating", 0),
        })
    except Exception as e:
        logger.error(f"[api_mobile_stats] {e}")
        return jsonify({"total_conversations": 0, "resolved_conversations": 0,
                        "transferred_conversations": 0, "avg_rating": 0}), 200


@app.route("/api/mobile/history", methods=["GET", "POST"])
def api_mobile_history():
    uid = _mobile_user_id()
    if not uid:
        return jsonify({"error": "user_id requis"}), 400
    try:
        reclamations = reclamations_get_by_user(uid, limit=50)
        conversations = []
        for r in reclamations:
            # Priorité titre : sujet (intent NLU) → apercu (1er msg) → vide
            sujet  = (r.get("sujet") or "").strip()
            apercu = (r.get("apercu") or r.get("last_msg") or "").strip()

            # Exclure les sujets génériques créés automatiquement
            if sujet in ("Chat mobile", "Chat web", "—", "-"):
                sujet = ""

            titre = sujet or apercu or ""
            conversations.append({
                "conv_id":       r.get("reclamation_id", ""),
                "first_message": titre,
                "last_message":  apercu,
                "message_count": r.get("nb_messages", 0),
                "status":        r.get("statut", "en_cours"),
                "created_at":    r.get("created_at", ""),
                "rating":        r.get("satisfaction_rating", 0),
            })
        return jsonify(conversations)
    except Exception as e:
        logger.error(f"[api_mobile_history] {e}")
        return jsonify([]), 200


@app.route("/api/mobile/conversation/<conv_id>", methods=["GET", "POST"])
def api_mobile_conversation(conv_id):
    uid = _mobile_user_id()
    try:
        msgs = messages_get_by_conversation(conv_id)
        result = []
        for m in msgs:
            result.append({
                "role":      m.get("role", "bot"),
                "text":      m.get("content", ""),
                "timestamp": str(m.get("created_at", "")),
            })
        return jsonify({"conv_id": conv_id, "messages": result})
    except Exception as e:
        logger.error(f"[api_mobile_conversation] {e}")
        return jsonify({"conv_id": conv_id, "messages": []}), 200


@app.route("/api/mobile/new_conversation", methods=["POST"])
def api_mobile_new_conversation():
    uid = _mobile_user_id()
    if not uid:
        return jsonify({"error": "user_id requis"}), 400
    try:
        conv_id = conversation_create(uid, sujet="Chat mobile", canal="mobile")
        return jsonify({"conv_session_id": conv_id, "conv_id": conv_id})
    except Exception as e:
        logger.error(f"[api_mobile_new_conversation] {e}")
        import uuid as _uuid
        fallback = str(_uuid.uuid4())
        return jsonify({"conv_session_id": fallback, "conv_id": fallback})


@app.route("/api/mobile/chat", methods=["POST"])
def api_mobile_chat():
    """Chat mobile — identique à /api/user/chat mais sans login_required."""
    data    = request.get_json(silent=True) or {}
    uid     = data.get("user_id", "").strip() or request.headers.get("X-User-ID", "")
    text    = data.get("text", "").strip()
    conv_id = data.get("conv_session_id", "").strip()

    if not text:
        return jsonify({"error": "text requis"}), 400

    # Créer la conversation Firebase si elle n'existe pas encore
    if not conv_id and uid:
        try:
            conv_id = conversation_create(uid, sujet="Chat mobile", canal="mobile")
        except Exception as _ce:
            import uuid as _u
            conv_id = str(_u.uuid4())
            logger.warning(f"[api_mobile_chat] conv_create fallback uuid: {_ce}")

    # Injecter user_id dans la session Flask temporairement
    if uid:
        session["user_id"] = uid

    # ── Stamper le user_id dans l'état de conversation (nécessaire pour
    #    api_internal_agent_reply qui écrit la réponse agent dans le chat) ──
    _mobile_state = _get_conv_state(conv_id)
    if uid and not _mobile_state.get("user_id"):
        _mobile_state["user_id"] = uid

    # ── Auto-gestion du stage "waiting_greeting" pour l'app mobile ─────────
    # L'app mobile affiche le message de bienvenue localement sans passer par
    # le bot. On doit donc faire avancer l'état du serveur vers "initial".
    #
    # RÈGLE :
    #   • Si le message de l'utilisateur EST déjà une salutation (عسلامة…)
    #     → NE PAS envoyer de salutation silencieuse : on laisse process_user_message
    #       traiter le message dans le stage "waiting_greeting" normalement.
    #       (envoyer un 2ᵉ "عسلامة" avant déplacerait le stage vers "initial"
    #        et le vrai "عسلامة" serait ensuite traité par le NLU → intent inconnu
    #        → transfert injustifié !)
    #   • Sinon (premier message = une réclamation directe, ex: "الانترنت مقطوع")
    #     → envoyer "عسلامة" silencieusement pour passer de "waiting_greeting"
    #       à "initial", puis traiter le message réel.
    if _mobile_state.get("stage") == "waiting_greeting":
        if not _is_greeting(text):
            # Utilisateur a sauté la salutation → avancer l'état silencieusement
            try:
                process_user_message(conv_id, "عسلامة")
            except Exception:
                pass  # Non bloquant
        # Si _is_greeting(text) → on laisse process_user_message traiter le salut
        # dans le stage "waiting_greeting" directement (comportement web identique)

    try:
        result = process_user_message(conv_id, text)
    except Exception as e:
        logger.error(f"[api_mobile_chat] process_user_message error: {e}")
        result = {"bot_response": Config.NOT_UNDERSTOOD_MSG,
                  "session_ended": False, "transferred": False,
                  "statut": "en_cours"}

    bot_resp   = result.get("bot_response", "")
    new_statut = result.get("statut", "en_cours")

    # ── Extraire et enrichir les données NLU (identique à /api/user/chat) ─────
    _mob_sess_state = user_conv_state.get(conv_id, {})
    _mob_nlu_data   = _mob_sess_state.get("last_nlu", None)
    if _mob_nlu_data is not None:
        _mob_transferred = bool(result.get("transferred"))
        _mob_nlu_data["escalate"] = _mob_transferred
        _mob_nlu_data["decision"] = (
            "escalade_agent_humain" if _mob_transferred else "reponse_automatique"
        )
        # Wilaya / délégation finales depuis collected_entities
        _mob_ce = _mob_sess_state.get("collected_entities", {}) or {}
        if _mob_ce.get("wilaya"):     _mob_nlu_data["wilaya"]     = _mob_ce["wilaya"]
        if _mob_ce.get("delegation"): _mob_nlu_data["delegation"] = _mob_ce["delegation"]

    # Sauvegarder les messages dans Firebase (avec NLU data, identique au web)
    if uid and conv_id:
        try:
            message_add(conv_id, uid, "user", text, nlu_data=_mob_nlu_data)
            message_add(conv_id, uid, "bot", bot_resp)

            # Mettre à jour statut, sujet ET service_type (identique à api_chat)
            _mob_conv = conversation_get(conv_id) or {}
            new_sujet   = (result.get("sujet")        or "").strip() or _mob_conv.get("sujet", "")
            new_service = (result.get("service_type") or "").strip() or _mob_conv.get("service_type", "")
            _upd = dict(statut=new_statut)
            if new_sujet:
                _upd["sujet"] = new_sujet
            if new_service:
                _upd["service_type"] = new_service
            if result.get("transferred"):
                _upd["was_transferred"] = True
            conversation_update(conv_id, **_upd)
        except Exception as e:
            logger.error(f"[api_mobile_chat] Firebase save error: {e}")

    # ── Transfert vers agent humain → appel Asterisk (identique à /api/user/chat) ──
    ami_called         = False
    asterisk_available = False
    ami_reason         = ""

    if result.get("transferred"):
        # get_current_user() lit session["user_id"] — déjà injecté ci-dessus
        user_info = get_current_user() or {}
        # Fallback : lire directement dans Firebase si session insuffisante
        if not user_info and uid:
            try:
                user_info = user_get_by_id(uid) or {}
            except Exception:
                user_info = {}

        phone     = (user_info.get("telephone") or "").strip()
        u_name    = f"{user_info.get('prenom','')} {user_info.get('nom','')}".strip()
        ticket_id = conv_id[:8] if conv_id else "mobile"

        logger.info(
            f"[Asterisk/mobile] Transfert — user={uid} phone='{phone}' name='{u_name}'"
        )

        _transfer_sess = user_conv_state.get(conv_id, {})
        problem_text   = _build_tts_text(_transfer_sess)

        # Stocker le problème dans Firebase (visible back-office)
        raw_problem = _transfer_sess.get("last_transferred_problem", "") or problem_text
        if raw_problem and conv_id:
            try:
                conversation_update(conv_id, last_problem=raw_problem)
            except Exception as _cp_err:
                logger.warning(f"[Asterisk/mobile] Echec last_problem : {_cp_err}")

        if not phone:
            ami_reason = "no_phone"
            logger.warning(f"[Asterisk/mobile] Numéro manquant pour user {uid}")
        else:
            ami_result         = _asterisk_call(
                caller_number=phone,
                ticket_id=ticket_id,
                user_name=u_name,
                problem_text=problem_text,
                session_id=conv_id,
            )
            ami_called         = ami_result.get("success", False)
            asterisk_available = ami_called
            if ami_called:
                ami_reason = "ok"
            else:
                msg = ami_result.get("message", "").lower()
                ami_reason = (
                    "no_phone" if "manquant" in msg or "phone" in msg
                    else "ami_down"
                )
            logger.info(f"[Asterisk/mobile] {ami_result.get('message', str(ami_result))}")

        # Enregistrer l'état pour le polling call_status
        if conv_id:
            _call_state_mark_transferred(conv_id, ticket_id=conv_id)

    return jsonify({
        "bot_response":       bot_resp,
        "conversation_id":    conv_id,
        "conv_id":            conv_id,
        "session_ended":      result.get("session_ended", False),
        "transferred":        result.get("transferred", False),
        "ami_called":         ami_called,
        "asterisk_available": asterisk_available,
        "ami_reason":         ami_reason,
        "statut":             new_statut,
    })


@app.route("/api/mobile/top_issues", methods=["GET", "POST"])
def api_mobile_top_issues():
    """Principaux problèmes du client — utilisé pour le graphique camembert Flutter."""
    uid = _mobile_user_id()
    if not uid:
        return jsonify({"issues": [], "total": 0}), 200
    try:
        reclamations = reclamations_get_by_user(uid, limit=500)
        counts = {}
        for r in reclamations:
            label = (r.get("sujet") or "").strip()
            if not label or label == "—":
                label = (r.get("service_type") or "").strip()
            if not label or label == "—":
                label = "Autre"
            label = label[:40]
            counts[label] = counts.get(label, 0) + 1
        issues = [{"label": k, "count": v} for k, v in counts.items()]
        issues.sort(key=lambda x: x["count"], reverse=True)
        return jsonify({"issues": issues[:6], "total": len(reclamations)})
    except Exception as e:
        logger.error(f"[api_mobile_top_issues] {e}")
        return jsonify({"issues": [], "total": 0}), 200


@app.route("/api/mobile/rate_conversation", methods=["POST"])
def api_mobile_rate_conversation():
    data    = request.get_json(silent=True) or {}
    conv_id = data.get("conv_id", "").strip()
    rating  = data.get("rating", 0)
    if conv_id:
        try:
            conversation_rate(conv_id, int(rating))
        except Exception as e:
            logger.error(f"[api_mobile_rate] {e}")
    return jsonify({"success": True})


@app.route("/api/mobile/call_status/<conv_id>", methods=["GET", "POST"])
def api_mobile_call_status(conv_id):
    """
    Équivalent mobile de /api/user/call_status — sans @login_required.
    Retourne l'état du transfert vers agent humain :
      - transferred   : True si la conv a été transférée
      - agent_hung_up : True dès que l'agent a raccroché
      - agent_response: Transcription de la réponse de l'agent (si dispo)
      - seconds_since : Secondes écoulées depuis le transfert
      - statut        : Statut courant de la conversation Firebase
    """
    import time as _t
    uid = _mobile_user_id()
    try:
        conv = conversation_get(conv_id)
        if not conv:
            return jsonify({"ok": False, "error": "Conversation introuvable"}), 404

        # Vérification optionnelle : si uid connu, la conv doit lui appartenir
        if uid and conv.get("user_id") and conv.get("user_id") != uid:
            return jsonify({"ok": False, "error": "Accès refusé"}), 403

        conv_statut = (conv.get("statut") or "").strip()
        st = _call_states.get(conv_id)

        # Pas d'état en mémoire (ex: redémarrage serveur) — fallback via Firestore
        if not st:
            was_transferred = bool(conv.get("was_transferred")) or conv_statut == "transferee"
            agent_hung_up   = was_transferred and conv_statut == "resolue"
            return jsonify({
                "ok":             True,
                "transferred":    was_transferred,
                "agent_hung_up":  agent_hung_up,
                "seconds_since":  0,
                "statut":         conv_statut,
                "agent_response": "",
            })

        # Fallback : conv passée à "resolue" → l'agent a raccroché
        if st.get("transferred") and not st.get("agent_hung_up") and conv_statut == "resolue":
            _call_state_mark_hung_up(conv_id, "")
            st = _call_states.get(conv_id, st)

        seconds_since = int(_t.time() - (st.get("transferred_at") or _t.time()))
        return jsonify({
            "ok":             True,
            "transferred":    bool(st.get("transferred")),
            "agent_hung_up":  bool(st.get("agent_hung_up")),
            "seconds_since":  seconds_since,
            "statut":         conv_statut,
            "agent_response": st.get("agent_response", "") if st.get("agent_hung_up") else "",
        })

    except Exception as e:
        logger.error(f"[api_mobile_call_status] {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


# ══════════════════════════════════════════════════════════
#  API MOBILE — TTS (Text-to-Speech, sans session Flask)
#  Même moteur edge-tts que /api/user/tts mais sans @login_required.
#  Utilisé par l'application Flutter pour avoir la même voix
#  (ar-TN-ReemNeural) que l'interface web.
# ══════════════════════════════════════════════════════════

@app.route("/api/mobile/tts", methods=["POST"])
def api_mobile_tts():
    """
    TTS mobile — identique à /api/user/tts mais sans login_required.
    Accepte {"text": "...", "voice": "..."} ou user_id dans le body.
    Retourne un fichier audio MP3 (edge-tts ar-TN-ReemNeural).
    """
    data  = request.get_json(silent=True) or {}
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
        logger.warning("[mobile/tts] edge-tts non installé → TTS indisponible")
        return jsonify({"error": "TTS non disponible"}), 503
    except Exception as e:
        logger.error(f"[mobile/tts] Erreur : {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════
#  API MOBILE — STT (Speech-to-Text, sans session Flask)
#  Même moteur Whisper que /api/user/stt mais sans @login_required.
#  Utilisé par l'application Flutter pour la transcription darija.
# ══════════════════════════════════════════════════════════

@app.route("/api/mobile/stt", methods=["POST"])
def api_mobile_stt():
    """
    STT mobile — identique à /api/user/stt mais sans login_required.
    Reçoit un fichier audio (WebM/WAV/MP4) depuis Flutter,
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
        logger.info(f"[mobile/stt] Transcription : '{text[:80]}'")
        return jsonify({"text": text})

    except ImportError:
        logger.warning("[mobile/stt] faster-whisper non installé → STT indisponible")
        return jsonify({"error": "STT non disponible", "fallback": True}), 503
    except Exception as e:
        logger.error(f"[mobile/stt] Erreur : {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except: pass


# ══════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    try:
        user = get_current_user()
    except Exception as e:
        logger.error(f"[dashboard] Erreur Firebase get_current_user : {e}")
        # On utilise les données de session comme fallback (pas de déconnexion forcée)
        user = {
            "id":     session.get("user_id", ""),
            "nom":    session.get("user_nom", ""),
            "prenom": session.get("user_prenom", ""),
        }
    if not user:
        session.clear()
        return redirect(url_for("login"))

    # Convertir created_at en datetime si c'est une chaîne (cache disque)
    # Le template appelle user.created_at.strftime('%B %Y') → doit être datetime
    from datetime import datetime as _dt
    ca = user.get("created_at")
    if isinstance(ca, str):
        for _fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                     "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                user["created_at"] = _dt.strptime(ca, _fmt)
                break
            except ValueError:
                continue
        else:
            user["created_at"] = _dt.now()   # fallback si format inconnu
    elif ca is None:
        user["created_at"] = _dt.now()

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

    # Stamper le user_id dans la session dès le premier message (pour api_internal_agent_reply)
    _state = _get_conv_state(session_id)
    if not _state.get("user_id"):
        _state["user_id"] = user_id

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

    # Enrichir avec la décision finale (escalade / résolue) pour le back-office
    if _nlu_data is not None:
        _transferred = bool(result.get("transferred"))
        _nlu_data["escalate"] = _transferred
        _nlu_data["decision"] = "escalade_agent_humain" if _transferred else "reponse_automatique"
        # Wilaya / delegation finales depuis collected_entities (plus fiables)
        _ce = _sess_state.get("collected_entities", {}) or {}
        if _ce.get("wilaya"):     _nlu_data["wilaya"]     = _ce["wilaya"]
        if _ce.get("delegation"): _nlu_data["delegation"] = _ce["delegation"]

    # ── Sauvegarder le message utilisateur (avec NLU si disponible) ──
    message_add(conv_id_db, user_id, "user", user_text, nlu_data=_nlu_data)

    # ── Sauvegarder la réponse bot ────────────────────────
    message_add(conv_id_db, user_id, "bot", bot_resp)

    # ── Mettre à jour la conversation Firebase ───────────
    new_statut  = result.get("statut", "en_cours")
    new_sujet   = result.get("sujet")   or conv.get("sujet",        "")
    new_service = result.get("service_type") or conv.get("service_type", "")

    _upd_fields = dict(
        statut=new_statut,
        sujet=new_sujet,
        service_type=new_service,
    )
    # Marquer la conversation comme ayant été transférée — permet au
    # front-end / à /api/user/call_status de déduire l'état après un
    # redémarrage serveur ou si la mémoire in-memory est vidée.
    if result.get("transferred"):
        _upd_fields["was_transferred"] = True
    conversation_update(conv_id_db, **_upd_fields)

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

        # ── Construire le texte TTS selon le type de problème ──────
        # Problème connu (dans les 14 types du dataset) :
        #   → TTS = suggested_action + dernier message client
        # Problème inconnu :
        #   → TTS = message brut du client en arabe
        _transfer_sess = user_conv_state.get(session_id, {})
        problem_text   = _build_tts_text(_transfer_sess)

        # Stocker le problème dans Firebase pour que le back-office puisse l'afficher
        raw_problem = _transfer_sess.get("last_transferred_problem", "") or problem_text
        if raw_problem:
            try:
                conversation_update(conv_id_db, last_problem=raw_problem)
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
                session_id=conv_id_db,   # clé complète de user_conv_state → learning fonctionne
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

    # Si la conv a été transférée, enregistrer l'état pour le suivi
    # "agent a raccroché" (utilisé par /api/user/call_status côté front-end).
    # Note : on enregistre même si ami_called=False — ainsi le panneau
    # d'évaluation pourra s'afficher dès que le statut de la conv passe
    # à "resolue" (fallback robuste si Whisper/STT n'a pas tourné).
    if result.get("transferred") and conv_id_db:
        _call_state_mark_transferred(conv_id_db, ticket_id=conv_id_db)

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
    # Extraire l'intent AVANT que la session soit réinitialisée (pending_intent encore présent)
    learned = False
    if problem_text:
        _user_intent = (sess.get("pending_intent") or "").strip()
        _session_learn_store(sess, problem_text, response, intent=_user_intent)
        learned = True
        logger.info(
            f"[human_response] Appris : '{problem_text[:60]}' → '{response[:60]}' "
            f"(intent='{_user_intent}')"
        )

    # Remettre la session en état initial pour que l'utilisateur puisse continuer.
    # solution_given = True → si le user dit "merci", le bot clôture proprement
    # (identique à tous les autres points de résolution de la conversation).
    sess["solution_given"]           = True   # permet "merci" après réponse agent
    sess["transferred"]              = False
    sess["is_unknown_problem"]       = False
    sess["stage"]                    = "initial"
    sess["pending_intent"]           = ""
    sess["original_problem"]         = ""   # Fix TTS : effacer après réponse agent
    sess["last_transferred_problem"] = ""

    return jsonify({"success": True, "learned": learned})


# ══════════════════════════════════════════════════════════
#  API INTERNE — Réponse agent (appelée par app.py back-office)
#  Pas de login_required : accès par secret interne uniquement
# ══════════════════════════════════════════════════════════

_INTERNAL_SECRET = "tt_backoffice_2026"   # partagé avec app.py

# ──────────────────────────────────────────────────────────
# Suivi des appels transférés (in-memory) :
#   conv_id  → {
#     "transferred":     True si l'appel a été lancé,
#     "agent_hung_up":   True quand l'agent raccroche (réponse reçue),
#     "transferred_at":  timestamp epoch du transfert,
#     "hung_up_at":      timestamp epoch quand l'agent raccroche,
#     "agent_response":  texte transcrit (facultatif),
#     "ticket_id":       identifiant ticket correspondant,
#   }
# Utilisé par /api/user/call_status pour que le front-end détecte
# la fin d'appel et affiche l'évaluation étoiles à ce moment-là.
# ──────────────────────────────────────────────────────────
_call_states: dict = {}


def _call_state_mark_transferred(conv_id: str, ticket_id: str = ""):
    """Marque une conversation comme transférée (appel agent en cours)."""
    import time as _t
    if not conv_id:
        return
    _call_states[conv_id] = {
        "transferred":     True,
        "agent_hung_up":   False,
        "transferred_at":  _t.time(),
        "hung_up_at":      None,
        "agent_response":  "",
        "ticket_id":       ticket_id or conv_id,
    }


def _call_state_mark_hung_up(conv_id_or_ticket: str, response_text: str = ""):
    """
    Marque un appel comme terminé (agent a raccroché).
    Accepte soit un conv_id, soit un ticket_id.
    """
    import time as _t
    if not conv_id_or_ticket:
        return
    # Rechercher par clé directe OU par ticket_id
    target_key = None
    if conv_id_or_ticket in _call_states:
        target_key = conv_id_or_ticket
    else:
        for k, st in _call_states.items():
            if st.get("ticket_id") == conv_id_or_ticket:
                target_key = k
                break
    if target_key:
        _call_states[target_key]["agent_hung_up"]  = True
        _call_states[target_key]["hung_up_at"]     = _t.time()
        _call_states[target_key]["agent_response"] = (response_text or "")[:200]

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

    data                  = request.get_json(silent=True) or {}
    ticket_id             = data.get("ticket_id", "")
    response              = (data.get("response") or "").strip()
    sid                   = data.get("session_id", "")
    # problem_text transmis par app.py (texte réel du client, extrait du ticket)
    payload_problem_text  = (data.get("problem_text") or "").strip()

    # ── Cas "agent a raccroché sans parler / Whisper vide / timeout" ──
    # On accepte un `response` vide : on signale juste la fin d'appel au
    # front-end (via _call_state_mark_hung_up + statut='resolue') sans
    # ajouter de message dans le chat. Le panneau d'évaluation s'ouvrira
    # à la prochaine itération du polling côté client.
    if not response:
        try:
            conversation_update(ticket_id, statut="resolue")
        except Exception as _e:
            logger.warning(f"[internal_agent_reply] Echec mise à jour statut (réponse vide) : {_e}")
        try:
            _call_state_mark_hung_up(sid or ticket_id, "")
            logger.info(
                f"[internal_agent_reply] Appel marqué terminé SANS transcription "
                f"(ticket={ticket_id}) — panneau d'évaluation déclenché côté client"
            )
        except Exception as _e:
            logger.warning(f"[internal_agent_reply] Echec marquage appel terminé (réponse vide) : {_e}")
        return jsonify({"success": True, "hung_up_silent": True})

    # Résoudre le ticket côté Firestore
    try:
        transfer.resolve_ticket(ticket_id, response)
    except Exception as e:
        logger.warning(f"[internal_agent_reply] Erreur resolve_ticket({ticket_id}) : {e}")

    # Récupérer la session de conversation en mémoire
    sess = user_conv_state.get(sid, {})

    # Déterminer le texte du problème :
    # Priorité 1 : last_transferred_problem de la session (texte exact qui a déclenché le transfert)
    # Priorité 2 : problem_text transmis par app.py dans le payload (extrait du ticket)
    # Priorité 3 : dernier message utilisateur de l'historique de session
    history      = sess.get("history", [])
    last_user    = next((t for r, t in reversed(history) if r == "user"), "")
    problem_text = (
        sess.get("last_transferred_problem")
        or payload_problem_text
        or last_user
    )

    # Déterminer l'intent associé à ce problème :
    # Priorité 1 : pending_intent de la session (le plus fiable, issu de la clarification)
    # Priorité 2 : last_nlu intent (NLU direct du moment du transfert)
    # Priorité 3 : intent transmis par app.py dans le payload (extrait du ticket côté app.py)
    # Priorité 4 : intent lu directement dans le ticket (via transfer.get_ticket)
    # Stocké dans l'entrée pour deux usages :
    #   A. force_num check à la récupération (indépendant du NLU courant)
    #   B. intent-boost scoring dans _find_session_learned_pair
    _ticket_intent = ""
    try:
        _tkt_data = transfer.get_ticket(ticket_id) if ticket_id else {}
        _ticket_intent = (_tkt_data.get("intent", "") or "").strip().replace("unknown", "").strip()
    except Exception:
        pass
    _learn_intent = (
        (sess.get("pending_intent") or "").strip()
        or (sess.get("last_nlu") or {}).get("intent", "").strip()
        or (data.get("intent") or "").strip()   # transmis par app.py
        or _ticket_intent                        # lu dans le ticket (fallback ultime)
    )

    # Stocker la réponse apprise en mémoire éphémère (reset au redémarrage)
    learned = False
    if problem_text:
        _session_learn_store(sess, problem_text, response, intent=_learn_intent)
        learned = True
        logger.info(
            f"[internal_agent_reply] ✅ Bot apprend : "
            f"intent='{_learn_intent}' | '{problem_text[:60]}' → '{response[:60]}'"
        )
    else:
        logger.warning(
            f"[internal_agent_reply] ⚠️  problem_text vide — session {sid!r} introuvable "
            f"et payload_problem_text='{payload_problem_text}'. "
            "Réponse stockée avec ticket_id comme clé (fallback dégradé)."
        )
        # Dernier recours : stocker dans le store global avec ticket_id comme clé
        # (peu utile pour la correspondance, mais garde la trace de l'apprentissage)
        _session_learn_store({}, ticket_id or "unknown", response, intent=_learn_intent)
        learned = True

    # Écrire la réponse de l'agent comme message bot dans le chat Firebase
    # → le client voit la solution dans l'interface ; le bot a aussi appris
    _uid = sess.get("user_id", "") if sess else ""
    if sid and _uid:
        try:
            message_add(sid, _uid, "bot", response)
            logger.info(f"[internal_agent_reply] Réponse agent écrite dans le chat ({sid[:8]}…)")
        except Exception as _me:
            logger.warning(f"[internal_agent_reply] Echec écriture message agent : {_me}")

    # Remettre la session en état initial
    if sess:
        sess["solution_given"]           = True   # permet "merci" après réponse agent
        sess["transferred"]              = False
        sess["is_unknown_problem"]       = False
        sess["stage"]                    = "initial"
        sess["pending_intent"]           = ""
        sess["original_problem"]         = ""   # Fix TTS : effacer au reset transfert
        sess["last_transferred_problem"] = ""

    # Mettre à jour le statut Firebase
    try:
        conversation_update(ticket_id, statut="resolue")
    except Exception as _e:
        logger.warning(f"[internal_agent_reply] Echec mise à jour statut : {_e}")

    # ── Marquer l'appel comme terminé (agent a raccroché) ─────────
    # Le client pourra évaluer via le panneau étoiles (polling côté front-end).
    try:
        _call_state_mark_hung_up(sid or ticket_id, response)
        logger.info(f"[internal_agent_reply] Appel marqué terminé (ticket={ticket_id})")
    except Exception as _e:
        logger.warning(f"[internal_agent_reply] Echec marquage appel terminé : {_e}")

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
        # Ajouter les statistiques de satisfaction à partir des réclamations
        try:
            recs = reclamations_get_by_user(session["user_id"], limit=500)
            rated  = [r for r in recs if (r.get("satisfaction_rating") or 0) > 0]
            if rated:
                avg_rating = round(sum(r["satisfaction_rating"] for r in rated) / len(rated), 1)
            else:
                avg_rating = 0.0
            stats["satisfaction_avg"]   = avg_rating
            stats["satisfaction_count"] = len(rated)
        except Exception as _se:
            logger.warning(f"[api_stats] Erreur satisfaction : {_se}")
            stats["satisfaction_avg"]   = 0.0
            stats["satisfaction_count"] = 0
        return jsonify(stats)
    except Exception as e:
        logger.error(f"[api_stats] Erreur Firebase : {e}", exc_info=True)
        return jsonify({"total": 0, "resolues": 0, "transferees": 0, "en_cours": 0,
                        "satisfaction_avg": 0.0, "satisfaction_count": 0,
                        "error": str(e)}), 500


@app.route("/api/user/top_issues")
@login_required
def api_top_issues():
    """
    Retourne les principaux problèmes (sujets) de l'utilisateur,
    agrégés par sujet et triés par fréquence décroissante.
    Utilisé pour la liste + camembert sur le dashboard utilisateur.
    """
    try:
        user_id = session["user_id"]
        reclamations = reclamations_get_by_user(user_id, limit=500)

        # Agrégation : on préfère 'sujet', sinon 'service_type', sinon 'Autre'
        counts = {}
        for r in reclamations:
            label = (r.get("sujet") or "").strip()
            if not label or label == "—":
                label = (r.get("service_type") or "").strip()
            if not label or label == "—":
                label = "Autre"
            # Joliser : majuscule initiale
            label = label[:40]
            counts[label] = counts.get(label, 0) + 1

        issues = [{"label": k, "count": v} for k, v in counts.items()]
        issues.sort(key=lambda x: x["count"], reverse=True)

        return jsonify({"issues": issues, "total": len(reclamations)})
    except Exception as e:
        logger.error(f"[api_top_issues] Erreur Firebase : {e}", exc_info=True)
        return jsonify({"issues": [], "total": 0, "error": str(e)}), 500


@app.route("/api/user/call_status/<conv_id>")
@login_required
def api_call_status(conv_id):
    """
    Retourne l'état d'un appel transféré :
      - transferred   : True si l'appel a été lancé
      - agent_hung_up : True dès que l'agent raccroche (réponse reçue)
      - seconds_since : durée écoulée depuis le transfert
      - statut        : statut courant de la conv (pour fallback front-end)

    Stratégie de détection "agent a raccroché" (robuste) :
      1. Signal primaire : _call_states[conv_id].agent_hung_up=True
         (positionné par api_internal_agent_reply quand Whisper transcrit la réponse)
      2. Fallback : la conv a été marquée comme transférée puis son statut Firebase
         a basculé de 'transferee' → 'resolue' (agent a raccroché même sans audio).
    """
    import time as _t
    try:
        # Vérifier que la conversation appartient bien à l'utilisateur
        conv = conversation_get(conv_id)
        if not conv or conv.get("user_id") != session["user_id"]:
            return jsonify({"ok": False, "error": "Non trouvé"}), 404

        conv_statut = (conv.get("statut") or "").strip()
        st = _call_states.get(conv_id)

        # Pas d'état en mémoire : peut-être redémarrage serveur, mais la conv
        # a peut-être été transférée puis résolue → on considère l'appel terminé
        # seulement si on a une preuve explicite (statut = 'resolue' suffit si
        # on a un champ "was_transferred" sur la conv ; sinon on se contente de
        # reporter l'absence de suivi).
        if not st:
            was_transferred = bool(conv.get("was_transferred")) or conv_statut == "transferee"
            agent_hung_up   = was_transferred and conv_statut == "resolue"
            return jsonify({
                "ok":            True,
                "transferred":   was_transferred,
                "agent_hung_up": agent_hung_up,
                "seconds_since": 0,
                "statut":        conv_statut,
            })

        # Fallback : si la conv est passée à "resolue" alors qu'elle était
        # marquée transférée, l'agent a forcément raccroché (même si Whisper
        # n'a rien capté ou si le watcher est en timeout).
        if st.get("transferred") and not st.get("agent_hung_up") and conv_statut == "resolue":
            _call_state_mark_hung_up(conv_id, "")
            st = _call_states.get(conv_id, st)

        seconds_since = int(_t.time() - (st.get("transferred_at") or _t.time()))
        return jsonify({
            "ok":             True,
            "transferred":    bool(st.get("transferred")),
            "agent_hung_up":  bool(st.get("agent_hung_up")),
            "seconds_since":  seconds_since,
            "statut":         conv_statut,
            "agent_response": st.get("agent_response", "") if st.get("agent_hung_up") else "",
        })
    except Exception as e:
        logger.error(f"[api_call_status] Erreur : {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/user/rate_conversation", methods=["POST"])
@login_required
def api_rate_conversation():
    """
    Enregistre la note (1-5) et un feedback optionnel d'une conversation.
    Body JSON : {"conv_id": "...", "rating": 1-5, "feedback": "..." }
    """
    try:
        data = request.get_json(silent=True) or {}
        conv_id  = (data.get("conv_id") or "").strip()
        rating   = data.get("rating")
        feedback = data.get("feedback") or ""

        if not conv_id:
            return jsonify({"ok": False, "error": "conv_id manquant"}), 400

        # Vérification : la conversation appartient bien à l'utilisateur courant
        conv = conversation_get(conv_id)
        if not conv or conv.get("user_id") != session["user_id"]:
            return jsonify({"ok": False, "error": "Conversation introuvable"}), 404

        ok = conversation_rate(conv_id, rating, feedback)
        if not ok:
            return jsonify({"ok": False, "error": "Note invalide (1-5 attendu)"}), 400

        return jsonify({"ok": True, "rating": int(rating)})
    except Exception as e:
        logger.error(f"[api_rate_conversation] Erreur : {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


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
#  API VOCAL — STT pour la voix de l'AGENT humain
# ══════════════════════════════════════════════════════════

# Prompt STT spécialisé : couvre les 5 types de problèmes connus + problèmes inconnus
# Optimisé pour la darija tunisienne et le vocabulaire des agents TT.
# ── Stratégie : phrases complètes typiques d'un agent + toutes les expressions
#    fréquentes → guide Whisper vers la bonne transcription même avec accent régional.
_AGENT_STT_PROMPT = (
    # Contexte général
    "وكيل دعم تقني في تليكوم تونس يشرح الحل بالدارجة التونسية. "
    # ── تغيير الخدمة ─────────────────────────────────────────────────────────────
    "تغيير الخدمة: 'نعملك تحويل من ADSL لفيبر'، 'نرفعلك السرعة'، "
    "'نبدّل باقتك'، 'نحدّث الاشتراك'، 'الخدمة الجديدة تبدأ من بكري'، "
    "'يلزمك تمشي للوكالة تجيب بطاقتك'، 'نسجّل طلب التغيير'، "
    # ── مشكلة في التجوال ─────────────────────────────────────────────────────────
    "مشكلة في التجوال: 'نفعّل التجوال على خطك'، 'روامينق موش مفعّل'، "
    "'يلزمك تتصل بـ 1298 قبل السفر'، 'نبعث إشعار التفعيل'، "
    "'التجوال يخدم في أوروبا والمغرب'، 'السرعة في الخارج محدودة'، "
    # ── اعتراض على الفاتورة ──────────────────────────────────────────────────────
    "اعتراض على الفاتورة: 'نراجع الفاتورة معك'، 'المبلغ فيه غلطة'، "
    "'نعملك تخفيض'، 'نرجعلك الفرق'، 'الفاتورة فيها استهلاك زيادة'، "
    "'نفتح ملف اعتراض'، 'نصحح الفاتورة خلال 48 ساعة'، "
    "'ما فيهاش مشكلة نصفّي معك الحساب'، 'الفاتورة صحيحة لأن...'، "
    # ── انقطاع الانترنات ─────────────────────────────────────────────────────────
    "انقطاع الانترنات: 'نبعث فريق تقني يجيك'، 'عيطلك التقني اليوم'، "
    "'علاش ما تعيّد تشغيل الباكس'، 'الكابل الخارجي مقطوع'، "
    "'المشكل في البنية التحتية'، 'نسجّل شكوى قطع الانترنت'، "
    "'الخط يرجع يخدم باش نصلح العطب'، 'نتابع معك الموضوع'، "
    # ── تأخير في التركيب ─────────────────────────────────────────────────────────
    "تأخير في التركيب: 'موعد التقني يوم الخميس'، 'التقني يجيك من 9 لـ 12'، "
    "'نحجزلك موعد جديد'، 'الطلب مسجّل عندنا'، 'التركيب يأخذ يومين'، "
    "'نبعث تقني للتركيب'، 'نتابع ملف التركيب'، 'رقم طلبك هو'، "
    # ── مشاكل أخرى / غير معروفة ──────────────────────────────────────────────────
    "مشاكل أخرى: 'نسجّل مشكلتك'، 'نحيلك للقسم المختص'، "
    "'نرجع نتصل بيك خلال 24 ساعة'، 'الحل هو'، 'يلزمك'، 'اش نعملوا'، "
    # ── مفردات أرقام وأسماء أماكن ────────────────────────────────────────────────
    "رقم الطلب، رقم المعاملة، رقم الخط، رقم الحساب. "
    "صفاقس، سوسة، تونس، نابل، المنستير، بنزرت، قفصة، قابس، أريانة، منوبة، "
    "مدنين، تطاوين، القيروان، سيدي بوزيد، زغوان، سليانة، الكاف، جندوبة، باجة، "
    "توزر، قبلي، المهدية."
)


@app.route("/api/voice_agent", methods=["POST"])
def api_voice_agent():
    """
    STT optimisé pour la voix de l'agent humain (back-office).

    STRATÉGIE : proxy vers app.py (:5000/api/voice_agent) en priorité.
    Le modèle Whisper d'app.py est pré-chargé au démarrage, toujours chaud,
    et utilise les paramètres optimaux (beam_size=7, best_of=5, multi-temp,
    no_speech_threshold=0.9, prompt agent spécialisé).
    Si app.py n'est pas joignable → fallback local avec les mêmes paramètres.
    """
    if "audio" not in request.files:
        return jsonify({"error": "Fichier audio manquant"}), 400

    audio_file = request.files["audio"]
    audio_bytes = audio_file.read()
    ct          = audio_file.content_type or "audio/webm"
    filename    = audio_file.filename    or "audio.webm"

    # ── Proxy vers app.py (port 5000) ─────────────────────────────────────────
    import urllib.request as _ur
    import urllib.error   as _ue
    try:
        import io
        boundary = b"----UserAppSTTBoundary"
        body = (
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="audio"; filename="' +
            filename.encode() + b'"\r\n' +
            b"Content-Type: " + ct.encode() + b"\r\n\r\n" +
            audio_bytes + b"\r\n" +
            b"--" + boundary + b"--\r\n"
        )
        _req = _ur.Request(
            "http://127.0.0.1:5000/api/voice_agent",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"},
            method="POST",
        )
        with _ur.urlopen(_req, timeout=30) as _r:
            import json as _json
            result = _json.loads(_r.read().decode("utf-8"))
            transcript = result.get("transcript", "")
            logger.info(f"[voice_agent] Proxy app.py → '{transcript[:80]}'")
            return jsonify({"transcript": transcript})
    except Exception as _proxy_err:
        logger.warning(
            f"[voice_agent] Proxy app.py indisponible ({_proxy_err}) — fallback local"
        )

    # ── Fallback local (app.py non joignable) ─────────────────────────────────
    suffix = ".webm"
    if "wav"  in ct: suffix = ".wav"
    elif "mp4" in ct or "mp4a" in ct: suffix = ".mp4"
    elif "ogg" in ct: suffix = ".ogg"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        model = _get_whisper()
        segments, info = model.transcribe(
            tmp_path,
            language=Config.STT_LANGUAGE,
            beam_size=7,
            best_of=5,
            vad_filter=False,
            initial_prompt=_AGENT_STT_PROMPT,
            temperature=[0.0, 0.2, 0.4],
            condition_on_previous_text=True,
            no_speech_threshold=0.9,
            compression_ratio_threshold=2.8,
            word_timestamps=False,
        )
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        logger.info(
            f"[voice_agent] Fallback local → '{transcript[:80]}' "
            f"[lang={info.language} prob={info.language_probability:.2f}]"
        )
        return jsonify({"transcript": transcript})

    except ImportError:
        logger.warning("faster-whisper non installé → STT agent indisponible")
        return jsonify({"error": "STT non disponible", "fallback": True}), 503
    except Exception as e:
        logger.error(f"[voice_agent] Erreur : {e}", exc_info=True)
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
#  GESTIONNAIRES D'ERREURS GLOBAUX
# ══════════════════════════════════════════════════════════

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"[500] Erreur interne : {e}", exc_info=True)
    # Si la requête attend du JSON → répondre en JSON
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Erreur interne du serveur", "detail": str(e)}), 500
    # Sinon → page d'erreur simple
    return render_template("user_login.html",
                           error="Une erreur interne est survenue. Veuillez réessayer.",
                           mode="login"), 500


@app.errorhandler(Exception)
def unhandled_exception(e):
    logger.error(f"[Exception non gérée] {type(e).__name__}: {e}", exc_info=True)
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"error": "Erreur interne du serveur", "detail": str(e)}), 500
    return render_template("user_login.html",
                           error="Une erreur interne est survenue. Veuillez réessayer.",
                           mode="login"), 500


# ══════════════════════════════════════════════════════════
#  LANCEMENT
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  Espace Client TT — http://localhost:5001")
    logger.info("=" * 55)
    app.run(host="0.0.0.0", port=5001, debug=False)
