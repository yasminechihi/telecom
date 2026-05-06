#!/usr/bin/env python3
# ============================================================
#  supabase_config.py — Connexion Supabase (PostgreSQL)
#  Remplace firebase_config.py (Firebase Firestore)
#
#  SETUP REQUIS (une seule fois) :
#    1. Aller sur https://supabase.com → créer un projet
#    2. Settings → API → copier URL + service_role key dans config.py
#    3. Créer les tables SQL ci-dessous dans l'éditeur SQL Supabase :
#
#  -- TABLE users
#  CREATE TABLE users (
#      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#      nom TEXT, prenom TEXT, email TEXT UNIQUE NOT NULL,
#      password_hash TEXT, telephone TEXT DEFAULT '',
#      avatar_color TEXT DEFAULT '#5B1FBE',
#      is_active BOOLEAN DEFAULT TRUE,
#      last_login TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW()
#  );
#
#  -- TABLE conversations
#  CREATE TABLE conversations (
#      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#      user_id TEXT, titre TEXT DEFAULT 'Nouvelle conversation',
#      statut TEXT DEFAULT 'en_cours', sujet TEXT DEFAULT '',
#      service_type TEXT DEFAULT '', canal TEXT DEFAULT 'web',
#      last_msg TEXT DEFAULT '', last_role TEXT DEFAULT '',
#      nb_messages INT DEFAULT 0, apercu TEXT DEFAULT '',
#      satisfaction_rating INT DEFAULT 0,
#      satisfaction_feedback TEXT DEFAULT '',
#      satisfaction_rated_at TIMESTAMPTZ,
#      was_transferred BOOLEAN DEFAULT FALSE,
#      transferred BOOLEAN DEFAULT FALSE,
#      last_problem TEXT DEFAULT '',
#      created_at TIMESTAMPTZ DEFAULT NOW(),
#      updated_at TIMESTAMPTZ DEFAULT NOW()
#  );
#
#  -- TABLE messages
#  CREATE TABLE messages (
#      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#      conversation_id TEXT, user_id TEXT,
#      role TEXT, content TEXT,
#      nlu_intent TEXT DEFAULT '', nlu_confidence FLOAT DEFAULT 0,
#      nlu_sentiment TEXT DEFAULT '', nlu_service TEXT DEFAULT '',
#      nlu_wilaya TEXT DEFAULT '', nlu_delegation TEXT DEFAULT '',
#      nlu_action TEXT DEFAULT '', nlu_decision TEXT DEFAULT '',
#      nlu_conf_rag FLOAT DEFAULT 0,
#      nlu_ml_used BOOLEAN DEFAULT FALSE,
#      nlu_escalate BOOLEAN DEFAULT FALSE,
#      created_at TIMESTAMPTZ DEFAULT NOW()
#  );
#
#  -- TABLE dataset_nlp
#  CREATE TABLE dataset_nlp (
#      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#      client_name TEXT, location_wilaya TEXT,
#      location_delegation TEXT, issue_type TEXT,
#      service_type TEXT, suggested_action TEXT,
#      sentiment_label TEXT, instruction TEXT, response TEXT,
#      idx INT DEFAULT 0,
#      added_at TIMESTAMPTZ DEFAULT NOW()
#  );
#
#    4. pip install supabase
# ============================================================

import os
import time
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("supabase_config")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ════════════════════════════════════════════════════════════
#  CACHE IN-MEMORY (TTL) — évite les requêtes répétitives
# ════════════════════════════════════════════════════════════

class _TTLCache:
    """Cache dict simple avec expiration + données périmées (stale) en fallback."""
    def __init__(self):
        self._store: dict = {}
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
        self._stale[key] = value

    def invalidate(self, key):
        self._store.pop(key, None)
        self._stale.pop(key, None)

    def clear(self):
        self._store.clear()
        self._stale.clear()


_cache = _TTLCache()


# ════════════════════════════════════════════════════════════
#  CACHE DISQUE — survit aux redémarrages du serveur
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
        os.replace(tmp, path)
    except Exception as _e:
        logger.debug(f"[disk_cache] Écriture échouée ({filename}): {_e}")


def _disk_read(filename: str, default=None):
    """Lit un fichier JSON du cache disque."""
    try:
        path = os.path.join(_CACHE_DIR, filename)
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception as _e:
        logger.debug(f"[disk_cache] Lecture échouée ({filename}): {_e}")
        return default


