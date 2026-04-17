# ============================================================
#  modules/clarification.py — Stratégie de Clarification
#  Le bot pose des questions intelligentes avant de répondre
# ============================================================
#
#  Principe :
#    Tour 1 : Client exprime son problème (vague ou précis)
#    Tour 2 : Bot pose 1 question de précision (service? localisation?)
#    Tour 3 : Bot a assez de contexte → répond avec RAG
#
#  Inspiré du flow des vrais agents de Tunisie Telecom
# ============================================================

import re
import logging

logger = logging.getLogger(__name__)

# ── Questions de clarification par intent ────────────────────
# Format : intent → liste de questions (on pose la 1ère pertinente)
CLARIFICATION_MAP = {

    "عطل في الشبكه": [
        {
            "condition": lambda e: not e.get("service_type"),
            "question":  "الخدمة موبيل ولا فيكس (ADSL / Fibre)؟"
        },
        {
            "condition": lambda e: not e.get("wilaya"),
            "question":  "فين بالضبط تسكن؟ قولي الولاية."
        },
        {
            "condition": lambda _: True,
            "question":  "المشكلة بدات امتى؟ وهل عندك شريط شبكة ولا لا شيء خالص؟"
        },
    ],

    "انقطاع الانترنت": [
        {
            "condition": lambda e: not e.get("service_type"),
            "question":  "الانترنت عندك ADSL، Fibre، ولا موبيل 4G/5G؟"
        },
        {
            "condition": lambda _: True,
            "question":  "كانش ضوء أحمر في الراوتر؟ وجربت تعيد تشغيله؟"
        },
    ],

    "مشكله في اشاره الويفي": [
        {
            "condition": lambda _: True,
            "question":  "الراوتر / Box عندك — شنوة لون الضوء؟ وفين تحس بالمشكلة، قدام الراوتر ولا بعيد؟"
        },
    ],

    "بطء في الانترنت": [
        {
            "condition": lambda e: not e.get("service_type"),
            "question":  "نوع الاشتراك عندك ADSL، VDSL، ولا Fibre؟"
        },
        {
            "condition": lambda _: True,
            "question":  "البطء في كل الأجهزة ولا جهاز واحد بالذات؟ وكانش مشكلة في فيديو / تحميل بالخصوص؟"
        },
    ],

    "مشكله في الدفع": [
        {
            "condition": lambda e: not e.get("transaction_id"),
            "question":  "الدفع كان عبر MyTT ولا حوالة بنكية؟ وعندك رقم المعاملة (numéro de transaction)؟"
        },
        {
            "condition": lambda _: True,
            "question":  "الخط لتوا مقطوع ولا لا زال يخدم؟"
        },
    ],

    "اعتراض على الفاتوره": [
        {
            "condition": lambda _: True,
            "question":  "الفاتورة تاعة أنهي شهر؟ وشنوة المبلغ اللي تعترض عليه بالضبط؟"
        },
    ],

    "مشكله في الجوال": [
        {
            "condition": lambda _: True,
            "question":  "أنت لبرا في أنهي بلاد بالضبط؟ وعندك خدمة Roaming مفعّلة في حسابك؟"
        },
    ],

    "تاخير في التركيب": [
        {
            "condition": lambda _: True,
            "question":  "عندك رقم الطلب (numéro de commande)؟ ومتى كان الموعد المبرمج؟"
        },
    ],

    "تبديل شريحه": [
        {
            "condition": lambda e: not e.get("phone_number"),
            "question":  "أعطيني رقم هاتفك باش نثبت في حسابك."
        },
    ],

    "استفسار عن الرصيد": [
        {
            "condition": lambda e: not e.get("phone_number"),
            "question":  "أعطيني رقم هاتفك، ولا تنجم ترسل *100# من تليفونك باش تعرف رصيدك مباشرة."
        },
    ],

    "استفسار عن العروض": [
        {
            "condition": lambda e: not e.get("service_type"),
            "question":  "تحب تعرف عروض الموبيل، الانترنت، ولا الاشتراك المنزلي (Fixe/Fibre)؟"
        },
    ],

    "استفسار عن التغطيه": [
        {
            "condition": lambda e: not e.get("wilaya"),
            "question":  "أي منطقة تسأل على التغطية فيها بالضبط؟"
        },
    ],

    "عطب في الجهاز": [
        {
            "condition": lambda _: True,
            "question":  "شنوة الجهاز بالضبط — décodeur، routeur، ولا هاتف؟ وشنوة المشكلة اللي تشوفها؟"
        },
    ],
}

# ── Réponses de confirmation après clarification ─────────────
UNDERSTOOD_PHRASES = [
    "مفهوم، ",
    "واضح، ",
    "حاضر، ",
    "فاهم المشكلة، ",
]

