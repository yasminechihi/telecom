# ============================================================
#  modules/dialog_manager.py — Gestionnaire de Dialogue
#  Orchestre tous les modules du VoiceBot
# ============================================================

import json
import logging
import os
from datetime import datetime
from enum import Enum, auto

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """États possibles de la conversation."""
    INIT          = auto()   # Démarrage
    GREETING      = auto()   # Salutation envoyée
    LISTENING     = auto()   # En attente de la parole client
    PROCESSING    = auto()   # Traitement de la requête
    RESPONDING    = auto()   # Réponse envoyée
    CLARIFYING    = auto()   # Demande de clarification
    TRANSFERRING  = auto()   # Transfert vers humain en cours
    RESOLVED      = auto()   # Problème résolu
    ENDED         = auto()   # Conversation terminée


class DialogManager:
    """
    Gestionnaire de dialogue — cerveau du VoiceBot.

    Responsabilités :
        - Orchestrer le flux STT → NLU → RAG → TTS
        - Maintenir l'état et l'historique de la conversation
        - Décider quand demander une clarification
        - Décider quand transférer vers un agent humain
        - Logger toutes les interactions
    """

    def __init__(self, config, stt, tts, nlu, engine, transfer, learning):
        self.config   = config
        self.stt      = stt
        self.tts      = tts
        self.nlu      = nlu
        self.engine   = engine
        self.transfer = transfer
        self.learning = learning

        # État de la conversation
        self.state           = ConversationState.INIT
        self.history         = []        # [(role, text), ...]
        self.turn_count      = 0
        self.failed_attempts = 0
        self.session_id      = self._generate_session_id()
        self.session_data    = {
            "session_id":  self.session_id,
            "start_time":  datetime.now().isoformat(),
            "turns":       [],
            "resolved":    False,
            "transferred": False,
        }

        logger.info(f"DialogManager initialisé — session: {self.session_id}")

    # ─────────────────────────────────────────────────────────
    # Boucle principale de conversation
    # ─────────────────────────────────────────────────────────
    def run(self):
        """
        Lance la boucle principale du VoiceBot.
        S'exécute jusqu'à fin de conversation ou transfert.
        """
        try:
            self._greet()

            while self.state not in (ConversationState.ENDED, ConversationState.TRANSFERRING):
                # Vérification du nombre max de tours
                if self.turn_count >= self.config.MAX_TURNS:
                    logger.info("Nombre max de tours atteint.")
                    self._end_conversation(resolved=False)
                    break

                # Écoute le client
                self.state = ConversationState.LISTENING
                user_text  = self.stt.listen_and_transcribe()

                # Rien entendu → redemander
                if not user_text:
                    self._handle_silence()
                    continue

                # Traitement
                self.state = ConversationState.PROCESSING
                self._process_turn(user_text)

        except KeyboardInterrupt:
            logger.info("Conversation interrompue (Ctrl+C).")
            self.tts.speak_farewell()
        except Exception as e:
            logger.error(f"Erreur critique dans DialogManager: {e}", exc_info=True)
            self.tts.speak("مشكلة تقنية، سامحنا. اتصل بنا لاحقا.")
        finally:
            self._save_session()

    # ─────────────────────────────────────────────────────────
    # Gestion d'un tour de parole
    # ─────────────────────────────────────────────────────────
    def _process_turn(self, user_text: str):
        """Traite un tour de parole utilisateur."""
        self.turn_count += 1
        self._add_to_history("user", user_text)

        # 1. Analyse NLU
        nlu_result = self.nlu.analyze(user_text)

        # 2. Mot-clé de fin ?
        if nlu_result.get("is_stop"):
            self._end_conversation(resolved=True)
            return

        # 3. Récupérer une réponse (RAG + ML combinés)
        self.tts.speak_wait()
        rag_result = self.engine.find_response(user_text, self.history)

        # 4. Décision ML (si disponible) prime sur RAG pour l'escalade
        ml_decision = nlu_result.get("decision", "reponse_automatique")
        if ml_decision == "escalade_agent_humain" and nlu_result.get("ml_used"):
            # Le moteur ML.ipynb recommande un transfert humain
            self.failed_attempts += 1
            if self.failed_attempts >= self.config.ESCALATION_ATTEMPTS:
                self._escalate_to_human(user_text, nlu_result, rag_result)
                return
            else:
                self._ask_clarification(nlu_result)
                return

        if rag_result["escalate"] and not nlu_result.get("ml_used"):
            self.failed_attempts += 1
            if self.failed_attempts >= self.config.ESCALATION_ATTEMPTS:
                self._escalate_to_human(user_text, nlu_result, rag_result)
                return
            else:
                self._ask_clarification(nlu_result)
                return

        # 5. Choisir la meilleure réponse :
        #    - RAG (similarité sémantique sur dataset darija) si score ≥ seuil
        #    - ML response (predict_response de ML.ipynb) comme fallback
        self.failed_attempts = 0
        response = rag_result.get("response", "")
        if not response and nlu_result.get("ml_response"):
            response = nlu_result["ml_response"]
            logger.info("Réponse fournie par le modèle ML.ipynb (response_model).")
        if not response:
            response = self.config.NOT_UNDERSTOOD_MSG

        self.state = ConversationState.RESPONDING
        self.tts.speak(response)
        self._add_to_history("bot", response)

        # Logger le tour
        self._log_turn(user_text, nlu_result, rag_result, response)
        logger.info(
            f"[Tour {self.turn_count}] "
            f"intent='{nlu_result.get('intent','')}' | "
            f"sentiment='{nlu_result.get('sentiment','')}' | "
            f"service='{nlu_result.get('entities',{}).get('service_type','')}' | "
            f"RAG={rag_result.get('confidence',0):.2f} | "
            f"ML={'✅' if nlu_result.get('ml_used') else '⚙️ règles'}"
        )

        # 6. Vérifier si résolu
        if self._is_resolved(rag_result, nlu_result):
            self._ask_if_satisfied()

    # ─────────────────────────────────────────────────────────
    # Salutation et clôture
    # ─────────────────────────────────────────────────────────
    def _greet(self):
        """Envoie le message de bienvenue."""
        self.state = ConversationState.GREETING
        self.tts.speak_greeting()
        self._add_to_history("bot", self.config.GREETING_MESSAGE)

    def _end_conversation(self, resolved: bool = True):
        """Termine la conversation proprement."""
        self.state = ConversationState.ENDED
        self.session_data["resolved"] = resolved
        self.tts.speak_farewell()
        logger.info(f"Conversation terminée — résolu: {resolved}")

    def _ask_if_satisfied(self):
        """Demande au client si le problème est résolu."""
        self.tts.speak("تحل مشكلتك؟ إذا عندك شي آخر نجم نعاونك فيه؟")
        self._add_to_history("bot", "تحل مشكلتك؟ إذا عندك شي آخر نجم نعاونك فيه؟")

    def _ask_clarification(self, nlu_result: dict):
        """Demande une clarification au client."""
        self.state = ConversationState.CLARIFYING
        intent = nlu_result.get("intent", "unknown")

        clarification_msgs = {
            "reseau_mobile":  "الخدمة موبيل ولا فيكس؟",
            "paiement":       "الدفع عبر MyTT ولا حوالة بنكية؟",
            "wifi":           "مشكلة في الاتصال ولا في الجهاز نفسو؟",
            "internet_coupe": "من امتى الإنترنت منقطع؟",
        }

        msg = clarification_msgs.get(intent, self.config.NOT_UNDERSTOOD_MSG)
        self.tts.speak(msg)
        self._add_to_history("bot", msg)

    def _handle_silence(self):
        """Gère l'absence de réponse du client."""
        self.failed_attempts += 1
        if self.failed_attempts >= 3:
            self.tts.speak("ما سمعتكش، نحولك لوكيل بشري.")
            self._escalate_to_human("", {}, {})
        else:
            self.tts.speak("ما سمعتك برشا، قادر تعاود تقول؟")

    # ─────────────────────────────────────────────────────────
    # Transfert vers agent humain
    # ─────────────────────────────────────────────────────────
    def _escalate_to_human(self, user_text: str, nlu_result: dict, rag_result: dict):
        """Transfère la conversation à un agent humain."""
        self.state = ConversationState.TRANSFERRING
        self.session_data["transferred"] = True

        logger.info("Transfert vers agent humain déclenché.")
        self.tts.speak_transfer()

        # Créer le ticket de transfert
        ticket = self.transfer.create_ticket(
            session_id       = self.session_id,
            history          = self.history,
            user_last_text   = user_text,
            nlu_result       = nlu_result,
            rag_confidence   = rag_result.get("confidence", 0),
        )

        # Attendre la résolution humaine (mode async)
        human_response = self.transfer.wait_for_human_response(ticket)
        if human_response:
            # Apprentissage de la nouvelle interaction
            self.learning.learn_from_human(
                user_text      = user_text,
                human_response = human_response,
                issue_type     = nlu_result.get("intent", ""),
                service_type   = rag_result.get("service_type", ""),
            )
            # Recharger l'index si seuil atteint
            if self.learning.should_retrain():
                self.engine.reload_index()

        self._end_conversation(resolved=bool(human_response))

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _is_resolved(self, rag_result: dict, nlu_result: dict) -> bool:
        """Détermine si le problème semble résolu."""
        return (
            rag_result.get("confidence", 0) >= self.config.RAG_EXACT_THRESHOLD
            and nlu_result.get("intent") != "unknown"
        )

    def _add_to_history(self, role: str, text: str):
        """Ajoute un tour à l'historique."""
        self.history.append((role, text))

    def _log_turn(self, user_text, nlu_result, rag_result, bot_response):
        """Enregistre le tour dans les données de session."""
        turn = {
            "turn":         self.turn_count,
            "user":         user_text,
            "intent":       nlu_result.get("intent", ""),
            "entities":     nlu_result.get("entities", {}),
            "sentiment":    nlu_result.get("sentiment", ""),
            "rag_score":    round(rag_result.get("confidence", 0), 3),
            "issue_type":   rag_result.get("issue_type", ""),
            "service_type": rag_result.get("service_type", ""),
            "bot":          bot_response,
            "escalated":    rag_result.get("escalate", False),
        }
        self.session_data["turns"].append(turn)

    def _save_session(self):
        """Sauvegarde la session dans les logs."""
        if not self.config.LOG_CONVERSATIONS:
            return
        self.session_data["end_time"] = datetime.now().isoformat()
        os.makedirs(self.config.LOGS_DIR, exist_ok=True)
        with open(self.config.CONVERSATION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.session_data, ensure_ascii=False) + "\n")
        logger.debug(f"Session sauvegardée: {self.session_id}")

    def _generate_session_id(self) -> str:
        """Génère un identifiant de session unique."""
        return datetime.now().strftime("TT_%Y%m%d_%H%M%S")
