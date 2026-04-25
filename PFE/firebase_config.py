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
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger("firebase_config")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(BASE_DIR, "serviceAccountKey.json")

# ════════════════════════════════════════════════════════════
#  CACHE IN-MEMORY (TTL) — évite de dépasser le quota gratuit
#  Firestore Spark plan : 50 000 lectures/jour.
#  Les endpoints admin lisent parfois TOUTES les conversations
#  + tous leurs messages → très coûteux en quota.
#  Solution : on met en cache les réponses les plus lourdes.
# ════════════════════════════════════════════════════════════

class _TTLCache:
    """Cache dict simple avec expiration + données périmées (stale) en fallback."""
    def __init__(self):
        self._store: dict = {}
        # Copie persistante sans expiration — sert de fallback quand Firebase est KO
        self._stale: dict = {}

    def get(self, key, default=None):
        entry = self._store.get(key)
        if entry is None:
            return default
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return default
        return value

    def get_stale(self, key, default=None):
        """Retourne la dernière valeur mise en cache, même si expirée."""
        return self._stale.get(key, default)

    def set(self, key, value, ttl_seconds: int = 300):
        self._store[key] = (value, time.time() + ttl_seconds)
        # Mettre également à jour le stale store (données fraîches)
        self._stale[key] = value

    def invalidate(self, key):
        self._store.pop(key, None)
        self._stale.pop(key, None)

    def clear(self):
        self._store.clear()
        self._stale.clear()


_cache = _TTLCache()

# ════════════════════════════════════════════════════════════
#  BUDGET DE LECTURES QUOTIDIEN — garde-fou anti-quota
#  Firestore Spark : 50 000 lectures/jour.
#  On coupe les lectures Firebase à 40 000 (marge 10K pour les écrits).
#  Le compteur se remet à zéro automatiquement chaque jour (minuit UTC).
# ════════════════════════════════════════════════════════════

_DAILY_READ_LIMIT = 40_000   # seuil de sécurité (< 50K Firestore Spark)
_read_budget = {"count": 0, "day": None}

def _budget_ok(estimated_reads: int = 1) -> bool:
    """Retourne True si on peut effectuer les lectures Firestore prévues."""
    today = datetime.now(timezone.utc).date()
    if _read_budget["day"] != today:
        _read_budget["count"] = 0
        _read_budget["day"]   = today
    if _read_budget["count"] + estimated_reads > _DAILY_READ_LIMIT:
        logger.warning(
            f"[budget] Budget lectures épuisé ({_read_budget['count']}/{_DAILY_READ_LIMIT}). "
            "Firebase désactivé jusqu'à minuit UTC — cache utilisé."
        )
        return False
    return True

def _budget_consume(n: int):
    """Ajoute n lectures au compteur quotidien."""
    _read_budget["count"] += n

def get_read_budget() -> dict:
    """Expose le budget courant (pour un éventuel endpoint /api/admin/budget)."""
    today = datetime.now(timezone.utc).date()
    if _read_budget["day"] != today:
        return {"count": 0, "limit": _DAILY_READ_LIMIT, "pct": 0}
    return {
        "count": _read_budget["count"],
        "limit": _DAILY_READ_LIMIT,
        "pct":   round(_read_budget["count"] / _DAILY_READ_LIMIT * 100, 1),
    }


# ════════════════════════════════════════════════════════════
#  CACHE DISQUE — survit aux redémarrages du serveur
#  Stocke les dernières données valides dans des fichiers JSON
#  pour que l'interface ne soit jamais vide même si Firebase est KO.
# ════════════════════════════════════════════════════════════

import json as _json

_CACHE_DIR = os.path.join(BASE_DIR, ".cache_local")

