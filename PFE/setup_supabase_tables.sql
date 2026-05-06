-- ============================================================
--  setup_supabase_tables.sql
--  Script de création / mise à jour des tables Supabase
--  pour le VoiceBot PFE Tunisie Telecom
--
--  ➤ Copiez tout ce fichier dans Supabase → SQL Editor → New Query
--  ➤ Cliquez sur "Run" (F5)
--  ➤ Ce script est SAFE : il ne supprime aucune donnée existante.
-- ============================================================


-- ═══════════════════════════════════════════════════════════
--  TABLE  users
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom           TEXT             DEFAULT '',
    prenom        TEXT             DEFAULT '',
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT             DEFAULT '',
    telephone     TEXT             DEFAULT '',
    avatar_color  TEXT             DEFAULT '#5B1FBE',
    is_active     BOOLEAN          DEFAULT TRUE,
    last_login    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ      DEFAULT NOW()
);

-- Colonnes manquantes (safe si elles existent déjà)
ALTER TABLE users ADD COLUMN IF NOT EXISTS nom           TEXT         DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS prenom        TEXT         DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT         DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS telephone     TEXT         DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_color  TEXT         DEFAULT '#5B1FBE';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active     BOOLEAN      DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login    TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ  DEFAULT NOW();


-- ═══════════════════════════════════════════════════════════
--  TABLE  conversations
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS conversations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               TEXT             DEFAULT '',
    titre                 TEXT             DEFAULT 'Nouvelle conversation',
    statut                TEXT             DEFAULT 'en_cours',
    sujet                 TEXT             DEFAULT '',
    service_type          TEXT             DEFAULT '',
    canal                 TEXT             DEFAULT 'web',
    last_msg              TEXT             DEFAULT '',
    last_role             TEXT             DEFAULT '',
    nb_messages           INT              DEFAULT 0,
    apercu                TEXT             DEFAULT '',
    last_problem          TEXT             DEFAULT '',
    satisfaction_rating   INT              DEFAULT 0,
    satisfaction_feedback TEXT             DEFAULT '',
    satisfaction_rated_at TIMESTAMPTZ,
    was_transferred       BOOLEAN          DEFAULT FALSE,
    transferred           BOOLEAN          DEFAULT FALSE,
    created_at            TIMESTAMPTZ      DEFAULT NOW(),
    updated_at            TIMESTAMPTZ      DEFAULT NOW()
);

-- Colonnes manquantes
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id               TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS titre                 TEXT        DEFAULT 'Nouvelle conversation';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS statut                TEXT        DEFAULT 'en_cours';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS sujet                 TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS service_type          TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS canal                 TEXT        DEFAULT 'web';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_msg              TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_role             TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS nb_messages           INT         DEFAULT 0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS apercu                TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_problem          TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS satisfaction_rating   INT         DEFAULT 0;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS satisfaction_feedback TEXT        DEFAULT '';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS satisfaction_rated_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS was_transferred       BOOLEAN     DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS transferred           BOOLEAN     DEFAULT FALSE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS created_at            TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS updated_at            TIMESTAMPTZ DEFAULT NOW();


-- ═══════════════════════════════════════════════════════════
--  TABLE  messages
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT             DEFAULT '',
    user_id         TEXT             DEFAULT '',
    role            TEXT             DEFAULT 'user',
    content         TEXT             DEFAULT '',
    nlu_intent      TEXT             DEFAULT '',
    nlu_confidence  FLOAT            DEFAULT 0,
    nlu_sentiment   TEXT             DEFAULT '',
    nlu_service     TEXT             DEFAULT '',
    nlu_wilaya      TEXT             DEFAULT '',
    nlu_delegation  TEXT             DEFAULT '',
    nlu_action      TEXT             DEFAULT '',
    nlu_decision    TEXT             DEFAULT '',
    nlu_conf_rag    FLOAT            DEFAULT 0,
    nlu_ml_used     BOOLEAN          DEFAULT FALSE,
    nlu_escalate    BOOLEAN          DEFAULT FALSE,
    created_at      TIMESTAMPTZ      DEFAULT NOW()
);

-- Colonnes manquantes
ALTER TABLE messages ADD COLUMN IF NOT EXISTS conversation_id TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_id         TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS role            TEXT        DEFAULT 'user';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS content         TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_intent      TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_confidence  FLOAT       DEFAULT 0;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_sentiment   TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_service     TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_wilaya      TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_delegation  TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_action      TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_decision    TEXT        DEFAULT '';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_conf_rag    FLOAT       DEFAULT 0;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_ml_used     BOOLEAN     DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS nlu_escalate    BOOLEAN     DEFAULT FALSE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ DEFAULT NOW();


-- ═══════════════════════════════════════════════════════════
--  TABLE  dataset_nlp  (vérification colonnes)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dataset_nlp (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_name         TEXT DEFAULT '',
    location_wilaya     TEXT DEFAULT '',
    location_delegation TEXT DEFAULT '',
    issue_type          TEXT DEFAULT '',
    service_type        TEXT DEFAULT '',
    suggested_action    TEXT DEFAULT '',
    sentiment_label     TEXT DEFAULT '',
    instruction         TEXT DEFAULT '',
    response            TEXT DEFAULT '',
    added_at            TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS client_name         TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS location_wilaya     TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS location_delegation TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS issue_type          TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS service_type        TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS suggested_action    TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS sentiment_label     TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS instruction         TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS response            TEXT        DEFAULT '';
ALTER TABLE dataset_nlp ADD COLUMN IF NOT EXISTS added_at            TIMESTAMPTZ DEFAULT NOW();


-- ═══════════════════════════════════════════════════════════
--  Désactiver la sécurité RLS pour toutes les tables
--  (nécessaire pour l'accès via service_role key)
-- ═══════════════════════════════════════════════════════════
ALTER TABLE users         DISABLE ROW LEVEL SECURITY;
ALTER TABLE conversations DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages      DISABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_nlp   DISABLE ROW LEVEL SECURITY;


-- ═══════════════════════════════════════════════════════════
--  Index utiles pour les performances
-- ═══════════════════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_users_email         ON users(email);
CREATE INDEX IF NOT EXISTS idx_conv_user_id        ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_created_at     ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_msg_conv_id         ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_msg_created_at      ON messages(created_at DESC);

-- ============================================================
--  ✅ Script terminé — toutes les tables sont prêtes.
-- ============================================================
