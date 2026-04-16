#!/usr/bin/env python3
# ============================================================
#  firebase_config.py — Connexion Firebase Firestore
#  Remplace db_config.py (MySQL EasyPHP)
#
#  SETUP REQUIS (une seule fois) :
#    1. Aller sur https://console.firebase.google.com
#    2. Créer un projet → Firestore Database → "Start in production mode"
#    3. Project Settings → Service Accounts → Generate new private key
#    4. Sauvegarder le fichier JSON sous :  PFE/serviceAccountKey.json
#    5. pip install firebase-admin
# ============================================================

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("firebase_config")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE_DIR, "serviceAccountKey.json")

# ── Initialisation Firebase (une seule fois) ──────────────
_db = None

def get_db():
    """Retourne le client Firestore (initialise Firebase si besoin)."""
    global _db
    if _db is not None:
        return _db
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if not os.path.exists(CRED_FILE):
                raise FileNotFoundError(
                    f"Fichier serviceAccountKey.json introuvable dans : {BASE_DIR}\n"
                    "  → Téléchargez-le depuis Firebase Console > Project Settings > Service Accounts"
                )
            cred = credentials.Certificate(CRED_FILE)
            firebase_admin.initialize_app(cred)

        _db = firestore.client()
        logger.info("Firebase Firestore connecté.")
        return _db

    except ImportError:
        raise ImportError("firebase-admin non installé. Lancez : pip install firebase-admin")


def init_firebase() -> bool:
    """Vérifie la connexion Firestore. Retourne True si OK."""
    try:
        db = get_db()
        # Test ping : liste les collections
        list(db.collections())
        logger.info("Firebase Firestore : connexion OK")
        return True
    except Exception as e:
        logger.critical(f"Firebase Firestore ERREUR : {e}")
        return False


# ════════════════════════════════════════════════════════════
#  HELPERS — Conversion Firestore ↔ dict Python
# ════════════════════════════════════════════════════════════

def _ts(dt) -> str:
    """Convertit un datetime (Firestore ou Python) en string lisible."""
    if dt is None:
        return ""
    if hasattr(dt, "strftime"):
        return dt.strftime("%d/%m/%Y %H:%M")
    return str(dt)


def _now():
    return datetime.now(timezone.utc)


# ════════════════════════════════════════════════════════════
#  USERS
# ════════════════════════════════════════════════════════════

def user_create(nom: str, prenom: str, email: str,
                password_hash: str, telephone: str = "",
                avatar_color: str = "#5B1FBE") -> str:
    """Crée un utilisateur et retourne son document ID Firebase."""
    db = get_db()
    from firebase_admin import firestore as _fs
    doc_ref = db.collection("users").document()
    doc_ref.set({
        "nom":           nom,
        "prenom":        prenom,
        "email":         email.lower().strip(),
        "password_hash": password_hash,
        "telephone":     telephone,
        "avatar_color":  avatar_color,
        "is_active":     True,
        "last_login":    None,
        "created_at":    _now(),
    })
    return doc_ref.id


def user_get_by_email(email: str) -> dict | None:
    """Retourne l'utilisateur avec cet email (ou None)."""
    db = get_db()
    docs = (db.collection("users")
              .where("email", "==", email.lower().strip())
              .where("is_active", "==", True)
              .limit(1)
              .stream())
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        return d
    return None


def user_get_by_id(user_id) -> dict | None:
    """Retourne l'utilisateur par son ID Firebase (ou None)."""
    if user_id is None:
        return None
    # Sécurité : Firebase exige une string (l'ancienne session MySQL stockait un int)
    user_id = str(user_id)
    # Un ID Firebase valide ne contient pas que des chiffres
    if user_id.isdigit():
        return None
    db = get_db()
    doc = db.collection("users").document(user_id).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = doc.id
        return d
    return None


def user_update_last_login(user_id: str):
    db = get_db()
    db.collection("users").document(user_id).update({"last_login": _now()})


def user_update_profile(user_id: str, **kwargs):
    db = get_db()
    db.collection("users").document(user_id).update(kwargs)


# ════════════════════════════════════════════════════════════
#  CONVERSATIONS
# ════════════════════════════════════════════════════════════