def _disk_write(filename: str, data) -> None:
    """Écrit des données JSON sur disque (silencieusement)."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        path = os.path.join(_CACHE_DIR, filename)
        tmp  = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, default=str)
        os.replace(tmp, path)   # remplacement atomique
    except Exception as _e:
        logger.debug(f"[disk_cache] Écriture échouée ({filename}): {_e}")

def _disk_read(filename: str, default=None):
    """Lit un fichier JSON du cache disque (retourne default si absent/corrompu)."""
    try:
        path = os.path.join(_CACHE_DIR, filename)
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as _e:
        logger.debug(f"[disk_cache] Lecture échouée ({filename}): {_e}")
        return default


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
    """Retourne l'utilisateur avec cet email (ou None).
    Résultat mis en cache 5 min + disque pour résister aux pannes Firebase.
    """
    email = email.lower().strip()
    cache_key = f"user_email_{email}"

    # 1. Cache mémoire TTL
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__none__" else None

    # 2. Firestore
    try:
        db = get_db()
        docs = (db.collection("users")
                  .where("email", "==", email)
                  .where("is_active", "==", True)
                  .limit(1)
                  .stream())
        user = None
        for doc in docs:
            d = doc.to_dict()
            d["id"] = doc.id
            user = d
            break

        # Mettre en cache (valeur ou sentinelle None)
        _cache.set(cache_key, user if user is not None else "__none__", ttl_seconds=300)
        if user is not None:
            # Persister sur disque pour fallback si Firebase KO plus tard
            users_disk = _disk_read("users_local.json", default={})
            users_disk[email] = user
            _disk_write("users_local.json", users_disk)
        return user

    except Exception as e:
        # Firebase KO → chercher dans le cache disque local
        logger.warning(f"[user_get_by_email] Firebase KO ({e}) — tentative disque.")
        users_disk = _disk_read("users_local.json", default={})
        user = users_disk.get(email)
        if user:
            logger.info(f"[user_get_by_email] Utilisateur trouvé en cache disque : {email}")
            _cache.set(cache_key, user, ttl_seconds=300)
            return user
        raise  # On ne peut pas authentifier sans données — propager l'erreur


def user_get_by_id(user_id) -> dict | None:
    """Retourne l'utilisateur par son ID Firebase (ou None).
    Résultat mis en cache 5 min + disque pour résister aux pannes Firebase.
    """
    if user_id is None:
        return None
    # Sécurité : Firebase exige une string (l'ancienne session MySQL stockait un int)
    user_id = str(user_id)
    # Un ID Firebase valide ne contient pas que des chiffres
    if user_id.isdigit():
        return None

    cache_key = f"user_id_{user_id}"

    # 1. Cache mémoire TTL
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__none__" else None

    # 2. Firestore
    try:
        db = get_db()
        doc = db.collection("users").document(user_id).get()
        if doc.exists:
            d = doc.to_dict()
            d["id"] = doc.id
            _cache.set(cache_key, d, ttl_seconds=300)
            # Aussi sauvegarder par email sur disque si email présent
            if d.get("email"):
                users_disk = _disk_read("users_local.json", default={})
                users_disk[d["email"]] = d
                _disk_write("users_local.json", users_disk)
            return d
        _cache.set(cache_key, "__none__", ttl_seconds=300)
        return None

    except Exception as e:
        # Firebase KO → chercher dans le cache disque par ID
        logger.warning(f"[user_get_by_id] Firebase KO ({e}) — tentative disque.")
        users_disk = _disk_read("users_local.json", default={})
        for u in users_disk.values():
            if isinstance(u, dict) and u.get("id") == user_id:
                logger.info(f"[user_get_by_id] Utilisateur trouvé en cache disque : {user_id}")
                _cache.set(cache_key, u, ttl_seconds=300)
                return u
        return None   # Non trouvé → retourner None sans crash


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
                        service_type: str = "",
                        canal: str = "web") -> str:
    """Crée une conversation et retourne son document ID Firebase.
    canal : 'web' (interface Flask) ou 'mobile' (app Flutter)."""
    db = get_db()
    now = _now()
    doc_ref = db.collection("conversations").document()
    doc_ref.set({
        "user_id":      user_id,
        "titre":        titre,
        "statut":       statut,
        "sujet":        sujet,
        "service_type": service_type,
        "canal":        canal,
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


def conversation_rate(conv_id: str, rating: int, feedback: str = "") -> bool:
    """
    Enregistre la note de satisfaction (1-5 étoiles) et un commentaire
    optionnel sur une conversation. Retourne True si succès.
    """
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return False
    if rating < 1 or rating > 5:
        return False

    db = get_db()
    db.collection("conversations").document(conv_id).update({
        "satisfaction_rating":   rating,
        "satisfaction_feedback": (feedback or "")[:500],
        "satisfaction_rated_at": _now(),
        "updated_at":            _now(),
    })
    return True


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

    Dénormalisation : met à jour la conversation parente avec last_msg / last_role /
    nb_messages / apercu pour que conversations_get_all_recent() n'ait PAS besoin
    de lire la collection messages (économie de quota Firestore).
    """
    db = get_db()
    now = _now()
    doc_ref = db.collection("messages").document()
    doc = {
        "conversation_id": conv_id,
        "user_id":         user_id,
        "role":            role,       # "user" | "bot"
        "content":         content,
        "created_at":      now,
    }
    if nlu_data and role == "user":
        doc["nlu_intent"]     = nlu_data.get("intent", "")
        doc["nlu_confidence"] = nlu_data.get("confidence", 0)
        doc["nlu_sentiment"]  = nlu_data.get("sentiment", "")
        doc["nlu_service"]    = nlu_data.get("service_type", "")
        # Champs étendus (pour reproduire l'analyse du Test Bot dans la Live Conv.)
        doc["nlu_wilaya"]     = nlu_data.get("wilaya", "")
        doc["nlu_delegation"] = nlu_data.get("delegation", "")
        doc["nlu_action"]     = nlu_data.get("action", "")
        doc["nlu_decision"]   = nlu_data.get("decision", "")
        doc["nlu_conf_rag"]   = nlu_data.get("confidence_rag", 0)
        doc["nlu_ml_used"]    = nlu_data.get("ml_used", False)
        doc["nlu_escalate"]   = nlu_data.get("escalate", False)
    doc_ref.set(doc)

    # ── Dénormalisation : mettre à jour la conversation parente ──
    # Cela évite de lire les messages lors du listing admin (économie de quota).
    try:
        from firebase_admin import firestore as _fs
        conv_ref = db.collection("conversations").document(conv_id)
        conv_update = {
            "last_msg":    content[:100],
            "last_role":   role,
            "updated_at":  now,
            "nb_messages": _fs.SERVER_TIMESTAMP,   # ← remplacé ci-dessous
        }
        # Incrément atomique du compteur nb_messages (écriture, pas de lecture)
        conv_update["nb_messages"] = _fs.Increment(1)
        # Aperçu : on stocke le contenu du premier message user via un champ
        # "apercu_set" dans le cache local (évite une lecture Firestore par message)
        if role == "user":
            apercu_cache_key = f"apercu_set_{conv_id}"
            if not _cache.get(apercu_cache_key):
                conv_update["apercu"] = content[:100]
                _cache.set(apercu_cache_key, True, ttl_seconds=86400)  # 24h
        conv_ref.update(conv_update)
        # Invalider le cache mémoire des conversations (données modifiées)
        _cache.invalidate(f"conv_all_recent_30")
        _cache.invalidate(f"conv_all_recent_50")
        _cache.invalidate(f"conv_all_recent_100")
    except Exception as _e:
        # Non bloquant — le message est déjà sauvegardé
        logger.debug(f"[message_add] Dénormalisation conv échouée : {_e}")

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
    """Retourne les stats réclamations de l'utilisateur.
    Cache mémoire 2 minutes pour éviter les lectures répétitives depuis le dashboard."""
    cache_key = f"user_stats_{user_id}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        db   = get_db()
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

        result = {
            "total":       total,
            "resolues":    resolues,
            "transferees": transferees,
            "en_cours":    en_cours,
        }
        _cache.set(cache_key, result, ttl_seconds=120)
        return result

    except Exception as e:
        logger.warning(f"[user_stats] Firebase KO ({e})")
        stale = _cache.get_stale(cache_key)
        if stale is not None:
            return stale
        return {"total": 0, "resolues": 0, "transferees": 0, "en_cours": 0}