# ════════════════════════════════════════════════════════════
#  INITIALISATION SUPABASE — client unique (singleton)
# ════════════════════════════════════════════════════════════

_supabase = None


def get_supabase():
    """Retourne le client Supabase (initialise si besoin)."""
    global _supabase
    if _supabase is not None:
        return _supabase
    try:
        from supabase import create_client
        # Lire les credentials depuis config.py
        import sys
        sys.path.insert(0, BASE_DIR)
        import config as _cfg
        url = _cfg.SUPABASE_URL
        key = _cfg.SUPABASE_KEY
        _supabase = create_client(url, key)
        logger.info("Supabase connecté.")
        return _supabase
    except ImportError:
        raise ImportError("supabase non installé. Lancez : pip install supabase")


def init_supabase() -> bool:
    """Vérifie la connexion Supabase. Retourne True si OK."""
    try:
        sb = get_supabase()
        # Test ping : lire 1 ligne de la table users
        sb.table("users").select("id").limit(1).execute()
        logger.info("Supabase : connexion OK")
        return True
    except Exception as e:
        logger.critical(f"Supabase ERREUR : {e}")
        return False


# Alias pour compatibilité avec l'ancien code qui appelle init_firebase()
init_firebase = init_supabase


# ════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════

def _ts(dt) -> str:
    """Convertit un datetime ou string ISO en string lisible."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    if hasattr(dt, "strftime"):
        return dt.strftime("%d/%m/%Y %H:%M")
    return str(dt)


def _now() -> str:
    """Retourne l'heure UTC actuelle en format ISO (pour Supabase)."""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """Génère un UUID unique."""
    return str(uuid.uuid4())


# ════════════════════════════════════════════════════════════
#  USERS
# ════════════════════════════════════════════════════════════

def user_create(nom: str, prenom: str, email: str,
                password_hash: str, telephone: str = "",
                avatar_color: str = "#5B1FBE") -> str:
    """Crée un utilisateur et retourne son ID Supabase."""
    sb = get_supabase()
    data = {
        "id":            _new_id(),
        "nom":           nom,
        "prenom":        prenom,
        "email":         email.lower().strip(),
        "password_hash": password_hash,
        "telephone":     telephone,
        "avatar_color":  avatar_color,
        "is_active":     True,
        "last_login":    None,
        "created_at":    _now(),
    }
    result = sb.table("users").insert(data).execute()
    new_id = result.data[0]["id"] if result.data else data["id"]

    # ── Invalider le cache "__none__" créé lors du check d'unicité email ──
    # Sans ça, user_get_by_email retourne None pendant 5 min → login échoue
    _cache.invalidate(f"user_email_{data['email']}")
    # Pré-remplir le cache avec le nouvel utilisateur (évite un aller-retour Supabase)
    new_user = {**data, "id": str(new_id)}
    _cache.set(f"user_email_{data['email']}", new_user, ttl_seconds=300)
    _cache.set(f"user_id_{new_id}", new_user, ttl_seconds=300)

    return str(new_id)


def user_get_by_email(email: str) -> dict | None:
    """Retourne l'utilisateur avec cet email (ou None).
    Résultat mis en cache 5 min + disque pour résistance aux pannes.
    """
    email = email.lower().strip()
    cache_key = f"user_email_{email}"

    # 1. Cache mémoire TTL
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__none__" else None

    # 2. Supabase
    try:
        sb = get_supabase()
        result = (sb.table("users")
                    .select("*")
                    .eq("email", email)
                    .eq("is_active", True)
                    .limit(1)
                    .execute())
        user = result.data[0] if result.data else None

        _cache.set(cache_key, user if user is not None else "__none__", ttl_seconds=300)
        if user is not None:
            users_disk = _disk_read("users_local.json", default={})
            users_disk[email] = user
            _disk_write("users_local.json", users_disk)
        return user

    except Exception as e:
        logger.warning(f"[user_get_by_email] Supabase KO ({e}) — tentative disque.")
        users_disk = _disk_read("users_local.json", default={})
        user = users_disk.get(email)
        if user:
            logger.info(f"[user_get_by_email] Utilisateur trouvé en cache disque : {email}")
            _cache.set(cache_key, user, ttl_seconds=300)
            return user
        raise