def conversation_create(user_id: str,
                        titre: str = "Nouvelle conversation",
                        statut: str = "en_cours",
                        sujet: str = "",
                        service_type: str = "") -> str:
    """Crée une conversation et retourne son document ID Firebase."""
    db = get_db()
    now = _now()
    doc_ref = db.collection("conversations").document()
    doc_ref.set({
        "user_id":      user_id,
        "titre":        titre,
        "statut":       statut,
        "sujet":        sujet,
        "service_type": service_type,
        "created_at":   now,
        "updated_at":   now,
    })
    return doc_ref.id


def conversation_get(conv_id: str) -> dict | None:
    db = get_db()
    doc = db.collection("conversations").document(conv_id).get()
    if doc.exists:
        d = doc.to_dict()
        d["id"] = doc.id
        return d
    return None


def conversation_update(conv_id: str, **kwargs):
    db = get_db()
    kwargs["updated_at"] = _now()
    db.collection("conversations").document(conv_id).update(kwargs)


def conversations_get_by_user(user_id: str, limit: int = 50) -> list:
    """Retourne les conversations d'un user, triées par date décroissante.
    Tri en Python pour éviter les index composites Firestore."""
    db = get_db()
    # Pas de order_by ici → évite l'index composite where+order_by
    docs = (db.collection("conversations")
              .where("user_id", "==", user_id)
              .stream())
    result = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        result.append(d)
    # Tri côté Python par created_at décroissant
    result.sort(key=lambda x: x.get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc),
                reverse=True)
    return result[:limit]


# ════════════════════════════════════════════════════════════
#  MESSAGES
# ════════════════════════════════════════════════════════════

def message_add(conv_id: str, user_id: str,
                role: str, content: str,
                nlu_data: dict = None) -> str:
    """Ajoute un message (role='user' ou 'bot') dans une conversation.
    nlu_data : dict optionnel avec intent, confidence, sentiment, service_type
               (uniquement pour les messages 'user').
    """
    db = get_db()
    doc_ref = db.collection("messages").document()
    doc = {
        "conversation_id": conv_id,
        "user_id":         user_id,
        "role":            role,       # "user" | "bot"
        "content":         content,
        "created_at":      _now(),
    }
    if nlu_data and role == "user":
        doc["nlu_intent"]     = nlu_data.get("intent", "")
        doc["nlu_confidence"] = nlu_data.get("confidence", 0)
        doc["nlu_sentiment"]  = nlu_data.get("sentiment", "")
        doc["nlu_service"]    = nlu_data.get("service_type", "")
    doc_ref.set(doc)
    return doc_ref.id


def messages_get_by_conversation(conv_id: str) -> list:
    """Retourne tous les messages d'une conversation, triés par date.
    Tri en Python pour éviter les index composites Firestore."""
    db = get_db()
    docs = (db.collection("messages")
              .where("conversation_id", "==", conv_id)
              .stream())
    result = []
    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        result.append(d)
    # Tri côté Python par created_at croissant (ordre chronologique)
    result.sort(key=lambda x: x.get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc))
    return result


# ════════════════════════════════════════════════════════════
#  STATISTIQUES
# ════════════════════════════════════════════════════════════

def user_stats(user_id: str) -> dict:
    """Retourne les stats réclamations de l'utilisateur."""
    db = get_db()
    docs = db.collection("conversations").where("user_id", "==", user_id).stream()

    total = resolues = transferees = en_cours = 0
    for doc in docs:
        statut = doc.to_dict().get("statut", "")
        total += 1
        if statut == "resolue":
            resolues += 1
        elif statut == "transferee":
            transferees += 1
        else:
            en_cours += 1

    return {
        "total":       total,
        "resolues":    resolues,
        "transferees": transferees,
        "en_cours":    en_cours,
    }


# ════════════════════════════════════════════════════════════
#  HISTORIQUE RÉCLAMATIONS (vue équivalente à v_user_reclamations)
# ════════════════════════════════════════════════════════════