import random


class ClarificationEngine:
    """
    Gère la stratégie de clarification multi-tours.

    Intégré dans app.py — maintient un état par session :
        {
          "clarification_count": int,   # Nb de questions déjà posées
          "clarification_done":  bool,  # True quand on a assez d'infos
          "collected_entities":  dict,  # Entités accumulées sur plusieurs tours
        }
    """

    def __init__(self, config):
        self.config = config

    # ─────────────────────────────────────────────────────────
    # Décision : faut-il clarifier ?
    # ─────────────────────────────────────────────────────────
    def should_clarify(self, session: dict, nlu_result: dict) -> bool:
        """
        Retourne True si le bot doit poser une question de clarification
        plutôt que de répondre directement.

        Conditions :
          - Clarification activée dans config
          - Intent connu (sinon inutile de clarifier)
          - N'a pas déjà posé trop de questions
          - Il manque encore des informations clés
        """
        if not self.config.CLARIFICATION_ENABLED:
            return False

        intent  = nlu_result.get("intent", "")
        if intent in ("غير محدد", "unknown", "", "salutation", "au_revoir"):
            return False

        count = session.get("clarification_count", 0)
        if count >= self.config.MAX_CLARIFICATION_TURNS:
            return False

        # Vérifier si on a une question pertinente pour cet intent
        return self._get_question(intent, session) is not None

    # ─────────────────────────────────────────────────────────
    # Générer la question de clarification
    # ─────────────────────────────────────────────────────────
    def get_clarification_question(self, session: dict, nlu_result: dict) -> str:
        """
        Retourne la question de clarification la plus pertinente
        en fonction de l'intent et des entités déjà collectées.
        """
        intent   = nlu_result.get("intent", "")
        question = self._get_question(intent, session)

        if not question:
            return ""

        # Incrémenter le compteur
        session["clarification_count"] = session.get("clarification_count", 0) + 1
        # Mémoriser l'intent pour la suite
        session["pending_intent"] = intent

        return question

    def _get_question(self, intent: str, session: dict) -> str:
        """Trouve la première question pertinente non encore posée."""
        intent_clean = self._normalize_intent(intent)

        # Cherche dans la map par correspondance partielle
        matched_key = None
        for key in CLARIFICATION_MAP:
            if self._normalize_intent(key) in intent_clean or intent_clean in self._normalize_intent(key):
                matched_key = key
                break

        if not matched_key:
            return None

        # Entités déjà collectées (de tous les tours précédents)
        entities = session.get("collected_entities", {})
        questions_asked = session.get("questions_asked", [])

        for item in CLARIFICATION_MAP[matched_key]:
            q = item["question"]
            if q in questions_asked:
                continue
            try:
                if item["condition"](entities):
                    # Marquer comme posée
                    if "questions_asked" not in session:
                        session["questions_asked"] = []
                    session["questions_asked"].append(q)
                    return q
            except Exception:
                continue

        return None

    # ─────────────────────────────────────────────────────────
    # Mise à jour des entités collectées
    # ─────────────────────────────────────────────────────────
    def update_entities(self, session: dict, nlu_result: dict):
        """
        Accumule les entités extraites sur plusieurs tours.
        Ex: la wilaya peut être mentionnée au tour 2, le service au tour 1.
        """
        if "collected_entities" not in session:
            session["collected_entities"] = {}

        new_entities = nlu_result.get("entities", {})
        for k, v in new_entities.items():
            if v:  # Ne mettre à jour que si la valeur est non nulle
                session["collected_entities"][k] = v

    # ─────────────────────────────────────────────────────────
    # Construire la requête enrichie pour le RAG
    # ─────────────────────────────────────────────────────────
    def build_enriched_query(self, session: dict, current_text: str) -> str:
        """
        Combine tous les tours utilisateur pour créer une requête
        contextuellement riche pour le RAG.
        """
        history = session.get("history", [])
        user_turns = [t for role, t in history if role == "user"]

        # Ajouter les entités collectées comme contexte textuel
        entities = session.get("collected_entities", {})
        entity_context = " ".join(filter(None, [
            entities.get("service_type", ""),
            entities.get("wilaya", ""),
            entities.get("delegation", ""),
        ]))

        combined = " ".join(user_turns[-3:])  # 3 derniers tours user
        if entity_context:
            combined = f"{entity_context} {combined}"

        return combined.strip() or current_text

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _normalize_intent(self, text: str) -> str:
        text = re.sub(r'\s+', '', str(text).strip())
        return text.replace('أ','ا').replace('إ','ا').replace('ة','ه').lower()