def user_get_by_id(user_id) -> dict | None:
    """Retourne l'utilisateur par son ID Supabase (ou None)."""
    if user_id is None:
        return None
    user_id = str(user_id)
    cache_key = f"user_id_{user_id}"

    cached = _cache.get(cache_key)
    if cached is not None:
        return cached if cached != "__none__" else None

    try:
        sb = get_supabase()
        result = sb.table("users").select("*").eq("id", user_id).limit(1).execute()
        if result.data:
            user = result.data[0]
            _cache.set(cache_key, user, ttl_seconds=300)
            if user.get("email"):
                users_disk = _disk_read("users_local.json", default={})
                users_disk[user["email"]] = user
                _disk_write("users_local.json", users_disk)
            return user
        _cache.set(cache_key, "__none__", ttl_seconds=300)
        return None

    except Exception as e:
        logger.warning(f"[user_get_by_id] Supabase KO ({e}) — tentative disque.")
        users_disk = _disk_read("users_local.json", default={})
        for u in users_disk.values():
            if isinstance(u, dict) and str(u.get("id")) == user_id:
                logger.info(f"[user_get_by_id] Utilisateur trouvé en cache disque : {user_id}")
                _cache.set(cache_key, u, ttl_seconds=300)
                return u
        return None


def user_update_last_login(user_id: str):
    sb = get_supabase()
    sb.table("users").update({"last_login": _now()}).eq("id", str(user_id)).execute()


def user_update_profile(user_id: str, **kwargs):
    sb = get_supabase()
    sb.table("users").update(kwargs).eq("id", str(user_id)).execute()


# ════════════════════════════════════════════════════════════
#  CONVERSATIONS
# ════════════════════════════════════════════════════════════

def conversation_create(user_id: str,
                        titre: str = "Nouvelle conversation",
                        statut: str = "en_cours",
                        sujet: str = "",
                        service_type: str = "",
                        canal: str = "web") -> str:
    """Crée une conversation et retourne son ID Supabase."""
    sb = get_supabase()
    now = _now()
    data = {
        "id":           _new_id(),
        "user_id":      str(user_id),
        "titre":        titre,
        "statut":       statut,
        "sujet":        sujet,
        "service_type": service_type,
        "canal":        canal,
        "nb_messages":  0,
        "created_at":   now,
        "updated_at":   now,
    }
    result = sb.table("conversations").insert(data).execute()
    new_id = result.data[0]["id"] if result.data else _new_id()
    return str(new_id)


def conversation_get(conv_id: str) -> dict | None:
    sb = get_supabase()
    result = sb.table("conversations").select("*").eq("id", conv_id).limit(1).execute()
    return result.data[0] if result.data else None


def conversation_update(conv_id: str, **kwargs):
    sb = get_supabase()
    kwargs["updated_at"] = _now()
    sb.table("conversations").update(kwargs).eq("id", conv_id).execute()
    # Invalider les caches liés
    for limit in [30, 50, 100]:
        _cache.invalidate(f"conv_all_recent_{limit}")


def conversation_rate(conv_id: str, rating: int, feedback: str = "") -> bool:
    """Enregistre la note de satisfaction (1-5 étoiles)."""
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return False
    if rating < 1 or rating > 5:
        return False

    sb = get_supabase()
    sb.table("conversations").update({
        "satisfaction_rating":   rating,
        "satisfaction_feedback": (feedback or "")[:500],
        "satisfaction_rated_at": _now(),
        "updated_at":            _now(),
    }).eq("id", conv_id).execute()
    return True