# ════════════════════════════════════════════════════════════
#  HISTORIQUE RÉCLAMATIONS (vue équivalente à v_user_reclamations)
# ════════════════════════════════════════════════════════════

def reclamations_get_by_user(user_id: str, limit: int = 50) -> list:
    """
    Retourne les réclamations enrichies (avec aperçu) pour l'historique.
    OPTIMISATION QUOTA : lit uniquement les docs conversation (zéro lecture messages).
    Cache mémoire 2 minutes par utilisateur.
    """
    cache_key = f"reclamations_{user_id}_{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        if not _budget_ok(estimated_reads=limit):
            stale = _cache.get_stale(cache_key)
            return stale if stale is not None else []

        db = get_db()
        # Lire uniquement les conversations (pas les messages) — N lectures seulement
        convs_docs = list(db.collection("conversations")
                            .where("user_id", "==", user_id)
                            .stream())
        _budget_consume(len(convs_docs))

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

            # Utiliser les champs dénormalisés (écrits par message_add) — 0 lecture messages
            apercu      = conv.get("apercu") or conv.get("last_msg") or ""
            nb_messages = conv.get("nb_messages") or 0

            result.append({
                "reclamation_id":        c_id,
                "sujet":                 conv.get("sujet")        or "—",
                "service_type":          conv.get("service_type") or "—",
                "statut":                conv.get("statut")       or "en_cours",
                "created_at":            _ts(conv.get("created_at")),
                "updated_at":            _ts(conv.get("updated_at")),
                "nb_messages":           nb_messages,
                "apercu":                apercu[:120] if apercu else "",
                "satisfaction_rating":   conv.get("satisfaction_rating") or 0,
                "satisfaction_feedback": conv.get("satisfaction_feedback") or "",
                "was_transferred":       bool(conv.get("was_transferred")) or (conv.get("statut") in ("transferee", "resolue") and bool(conv.get("transferred"))),
            })

        _cache.set(cache_key, result, ttl_seconds=120)
        return result

    except Exception as e:
        logger.warning(f"[reclamations_get_by_user] Firebase KO ({e})")
        stale = _cache.get_stale(cache_key)
        if stale is not None:
            return stale
        return []


