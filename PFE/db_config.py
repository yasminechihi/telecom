# ============================================================
#  db_config.py — Connexion MySQL (EasyPHP / XAMPP)
#  + Création automatique de la base et des tables au démarrage
# ============================================================

import mysql.connector
from mysql.connector import Error
import logging

logger = logging.getLogger(__name__)

# ── Paramètres EasyPHP par défaut ─────────────────────────
DB_HOST     = "127.0.0.1"
DB_PORT     = 3306
DB_USER     = "root"
DB_PASSWORD = ""          # EasyPHP : mot de passe vide par défaut
DB_NAME     = "user_app"


def get_db_connection():
    """Retourne une connexion MySQL active (avec la base sélectionnée)."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            use_unicode=True,
            autocommit=False,
        )
        return conn
    except Error as e:
        logger.error(f"[DB] Erreur connexion MySQL : {e}")
        raise


def init_db():
    """
    Crée automatiquement la base de données et les tables
    si elles n'existent pas encore.
    Appelée au démarrage de user_app.py.
    """
    try:
        # Connexion SANS sélectionner de base (pour pouvoir la créer)
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            charset="utf8mb4",
            use_unicode=True,
            autocommit=True,
        )
        cursor = conn.cursor()

        # 1. Créer la base si elle n'existe pas
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(f"USE `{DB_NAME}`")
        logger.info(f"[DB] Base '{DB_NAME}' OK")

        # 2. Table users
        cursor.execute("""
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        logger.info("[DB] Table 'users' OK")

        # 3. Table conversations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
              id           INT AUTO_INCREMENT PRIMARY KEY,
              user_id      INT          NOT NULL,
              session_id   VARCHAR(120) NOT NULL UNIQUE,
              sujet        VARCHAR(250) DEFAULT NULL,
              service_type VARCHAR(100) DEFAULT NULL,
              statut       ENUM('en_cours','resolue','transferee','fermee')
                           DEFAULT 'en_cours',
              created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
              updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
              INDEX idx_user_id   (user_id),
              INDEX idx_session_id (session_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        logger.info("[DB] Table 'conversations' OK")

        # 4. Table messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
              id              INT AUTO_INCREMENT PRIMARY KEY,
              conversation_id INT  NOT NULL,
              role            ENUM('user','bot') NOT NULL,
              content         TEXT NOT NULL,
              timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (conversation_id)
                REFERENCES conversations(id) ON DELETE CASCADE,
              INDEX idx_conv_id (conversation_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        logger.info("[DB] Table 'messages' OK")

        # 5. Vue récapitulative
        cursor.execute("""
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
              (SELECT content FROM messages
               WHERE conversation_id = c.id AND role = 'user'
               ORDER BY timestamp ASC LIMIT 1) AS apercu
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
        """)
        logger.info("[DB] Vue 'v_user_reclamations' OK")

        cursor.close()
        conn.close()
        logger.info("[DB] Initialisation base de données terminée avec succès ✓")
        return True

    except Error as e:
        logger.error(f"[DB] ERREUR initialisation : {e}")
        logger.error("[DB] Vérifiez que EasyPHP / MySQL est bien démarré !")
        return False


def db_execute(query: str, params: tuple = (), fetchone: bool = False,
               fetchall: bool = False, lastrowid: bool = False):
    """
    Helper pour exécuter une requête et gérer proprement la connexion.
    Retourne :
      - fetchone=True  → dict ou None
      - fetchall=True  → liste de dicts
      - lastrowid=True → id inséré
      - sinon          → None (UPDATE/DELETE)
    """
    conn   = None
    cursor = None
    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)

        if fetchone:
            result = cursor.fetchone()
        elif fetchall:
            result = cursor.fetchall()
        elif lastrowid:
            conn.commit()
            result = cursor.lastrowid
        else:
            conn.commit()
            result = None

        return result

    except Error as e:
        if conn:
            conn.rollback()
        logger.error(f"[DB] Erreur requête : {e}\nSQL : {query}\nParams : {params}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