def conversations_get_by_user(user_id: str, limit: int = 50) -> list:
    """Retourne les conversations d'un user, triées par date décroissante."""
    sb = get_supabase()
    result = (sb.table("conversations")
                .select("*")
                .eq("user_id", str(user_id))
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
    return result.data or []


# ════════════════════════════════════════════════════════════
#  MESSAGES
# ════════════════════════════════════════════════════════════

def message_add(conv_id: str, user_id: str,
                role: str, content: str,
                nlu_data: dict = None) -> str:
    """Ajoute un message dans une conversation."""
    sb  = get_supabase()
    now = _now()
    doc = {
        "id":              _new_id(),
        "conversation_id": conv_id,
        "user_id":         str(user_id),
        "role":            role,
        "content":         content,
        "created_at":      now,
    }
    if nlu_data and role == "user":
        doc["nlu_intent"]     = nlu_data.get("intent", "")
        doc["nlu_confidence"] = nlu_data.get("confidence", 0)
        doc["nlu_sentiment"]  = nlu_data.get("sentiment", "")
        doc["nlu_service"]    = nlu_data.get("service_type", "")
        doc["nlu_wilaya"]     = nlu_data.get("wilaya", "")
        doc["nlu_delegation"] = nlu_data.get("delegation", "")
        doc["nlu_action"]     = nlu_data.get("action", "")
        doc["nlu_decision"]   = nlu_data.get("decision", "")
        doc["nlu_conf_rag"]   = nlu_data.get("confidence_rag", 0)
        doc["nlu_ml_used"]    = nlu_data.get("ml_used", False)
        doc["nlu_escalate"]   = nlu_data.get("escalate", False)

    result = sb.table("messages").insert(doc).execute()
    new_id = result.data[0]["id"] if result.data else _new_id()

    # ── Dénormalisation : mettre à jour la conversation parente ──
    try:
        conv_result = sb.table("conversations").select("nb_messages").eq("id", conv_id).limit(1).execute()
        current_nb  = conv_result.data[0]["nb_messages"] if conv_result.data else 0
        conv_update = {
            "last_msg":    content[:100],
            "last_role":   role,
            "updated_at":  now,
            "nb_messages": (current_nb or 0) + 1,
        }
        if role == "user":
            apercu_cache_key = f"apercu_set_{conv_id}"
            if not _cache.get(apercu_cache_key):
                conv_update["apercu"] = content[:100]
                _cache.set(apercu_cache_key, True, ttl_seconds=86400)
        sb.table("conversations").update(conv_update).eq("id", conv_id).execute()
        for limit in [30, 50, 100]:
            _cache.invalidate(f"conv_all_recent_{limit}")
    except Exception as _e:
        logger.debug(f"[message_add] Dénormalisation conv échouée : {_e}")

    return str(new_id)


def messages_get_by_conversation(conv_id: str) -> list:
    """Retourne tous les messages d'une conversation, triés par date."""
    sb = get_supabase()
    result = (sb.table("messages")
                .select("*")
                .eq("conversation_id", conv_id)
                .order("created_at", desc=False)
                .execute())
    return result.data or []


# ════════════════════════════════════════════════════════════
#  STATISTIQUES
# ════════════════════════════════════════════════════════════

def user_stats(user_id: str) -> dict:
    """Retourne les stats réclamations de l'utilisateur. Cache 2 min."""
    cache_key = f"user_stats_{user_id}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        sb   = get_supabase()
        docs = (sb.table("conversations")
                  .select("statut")
                  .eq("user_id", str(user_id))
                  .execute())

        total = resolues = transferees = en_cours = 0
        for row in (docs.data or []):
            statut = row.get("statut", "")
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
        logger.warning(f"[user_stats] Supabase KO ({e})")
        stale = _cache.get_stale(cache_key)
        if stale is not None:
            return stale
        return {"total": 0, "resolues": 0, "transferees": 0, "en_cours": 0}


# ════════════════════════════════════════════════════════════
#  HISTORIQUE RÉCLAMATIONS
# ════════════════════════════════════════════════════════════

def reclamations_get_by_user(user_id: str, limit: int = 50) -> list:
    """Retourne les réclamations enrichies pour l'historique utilisateur."""
    cache_key = f"reclamations_{user_id}_{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        sb = get_supabase()
        convs = (sb.table("conversations")
                   .select("*")
                   .eq("user_id", str(user_id))
                   .order("created_at", desc=True)
                   .limit(limit)
                   .execute())

        result = []
        for conv in (convs.data or []):
            apercu      = conv.get("apercu") or conv.get("last_msg") or ""
            nb_messages = conv.get("nb_messages") or 0
            result.append({
                "reclamation_id":        conv.get("id"),
                "sujet":                 conv.get("sujet")        or "—",
                "service_type":          conv.get("service_type") or "—",
                "statut":                conv.get("statut")       or "en_cours",
                "created_at":            _ts(conv.get("created_at")),
                "updated_at":            _ts(conv.get("updated_at")),
                "nb_messages":           nb_messages,
                "apercu":                apercu[:120] if apercu else "",
                "satisfaction_rating":   conv.get("satisfaction_rating") or 0,
                "satisfaction_feedback": conv.get("satisfaction_feedback") or "",
                "was_transferred":       bool(conv.get("was_transferred")) or
                                         (conv.get("statut") in ("transferee", "resolue")
                                          and bool(conv.get("transferred"))),
            })

        _cache.set(cache_key, result, ttl_seconds=120)
        return result

    except Exception as e:
        logger.warning(f"[reclamations_get_by_user] Supabase KO ({e})")
        stale = _cache.get_stale(cache_key)
        return stale if stale is not None else []


# ════════════════════════════════════════════════════════════
#  BACK-OFFICE — Dashboard Admin (KPIs agrégés)
# ════════════════════════════════════════════════════════════

def admin_stats() -> dict:
    """Statistiques globales pour le dashboard admin. Cache 10 min + disque."""
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
            "satisfaction_rate": 0.0,
            "avg_rating":        0.0,
            "rated_count":       0,
        }

    def _fmt(sec: float) -> str:
        sec = int(sec)
        if sec < 60:   return f"{sec} s"
        if sec < 3600: m, s = divmod(sec, 60); return f"{m} min {s:02d}s"
        h, r = divmod(sec, 3600); return f"{h} h {r // 60:02d} min"

    try:
        sb   = get_supabase()
        docs = sb.table("conversations").select("*").execute()

        total = 0
        counts = {"en_cours": 0, "resolue": 0, "transferee": 0, "fermee": 0}
        durations: list = []
        rated_count     = 0
        rating_sum      = 0.0
        satisfied_count = 0

        for row in (docs.data or []):
            statut = row.get("statut", "en_cours")
            total += 1
            if statut in counts:
                counts[statut] += 1
            else:
                counts["en_cours"] += 1

            if statut == "resolue":
                cr = row.get("created_at")
                up = row.get("updated_at")
                if cr and up:
                    try:
                        cr_dt = datetime.fromisoformat(str(cr).replace("Z", "+00:00"))
                        up_dt = datetime.fromisoformat(str(up).replace("Z", "+00:00"))
                        delta = (up_dt - cr_dt).total_seconds()
                        if delta >= 0:
                            durations.append(delta)
                    except Exception:
                        pass

            rating = row.get("satisfaction_rating") or 0
            if isinstance(rating, (int, float)) and rating > 0:
                rated_count     += 1
                rating_sum      += rating
                if rating >= 4:
                    satisfied_count += 1

        def _pct(n): return round((n / total) * 100, 1) if total > 0 else 0.0

        avg_sec           = sum(durations) / len(durations) if durations else 0
        min_sec           = min(durations) if durations else 0
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
            "satisfaction_rate":  satisfaction_rate,
            "avg_rating":         avg_rating,
            "rated_count":        rated_count,
        }
        _cache.set("admin_stats", result, ttl_seconds=600)
        _disk_write("admin_stats_stale.json", result)
        return result

    except Exception as e:
        logger.warning(f"[admin_stats] Supabase KO ({e})")
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
    """Retourne les conversations les plus récentes de tous les utilisateurs."""
    cache_key = f"conv_all_recent_{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        sb = get_supabase()
        docs = (sb.table("conversations")
                  .select("*")
                  .order("updated_at", desc=True)
                  .limit(limit)
                  .execute())

        # Récupérer les noms des utilisateurs (groupés pour éviter les requêtes multiples)
        user_ids   = list({row.get("user_id", "") for row in (docs.data or []) if row.get("user_id")})
        user_names: dict = {}
        for uid in user_ids:
            cached_uname = _cache.get(f"uname_{uid}")
            if cached_uname:
                user_names[uid] = cached_uname
                continue
            try:
                u = sb.table("users").select("nom,prenom").eq("id", uid).limit(1).execute()
                if u.data:
                    ud   = u.data[0]
                    name = f"{ud.get('prenom', '')} {ud.get('nom', '')}".strip() or uid[:8]
                    user_names[uid] = name
                    _cache.set(f"uname_{uid}", name, ttl_seconds=600)
            except Exception:
                user_names[uid] = uid[:8]

        result = []
        for conv in (docs.data or []):
            uid    = conv.get("user_id", "")
            apercu = (conv.get("apercu") or conv.get("sujet") or "")[:100]
            result.append({
                "id":           conv.get("id"),
                "user_id":      uid,
                "user_name":    user_names.get(uid, uid[:8] if uid else "—"),
                "statut":       conv.get("statut")       or "en_cours",
                "sujet":        conv.get("sujet")        or "—",
                "service_type": conv.get("service_type") or "—",
                "created_at":   _ts(conv.get("created_at")),
                "updated_at":   _ts(conv.get("updated_at")),
                "nb_messages":  conv.get("nb_messages") or 0,
                "apercu":       apercu,
                "last_msg":     conv.get("last_msg") or "",
                "last_role":    conv.get("last_role") or "",
            })

        _cache.set(cache_key, result, ttl_seconds=30)
        _disk_write("conversations_stale.json", result)
        return result

    except Exception as e:
        stale = _cache.get_stale(cache_key)
        if stale is not None:
            logger.warning(f"[conversations_get_all_recent] Supabase KO ({e}) — stale mémoire.")
            return stale
        disk = _disk_read("conversations_stale.json")
        if disk:
            logger.warning(f"[conversations_get_all_recent] Supabase KO ({e}) — stale disque.")
            _cache.set(cache_key, disk, ttl_seconds=30)
            return disk
        logger.error(f"[conversations_get_all_recent] Supabase KO, aucun cache : {e}")
        return []