# ════════════════════════════════════════════════════════════
#  BACK-OFFICE — Dashboard Admin (KPIs agrégés)
# ════════════════════════════════════════════════════════════

def admin_stats() -> dict:
    """
    Statistiques globales pour le dashboard admin.
    Cache mémoire 10 min + cache disque persistant.
    Si Firebase KO → retourne les dernières stats connues (jamais de crash).
    """
    cached = _cache.get("admin_stats")
    if cached is not None:
        return cached

    def _empty():
        return {
            "total": 0,
            "counts": {"en_cours": 0, "resolue": 0, "transferee": 0, "fermee": 0},
            "percentages": {"en_cours": 0.0, "resolue": 0.0, "transferee": 0.0, "fermee": 0.0},
            "avg_response_sec": 0, "avg_response_str": "—",
            "min_response_sec": 0, "min_response_str": "—",
            "resolues_count": 0,
            "satisfaction_rate": 0.0,   # % conversations notées ≥ 4 étoiles
            "avg_rating":        0.0,   # note moyenne (1-5)
            "rated_count":       0,     # nb conversations ayant reçu une note
        }

    def _fmt(sec: float) -> str:
        sec = int(sec)
        if sec < 60:   return f"{sec} s"
        if sec < 3600: m, s = divmod(sec, 60); return f"{m} min {s:02d}s"
        h, r = divmod(sec, 3600); return f"{h} h {r//60:02d} min"

    try:
        if not _budget_ok(estimated_reads=100):
            stale = _cache.get_stale("admin_stats") or _disk_read("admin_stats_stale.json")
            if stale:
                logger.info("[admin_stats] Budget épuisé → cache stale.")
                return stale
            return _empty()

        db   = get_db()
        docs = list(db.collection("conversations").stream())
        _budget_consume(len(docs))

        total = 0
        counts = {"en_cours": 0, "resolue": 0, "transferee": 0, "fermee": 0}
        durations: list = []
        rated_count     = 0
        rating_sum      = 0.0
        satisfied_count = 0   # note ≥ 4 étoiles

        for doc in docs:
            d      = doc.to_dict()
            statut = d.get("statut", "en_cours")
            total += 1
            if statut in counts:
                counts[statut] += 1
            else:
                counts["en_cours"] += 1
            if statut == "resolue":
                cr = d.get("created_at"); up = d.get("updated_at")
                if cr and up:
                    try:
                        delta = (up - cr).total_seconds()
                        if delta >= 0:
                            durations.append(delta)
                    except Exception:
                        pass
            # Satisfaction : satisfaction_rating ∈ [1,5]
            rating = d.get("satisfaction_rating") or 0
            if isinstance(rating, (int, float)) and rating > 0:
                rated_count     += 1
                rating_sum      += rating
                if rating >= 4:
                    satisfied_count += 1

        def _pct(n): return round((n / total) * 100, 1) if total > 0 else 0.0

        avg_sec          = sum(durations) / len(durations) if durations else 0
        min_sec          = min(durations) if durations else 0
        satisfaction_rate = round((satisfied_count / rated_count) * 100, 1) if rated_count > 0 else 0.0
        avg_rating        = round(rating_sum / rated_count, 2)               if rated_count > 0 else 0.0

        result = {
            "total":              total,
            "counts":             counts,
            "percentages":        {k: _pct(v) for k, v in counts.items()},
            "avg_response_sec":   round(avg_sec, 1),
            "avg_response_str":   _fmt(avg_sec),
            "min_response_sec":   round(min_sec, 1),
            "min_response_str":   _fmt(min_sec),
            "resolues_count":     len(durations),
            "satisfaction_rate":  satisfaction_rate,   # % notées ≥ 4 étoiles
            "avg_rating":         avg_rating,           # note moyenne /5
            "rated_count":        rated_count,          # nb conversations notées
        }
        _cache.set("admin_stats", result, ttl_seconds=600)
        _disk_write("admin_stats_stale.json", result)
        return result

    except Exception as e:
        logger.warning(f"[admin_stats] Firebase KO ({e})")
        stale = _cache.get_stale("admin_stats")
        if stale is not None:
            return stale
        disk = _disk_read("admin_stats_stale.json")
        if disk:
            _cache.set("admin_stats", disk, ttl_seconds=600)
            return disk
        return _empty()


