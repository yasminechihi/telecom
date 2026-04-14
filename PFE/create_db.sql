-- ============================================================
--  create_db.sql — Base de données Espace Utilisateur TT
--  Compatible EasyPHP / XAMPP / MySQL 5.7+
--  Exécuter via phpMyAdmin ou : mysql -u root < create_db.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS user_app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE user_app;

-- ── Table utilisateurs ────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  nom           VARCHAR(60)  NOT NULL,
  prenom        VARCHAR(60)  NOT NULL,
  email         VARCHAR(120) UNIQUE NOT NULL,
  telephone     VARCHAR(25)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  avatar_color  VARCHAR(10)  DEFAULT '#6B2FA0',
  created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  last_login    TIMESTAMP    NULL,
  is_active     TINYINT(1)   DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── Table conversations (= dossiers réclamation) ──────────
CREATE TABLE IF NOT EXISTS conversations (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT          NOT NULL,
  session_id   VARCHAR(120) NOT NULL UNIQUE,
  sujet        VARCHAR(250) DEFAULT NULL,
  service_type VARCHAR(100) DEFAULT NULL,
  statut       ENUM('en_cours','resolue','transferee','fermee')
               DEFAULT 'en_cours',
  created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user_id (user_id),
  INDEX idx_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── Table messages ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  conversation_id INT  NOT NULL,
  role            ENUM('user','bot') NOT NULL,
  content         TEXT NOT NULL,
  timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
  INDEX idx_conv_id (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ── Vue récapitulative pour le dashboard ──────────────────
CREATE OR REPLACE VIEW v_user_reclamations AS
SELECT
  c.id           AS reclamation_id,
  c.user_id,
  c.session_id,
  c.sujet,
  c.service_type,
  c.statut,
  c.created_at,
  c.updated_at,
  COUNT(m.id)    AS nb_messages,
  -- premier message user comme aperçu
  (SELECT content FROM messages
   WHERE conversation_id = c.id AND role = 'user'
   ORDER BY timestamp ASC LIMIT 1) AS apercu
FROM conversations c
LEFT JOIN messages m ON m.conversation_id = c.id
GROUP BY c.id;