# ════════════════════════════════════════════════════════════
#  DATASET NLP — table "dataset_nlp"
# ════════════════════════════════════════════════════════════

_DATASET_TABLE = "dataset_nlp"
_LOCAL_JSONL   = os.path.join(BASE_DIR, "dataset_final_nlp_v2_corrected.jsonl")

_dataset_local_cache: list = []
_dataset_local_loaded: bool = False


def _load_local_dataset() -> list:
    """Charge le dataset depuis le fichier JSONL local (zéro requête Supabase)."""
    global _dataset_local_cache, _dataset_local_loaded
    if _dataset_local_loaded:
        return _dataset_local_cache
    records = []
    path = _LOCAL_JSONL
    if not os.path.exists(path):
        alt = os.path.join(BASE_DIR, "..", "bigdata", "dataset_final_nlp_v2.jsonl")
        if os.path.exists(alt):
            path = alt
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = _json.loads(line)
                        d["_supabase_id"] = f"local_{i}"
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
    """Charge tous les enregistrements du dataset.
    Priorité : JSONL local (zéro quota) → Supabase en fallback.
    """
    local = _load_local_dataset()
    if local:
        return local

    logger.warning("[dataset] JSONL local absent — chargement depuis Supabase.")
    cached = _cache.get("dataset_all")
    if cached is not None:
        return cached

    sb = get_supabase()
    result = sb.table(_DATASET_TABLE).select("*").order("idx", desc=False).execute()
    records = []
    for row in (result.data or []):
        row["_supabase_id"] = row.get("id", "")
        row["_idx"]         = row.get("idx", 0)
        records.append(row)

    _cache.set("dataset_all", records, ttl_seconds=3600)
    return records


