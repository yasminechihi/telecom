# ============================================================
#  modules/learning.py — Apprentissage Continu
#  Le bot apprend des interventions des agents humains
# ============================================================

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class LearningModule:
    """
    Module d'apprentissage continu.

    Principe :
        Quand un agent humain résout un problème que le bot
        ne savait pas gérer → sauvegarder l'échange dans
        learned_interactions.jsonl → déclencher le rechargement
        de l'index RAG si le seuil est atteint.

    Format des données apprises :
        Compatible avec le dataset principal (même schéma JSONL).
    """

    def __init__(self, config):
        self.config      = config
        self._new_count  = self._count_learned()
        os.makedirs(config.DATA_DIR, exist_ok=True)
        logger.info(f"LearningModule initialisé — {self._new_count} interactions apprises.")

    # ─────────────────────────────────────────────────────────
    # Apprentissage depuis un agent humain
    # ─────────────────────────────────────────────────────────
    def learn_from_human(
        self,
        user_text: str,
        human_response: str,
        issue_type: str = "",
        service_type: str = "",
        session_id: str = "",
        history: list = None,
    ) -> bool:
        """
        Enregistre une nouvelle interaction apprise depuis un agent humain.

        Args:
            user_text:      Dernière phrase du client
            human_response: Réponse fournie par l'agent humain
            issue_type:     Type de problème (ex: عطل في الشبكة)
            service_type:   Type de service (ex: Mobile)
            session_id:     ID de la session
            history:        Historique complet de la conversation

        Returns:
            True si sauvegardé avec succès.
        """
        if not user_text or not human_response:
            logger.warning("Données insuffisantes pour l'apprentissage.")
            return False

        # Construire l'instruction au format du dataset principal
        instruction = self._build_instruction(user_text, human_response, history)

        # Enregistrement au même format que le dataset d'origine
        record = {
            "client_name":          f"عميل_{session_id or datetime.now().strftime('%H%M%S')}",
            "location_wilaya":      "",
            "location_delegation":  "",
            "issue_type":           issue_type or "غير محدد",
            "service_type":         service_type or "Mobile",
            "suggested_action":     "تعلم من وكيل بشري",
            "sentiment_label":      "سلبي",
            "instruction":          instruction,
            "response":             human_response.strip(),
            "source":               "human_agent",
            "learned_at":           datetime.now().isoformat(),
            "session_id":           session_id,
        }

        try:
            with open(self.config.LEARNED_DATA_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._new_count += 1
            logger.info(
                f"Nouvelle interaction apprise #{self._new_count}: "
                f"'{user_text[:40]}...' → '{human_response[:40]}...'"
            )
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde apprentissage: {e}")
            return False

    # ─────────────────────────────────────────────────────────
    # Apprentissage depuis un fichier batch
    # ─────────────────────────────────────────────────────────
    def learn_from_batch(self, batch_file: str) -> int:
        """
        Importe un fichier JSONL de nouvelles interactions.
        Utile pour importer les données de l'ancien système CRM.

        Returns:
            Nombre d'interactions importées.
        """
        if not os.path.exists(batch_file):
            logger.error(f"Fichier batch introuvable: {batch_file}")
            return 0

        count = 0
        with open(batch_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("instruction") and rec.get("response"):
                        rec["source"]     = "batch_import"
                        rec["learned_at"] = datetime.now().isoformat()
                        with open(self.config.LEARNED_DATA_PATH, "a", encoding="utf-8") as out:
                            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        count += 1
                except json.JSONDecodeError:
                    continue

        self._new_count += count
        logger.info(f"Batch importé: {count} nouvelles interactions.")
        return count

    # ─────────────────────────────────────────────────────────
    # Décision de réentraînement
    # ─────────────────────────────────────────────────────────
    def should_retrain(self) -> bool:
        """
        Retourne True si le nombre de nouvelles interactions
        dépasse le seuil de réentraînement configuré.
        """
        return (
            self.config.AUTO_RETRAIN and
            self._new_count >= self.config.RETRAIN_THRESHOLD
        )

    def reset_counter(self):
        """Remet à zéro le compteur après réentraînement."""
        self._new_count = 0
        logger.info("Compteur d'apprentissage remis à zéro.")

    # ─────────────────────────────────────────────────────────
    # Statistiques
    # ─────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Retourne les statistiques d'apprentissage."""
        total = self._count_learned()
        return {
            "total_learned":      total,
            "since_last_retrain": self._new_count,
            "retrain_threshold":  self.config.RETRAIN_THRESHOLD,
            "next_retrain_in":    max(0, self.config.RETRAIN_THRESHOLD - self._new_count),
        }

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _count_learned(self) -> int:
        """Compte les interactions déjà apprises."""
        path = self.config.LEARNED_DATA_PATH
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    def _build_instruction(self, user_text: str, human_response: str, history: list) -> str:
        """
        Reconstruit une instruction au format du dataset principal.
        Format: "USER: ... | BOT: ... | USER: ..."
        """
        parts = ["USER: عسلامة", "BOT: مرحبا بيك في تليكوم، كيفاش نجم نعاونك؟"]

        if history:
            for role, text in history[-6:]:  # 6 derniers tours
                prefix = "USER" if role == "user" else "BOT"
                parts.append(f"{prefix}: {text}")
        else:
            parts.append(f"USER: {user_text}")

        return " | ".join(parts)