# ════════════════════════════════════════════════════════════
#  BACK-OFFICE — Toutes les conversations (admin)
# ════════════════════════════════════════════════════════════

def conversations_get_all_recent(limit: int = 30) -> list:
    """
    Retourne les conversations les plus recentes de TOUS les utilisateurs.
    Utilisee par l'interface back-office de app.py pour le monitoring live.

    Chaque entree contient :
        id, user_id, user_name, statut, sujet, service_type,
        created_at, updated_at, nb_messages (0), apercu (vide), last_msg, last_role

    OPTIMISATION QUOTA :
      - Ne lit QUE les documents conversations (pas les messages) → N lectures seulement
      - TTL cache en mémoire : 10 minutes (vs 12s refresh de l'admin)
      - Stale in-memory + disque : si Firebase KO → données périmées plutôt que liste vide
    """
    cache_key = f"conv_all_recent_{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        # Vérifier le budget avant de toucher Firebase
        if not _budget_ok(estimated_reads=limit + 10):
            stale = _cache.get_stale(cache_key) or _disk_read("conversations_stale.json") or []
            if stale:
                logger.info("[conversations_get_all_recent] Budget épuisé → cache stale.")
                return stale
            return []

        db = get_db()

        # ── Lecture UNIQUEMENT des documents conversations (pas des messages) ──
        # Économie : N lectures au lieu de N + N×M (M = nb messages par conv)
        docs = list(db.collection("conversations").stream())
        _budget_consume(len(docs))

        def _sort_key(doc):
            d = doc.to_dict()
            return d.get("updated_at") or d.get("created_at") or datetime(1970, 1, 1, tzinfo=timezone.utc)

        docs.sort(key=_sort_key, reverse=True)
        docs = docs[:limit]

        # ── Récupérer les noms des utilisateurs ──
        user_ids   = list({d.to_dict().get("user_id", "") for d in docs if d.to_dict().get("user_id")})
        user_names: dict = {}
        for uid in user_ids:
            # Essayer d'abord le cache disque (évite des lectures Firestore)
            cached_uname = _cache.get(f"uname_{uid}")
            if cached_uname:
                user_names[uid] = cached_uname
                continue
            try:
                u = db.collection("users").document(uid).get()
                if u.exists:
                    ud   = u.to_dict()
                    name = f"{ud.get('prenom', '')} {ud.get('nom', '')}".strip() or uid[:8]
                    user_names[uid] = name
                    _cache.set(f"uname_{uid}", name, ttl_seconds=600)
            except Exception:
                user_names[uid] = uid[:8]

        result = []
        for doc in docs:
            conv  = doc.to_dict()
            c_id  = doc.id
            uid   = conv.get("user_id", "")

            # Aperçu stocké directement dans la conversation (champ optionnel)
            # Sinon : vide — les détails sont chargés à la demande (click)
            apercu  = (conv.get("apercu") or conv.get("sujet") or "")[:100]

            result.append({
                "id":           c_id,
                "user_id":      uid,
                "user_name":    user_names.get(uid, uid[:8] if uid else "—"),
                "statut":       conv.get("statut")       or "en_cours",
                "sujet":        conv.get("sujet")        or "—",
                "service_type": conv.get("service_type") or "—",
                "created_at":   _ts(conv.get("created_at")),
                "updated_at":   _ts(conv.get("updated_at")),
                "nb_messages":  conv.get("nb_messages") or 0,   # mis à jour via conversation_update()
                "apercu":       apercu,
                "last_msg":     conv.get("last_msg") or "",
                "last_role":    conv.get("last_role") or "",
            })

        # Cache mémoire 10 minutes + stale store + disque
        _cache.set(cache_key, result, ttl_seconds=600)
        _disk_write("conversations_stale.json", result)
        return result

    except Exception as e:
        # Firebase indisponible (quota dépassé, réseau, etc.)
        # Ordre de préférence : stale mémoire → disque → liste vide
        stale = _cache.get_stale(cache_key)
        if stale is not None:
            logger.warning(
                f"[conversations_get_all_recent] Firebase KO ({e}) — "
                f"stale mémoire ({len(stale)} conversations)."
            )
            return stale
        disk = _disk_read("conversations_stale.json")
        if disk:
            logger.warning(
                f"[conversations_get_all_recent] Firebase KO ({e}) — "
                f"stale disque ({len(disk)} conversations)."
            )
            # Remettre en mémoire pour les prochains appels
            _cache.set(cache_key, disk, ttl_seconds=600)
            return disk
        logger.error(f"[conversations_get_all_recent] Firebase KO, aucun cache : {e}")
        return []