def dataset_count() -> int:
    """Retourne le nombre d'enregistrements dans le dataset."""
    local = _load_local_dataset()
    if local:
        return len(local)
    sb     = get_supabase()
    result = sb.table(_DATASET_TABLE).select("id", count="exact").execute()
    return result.count or 0


def dataset_add(record: dict) -> str:
    """Ajoute un enregistrement au dataset Supabase."""
    sb = get_supabase()
    n  = dataset_count()
    data = {k: v for k, v in record.items() if not k.startswith("_")}
    data["idx"]      = n
    data["added_at"] = _now()
    result = sb.table(_DATASET_TABLE).insert(data).execute()
    new_id = result.data[0]["id"] if result.data else _new_id()
    logger.info(f"[dataset] Enregistrement ajouté : {new_id}")
    return str(new_id)


def dataset_delete(supabase_id: str) -> bool:
    """Supprime un enregistrement du dataset par son ID Supabase."""
    sb = get_supabase()
    try:
        sb.table(_DATASET_TABLE).delete().eq("id", supabase_id).execute()
        logger.info(f"[dataset] Enregistrement supprimé : {supabase_id}")
        return True
    except Exception as e:
        logger.warning(f"[dataset] Erreur suppression {supabase_id} : {e}")
        return False


def dataset_get_page(page: int = 0, page_size: int = 50) -> list:
    """Retourne une page de `page_size` enregistrements."""
    all_records = dataset_load_all()
    start = page * page_size
    return all_records[start:start + page_size]