def reclamations_get_by_user(user_id: str, limit: int = 50) -> list:
    """
    Retourne les réclamations enrichies (avec aperçu) pour l'historique.
    Équivalent à la vue SQL v_user_reclamations.
    Tri en Python pour éviter les index composites Firestore.
    """
    db = get_db()
    # Récupérer toutes les conversations de l'user (sans order_by)
    convs_docs = list(db.collection("conversations")
                        .where("user_id", "==", user_id)
                        .stream())

    # Trier en Python par created_at décroissant, puis limiter
    convs_docs.sort(
        key=lambda d: d.to_dict().get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True
    )
    convs_docs = convs_docs[:limit]

    result = []
    for conv_doc in convs_docs:
        conv  = conv_doc.to_dict()
        c_id  = conv_doc.id

        # Récupérer les messages de cette conversation (sans order_by)
        msgs_docs = list(db.collection("messages")
                           .where("conversation_id", "==", c_id)
                           .stream())
        # Trier en Python par created_at croissant
        msgs_docs.sort(
            key=lambda d: d.to_dict().get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)
        )

        nb_messages = len(msgs_docs)

        # Aperçu = premier message utilisateur
        apercu = ""
        for m_doc in msgs_docs:
            md = m_doc.to_dict()
            if md.get("role") == "user":
                apercu = md.get("content", "")[:120]
                break

        result.append({
            "reclamation_id": c_id,
            "sujet":          conv.get("sujet")        or "—",
            "service_type":   conv.get("service_type") or "—",
            "statut":         conv.get("statut")       or "en_cours",
            "created_at":     _ts(conv.get("created_at")),
            "updated_at":     _ts(conv.get("updated_at")),
            "nb_messages":    nb_messages,
            "apercu":         apercu,
        })

    return result


# ════════════════════════════════════════════════════════════
#  BACK-OFFICE — Toutes les conversations (admin)
# ════════════════════════════════════════════════════════════

def conversations_get_all_recent(limit: int = 30) -> list:
    """
    Retourne les conversations les plus recentes de TOUS les utilisateurs.
    Utilisee par l'interface back-office de app.py pour le monitoring live.

    Chaque entree contient :
        id, user_id, user_name, statut, sujet, service_type,
        created_at, updated_at, nb_messages, apercu, last_msg, last_role
    """
    db = get_db()

    docs = list(db.collection("conversations").stream())

    def _sort_key(doc):
        d = doc.to_dict()
        return d.get("updated_at") or d.get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)

    docs.sort(key=_sort_key, reverse=True)
    docs = docs[:limit]

    if not docs:
        return []

    user_ids   = list({d.to_dict().get("user_id", "") for d in docs if d.to_dict().get("user_id")})
    user_names: dict = {}
    for uid in user_ids:
        try:
            u = db.collection("users").document(uid).get()
            if u.exists:
                ud   = u.to_dict()
                name = f"{ud.get('prenom', '')} {ud.get('nom', '')}".strip() or uid[:8]
                user_names[uid] = name
        except Exception:
            user_names[uid] = uid[:8]

    result = []
    for doc in docs:
        conv  = doc.to_dict()
        c_id  = doc.id
        uid   = conv.get("user_id", "")

        try:
            msgs_docs = list(db.collection("messages")
                               .where("conversation_id", "==", c_id)
                               .stream())
            msgs_docs.sort(
                key=lambda d: d.to_dict().get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)
            )
            nb_messages = len(msgs_docs)
            apercu      = ""
            last_msg    = ""
            last_role   = ""
            for m in msgs_docs:
                md = m.to_dict()
                if md.get("role") == "user" and not apercu:
                    apercu = md.get("content", "")[:100]
            if msgs_docs:
                lm        = msgs_docs[-1].to_dict()
                last_msg  = lm.get("content", "")[:100]
                last_role = lm.get("role", "")
        except Exception:
            apercu = ""; nb_messages = 0; last_msg = ""; last_role = ""

        result.append({
            "id":           c_id,
            "user_id":      uid,
            "user_name":    user_names.get(uid, uid[:8] if uid else "—"),
            "statut":       conv.get("statut")       or "en_cours",
            "sujet":        conv.get("sujet")        or "—",
            "service_type": conv.get("service_type") or "—",
            "created_at":   _ts(conv.get("created_at")),
            "updated_at":   _ts(conv.get("updated_at")),
            "nb_messages":  nb_messages,
            "apercu":       apercu,
            "last_msg":     last_msg,
            "last_role":    last_role,
        })

    return result