# ════════════════════════════════════════════════════════════
#  DATASET NLP — collection "dataset_nlp"
#
#  Chaque document conserve exactement les mêmes champs que
#  le fichier JSONL original :
#    client_name, location_wilaya, location_delegation,
#    issue_type, service_type, suggested_action,
#    sentiment_label, instruction, response
#  + un champ _idx (int) pour préserver l'ordre d'insertion.
# ════════════════════════════════════════════════════════════

_DATASET_COLLECTION = "dataset_nlp"

# Chemin du fichier JSONL local (source de vérité primaire)
_LOCAL_JSONL = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")
# Cache in-memory du dataset (chargé une seule fois par session serveur)
_dataset_local_cache: list = []
_dataset_local_loaded: bool = False


def _load_local_dataset() -> list:
    """Charge le dataset depuis le fichier JSONL local (ne consomme PAS de quota Firestore)."""
    global _dataset_local_cache, _dataset_local_loaded
    if _dataset_local_loaded:
        return _dataset_local_cache
    records = []
    path = _LOCAL_JSONL
    if not os.path.exists(path):
        # Fallback : chercher dans le répertoire bigdata
        alt = os.path.join(BASE_DIR, "..", "bigdata", "dataset_final_nlp_v2.jsonl")
        if os.path.exists(alt):
            path = alt
    if os.path.exists(path):
        try:
            import json as _json
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = _json.loads(line)
                        d["_firebase_id"] = f"local_{i}"
                        d["_idx"] = i
                        records.append(d)
                    except Exception:
                        continue
            logger.info(f"[dataset] Chargé depuis JSONL local : {len(records)} entrées")
        except Exception as e:
            logger.warning(f"[dataset] Erreur lecture JSONL local : {e}")
    _dataset_local_cache = records
    _dataset_local_loaded = True
    return records


