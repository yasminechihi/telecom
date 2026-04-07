# ============================================================
#  modules/human_transfer.py — Module Transfert Agent Humain
#  Gestion de l'escalade et de la file d'attente humaine
# ============================================================

import json
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class HumanTransfer:
    """
    Module de transfert vers un agent humain.

    Rôles :
        1. Créer un ticket dans la file d'attente
        2. Notifier l'agent humain (fichier / email / webhook)
        3. Attendre la réponse de l'agent humain (polling)
        4. Retourner la réponse au DialogManager pour apprentissage

    En production, ce module s'interface avec :
        - Le système CRM de Tunisie Telecom
        - La file ACD (Automatic Call Distribution)
        - Une interface agent web/mobile
    """

    def __init__(self, config):
        self.config = config
        os.makedirs(config.DATA_DIR,  exist_ok=True)
        os.makedirs(config.LOGS_DIR,  exist_ok=True)
        logger.info("HumanTransfer initialisé.")

    # ─────────────────────────────────────────────────────────
    # Création de ticket
    # ─────────────────────────────────────────────────────────
    def create_ticket(
        self,
        session_id: str,
        history: list,
        user_last_text: str,
        nlu_result: dict,
        rag_confidence: float,
    ) -> dict:
        """
        Crée un ticket de transfert et l'ajoute à la file d'attente.

        Returns:
            Dictionnaire ticket avec un ID unique.
        """
        ticket_id = f"TKT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session_id[-6:]}"

        # Résumé de la conversation pour l'agent humain
        conversation_summary = self._build_summary(history)

        ticket = {
            "ticket_id":      ticket_id,
            "session_id":     session_id,
            "timestamp":      datetime.now().isoformat(),
            "status":         "pending",           # pending | in_progress | resolved
            "priority":       self._get_priority(nlu_result),
            "issue_summary":  conversation_summary,
            "last_user_msg":  user_last_text,
            "intent":         nlu_result.get("intent", "unknown"),
            "entities":       nlu_result.get("entities", {}),
            "sentiment":      nlu_result.get("sentiment", "neutre"),
            "rag_confidence": round(rag_confidence, 3),
            "conversation":   [
                {"role": role, "text": text}
                for role, text in history
            ],
            "human_response": None,  # À remplir par l'agent
            "agent_id":       None,
            "resolution_time": None,
        }

        # Sauvegarder dans la file d'attente
        self._write_to_queue(ticket)
        logger.info(f"Ticket créé: {ticket_id} | priorité: {ticket['priority']}")

        return ticket

    # ─────────────────────────────────────────────────────────
    # File d'attente
    # ─────────────────────────────────────────────────────────
    def _write_to_queue(self, ticket: dict):
        """Écrit le ticket dans le fichier de file d'attente."""
        with open(self.config.HUMAN_AGENT_QUEUE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ticket, ensure_ascii=False) + "\n")

    def get_pending_tickets(self) -> list:
        """Retourne tous les tickets en attente (pour l'interface agent)."""
        tickets = []
        if not os.path.exists(self.config.HUMAN_AGENT_QUEUE):
            return tickets
        with open(self.config.HUMAN_AGENT_QUEUE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    if t.get("status") == "pending":
                        tickets.append(t)
                except json.JSONDecodeError:
                    continue
        return tickets

    def resolve_ticket(self, ticket_id: str, human_response: str, agent_id: str = "agent_01"):
        """
        Marque un ticket comme résolu et enregistre la réponse humaine.
        Appelé depuis l'interface de l'agent humain.
        """
        if not os.path.exists(self.config.HUMAN_AGENT_QUEUE):
            return False

        lines = []
        found = False
        with open(self.config.HUMAN_AGENT_QUEUE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    if t.get("ticket_id") == ticket_id:
                        t["status"]          = "resolved"
                        t["human_response"]  = human_response
                        t["agent_id"]        = agent_id
                        t["resolution_time"] = datetime.now().isoformat()
                        found = True
                    lines.append(json.dumps(t, ensure_ascii=False))
                except json.JSONDecodeError:
                    lines.append(line.strip())

        if found:
            with open(self.config.HUMAN_AGENT_QUEUE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            logger.info(f"Ticket résolu: {ticket_id}")
        return found

    # ─────────────────────────────────────────────────────────
    # Attente de réponse humaine
    # ─────────────────────────────────────────────────────────
    def wait_for_human_response(self, ticket: dict, timeout: int = 300) -> str:
        """
        Attend (polling) la réponse d'un agent humain.

        En production, remplacer par un webhook / WebSocket.

        Args:
            ticket:  Ticket de transfert
            timeout: Délai max en secondes (défaut 5 min)

        Returns:
            Réponse de l'agent humain ou "" si timeout.
        """
        ticket_id   = ticket.get("ticket_id")
        start_time  = time.time()
        poll_interval = 5  # secondes

        logger.info(f"Attente réponse humaine pour ticket {ticket_id} (timeout: {timeout}s)...")

        while time.time() - start_time < timeout:
            response = self._check_ticket_response(ticket_id)
            if response:
                logger.info(f"Réponse humaine reçue pour {ticket_id}: '{response[:50]}...'")
                return response
            time.sleep(poll_interval)

        logger.warning(f"Timeout: pas de réponse humaine pour {ticket_id}.")
        return ""

    def _check_ticket_response(self, ticket_id: str) -> str:
        """Vérifie si un ticket a été résolu par un agent humain."""
        if not os.path.exists(self.config.HUMAN_AGENT_QUEUE):
            return ""
        with open(self.config.HUMAN_AGENT_QUEUE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    if t.get("ticket_id") == ticket_id and t.get("status") == "resolved":
                        return t.get("human_response", "")
                except json.JSONDecodeError:
                    continue
        return ""

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _build_summary(self, history: list) -> str:
        """Construit un résumé de la conversation pour l'agent."""
        if not history:
            return "Pas d'historique disponible."
        lines = []
        for role, text in history[-10:]:  # Derniers 10 tours
            prefix = "Client" if role == "user" else "BOT"
            lines.append(f"{prefix}: {text}")
        return " | ".join(lines)

    def _get_priority(self, nlu_result: dict) -> str:
        """Détermine la priorité du ticket selon le sentiment et l'intent."""
        sentiment = nlu_result.get("sentiment", "neutre")
        intent    = nlu_result.get("intent", "")

        critical_intents = {"internet_coupe", "reseau_mobile", "paiement"}

        if sentiment == "négatif" and intent in critical_intents:
            return "haute"
        elif sentiment == "négatif":
            return "moyenne"
        return "normale"