def dataset_load_all() -> list:
    """
    Charge tous les enregistrements du dataset.
    Stratégie : fichier JSONL local en priorité (zéro lecture Firestore).
    Fallback Firestore uniquement si le fichier local est absent.
    Résultat mis en cache en mémoire pour la durée du processus serveur.
    """
    # Priorité : source locale (ne coûte pas de quota Firestore)
    local = _load_local_dataset()
    if local:
        return local

    # Fallback : Firestore (coûteux — utilisé uniquement si le JSONL est absent)
    logger.warning("[dataset] JSONL local absent — chargement depuis Firestore (coûteux !)")
    cached = _cache.get("dataset_all")
    if cached is not None:
        return cached
    db = get_db()
    docs = list(db.collection(_DATASET_COLLECTION).stream())
    # Tri Python (évite l'index composite Firestore requis par order_by("_idx"))
    records = []
    for doc in docs:
        d = doc.to_dict()
        d["_firebase_id"] = doc.id
        records.append(d)
    records.sort(key=lambda x: x.get("_idx", 0))
    _cache.set("dataset_all", records, ttl_seconds=3600)   # cache 1 heure
    return records


def dataset_count() -> int:
    """Retourne le nombre de documents dans la collection dataset_nlp.
    Utilise la source locale si disponible (zéro quota Firestore)."""
    local = _load_local_dataset()
    if local:
        return len(local)
    # Fallback Firestore
    db = get_db()
    try:
        from google.cloud.firestore_v1.base_query import BaseQuery  # noqa
        agg = db.collection(_DATASET_COLLECTION).count()
        result = agg.get()
        return result[0][0].value
    except Exception:
        return sum(1 for _ in db.collection(_DATASET_COLLECTION).stream())


def dataset_add(record: dict) -> str:
    """
    Ajoute un enregistrement au dataset Firebase.
    Retourne l'ID Firestore du document créé.
    """
    db = get_db()
    try:
        n = dataset_count()
    except Exception:
        n = 0
    doc_ref = db.collection(_DATASET_COLLECTION).document()
    data = {k: v for k, v in record.items() if not k.startswith("_")}
    data["_idx"] = n
    data["_added_at"] = _now()
    doc_ref.set(data)
    logger.info(f"[dataset] Enregistrement ajouté : {doc_ref.id}")
    return doc_ref.id


def dataset_delete(firebase_id: str) -> bool:
    """Supprime un enregistrement du dataset par son ID Firestore."""
    db = get_db()
    try:
        db.collection(_DATASET_COLLECTION).document(firebase_id).delete()
        logger.info(f"[dataset] Enregistrement supprimé : {firebase_id}")
        return True
    except Exception as e:
        logger.warning(f"[dataset] Erreur suppression {firebase_id} : {e}")
        return False


def dataset_get_page(page: int = 0, page_size: int = 50) -> list:
    """
    Retourne une page de `page_size` enregistrements (pour l'interface backoffice).
    page=0 → les premiers enregistrements.
    Utilise le JSONL local si disponible (zéro quota Firestore).
    """
    all_records = dataset_load_all()
    start = page * page_size
    return all_records[start:start + page_size]
