# ============================================================
#  modules/nlu.py — Natural Language Understanding
#  Stratégie hybride : Modèles ML (ML.ipynb) + Règles regex
#
#  Priorité :
#    1. MLPredictor (TF-IDF + LogisticRegression de ML.ipynb)
#       → issue_type, sentiment, service, wilaya, action, decision
#    2. Règles regex (fallback si modèles non disponibles)
# ============================================================

import re
import logging

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  Mapping délégation → gouvernorat (pour correction NLU)
#  Si l'user mentionne explicitement une délégation/ville,
#  on corrige la wilaya même si le ML l'a mal prédicte.
# ══════════════════════════════════════════════════════════════
DELEGATION_WILAYA_MAP = {
    # ── 1. تونس ──────────────────────────────────────────────────
    "تونس": "تونس",               "تونس المدينة": "تونس",
    "باب البحر": "تونس",          "باب سويقة": "تونس",
    "سيدي البشير": "تونس",        "الزهور": "تونس",
    "السيجومي": "تونس",           "العمران": "تونس",
    "العمران الأعلى": "تونس",     "التحرير": "تونس",
    "المنزه": "تونس",             "حي الخضراء": "تونس",
    "الكبارية": "تونس",           "جبل الجلود": "تونس",
    "المرسى": "تونس",             "قرطاج": "تونس",
    "حلق الوادي": "تونس",         "باردو": "تونس",
    "التضامن": "تونس",            "الملاسين": "تونس",
    "الوردية": "تونس",            "سيدي حسين": "تونس",
    "الكرم": "تونس",
    # ── 2. أريانة ────────────────────────────────────────────────
    "أريانة": "أريانة",           "اريانة": "أريانة",
    "أريانة المدينة": "أريانة",   "سكرة": "أريانة",
    "رواد": "أريانة",             "قلعة الأندلس": "أريانة",
    "المنيهلة": "أريانة",         "سيدي ثابت": "أريانة",
    # ── 3. بن عروس ───────────────────────────────────────────────
    "بن عروس": "بن عروس",         "المروج": "بن عروس",
    "حمام الأنف": "بن عروس",      "حمام الشط": "بن عروس",
    "بومهل البساتين": "بن عروس",  "رادس": "بن عروس",
    "مقرين": "بن عروس",           "فوشانة": "بن عروس",
    "المحمدية": "بن عروس",        "مرناق": "بن عروس",
    "الزهراء": "بن عروس",         "بوعرقوب": "بن عروس",
    # ── 4. منوبة ─────────────────────────────────────────────────
    "منوبة": "منوبة",             "دوار هيشر": "منوبة",
    "وادي الليل": "منوبة",        "طبربة": "منوبة",
    "الجديدة": "منوبة",           "المرناقية": "منوبة",
    "برج العامري": "منوبة",       "البطان": "منوبة",
    # ── 5. نابل ──────────────────────────────────────────────────
    "نابل": "نابل",               "دار شعبان الفهري": "نابل",
    "بني خيار": "نابل",           "الحمامات": "نابل",
    "سليمان": "نابل",             "قرمبالية": "نابل",
    "منزل بوزلفة": "نابل",        "تاكلسة": "نابل",
    "الهوارية": "نابل",           "قربة": "نابل",
    "الميدة": "نابل",             "بني خلاد": "نابل",
    "منزل تميم": "نابل",          "قليبية": "نابل",
    "اقليبية": "نابل",            "أقليبية": "نابل",
    "حمام الغزاز": "نابل",        "بوفيشة": "نابل",
    # ── 6. زغوان ─────────────────────────────────────────────────
    "زغوان": "زغوان",             "الفحص": "زغوان",
    "بئر مشارقة": "زغوان",        "الناظور": "زغوان",
    "الزريبة": "زغوان",           "صواف": "زغوان",
    # ── 7. بنزرت ─────────────────────────────────────────────────
    "بنزرت": "بنزرت",             "بنزرت الشمالية": "بنزرت",
    "بنزرت الجنوبية": "بنزرت",    "جرزونة": "بنزرت",
    "منزل بورقيبة": "بنزرت",      "منزل جميل": "بنزرت",
    "العالية": "بنزرت",           "رأس الجبل": "بنزرت",
    "غار الملح": "بنزرت",         "سجنان": "بنزرت",
    "ماطر": "بنزرت",              "جومين": "بنزرت",
    "غزالة": "بنزرت",             "تينجة": "بنزرت",
    "أوتيك": "بنزرت",
    # ── 8. باجة ──────────────────────────────────────────────────
    "باجة": "باجة",               "باجة الشمالية": "باجة",
    "باجة الجنوبية": "باجة",      "عمدون": "باجة",
    "نفزة": "باجة",               "تستور": "باجة",
    "تيبار": "باجة",              "مجاز الباب": "باجة",
    "قبلاط": "باجة",              "تبرسق": "باجة",
    # ── 9. جندوبة ────────────────────────────────────────────────
    "جندوبة": "جندوبة",           "جندوبة الشمالية": "جندوبة",
    "بوسالم": "جندوبة",           "بلطة بوعوان": "جندوبة",
    "طبرقة": "جندوبة",            "عين دراهم": "جندوبة",
    "غار الدماء": "جندوبة",       "فرنانة": "جندوبة",
    "الفرنانة": "جندوبة",         "وادي مليز": "جندوبة",
    # ── 10. الكاف ────────────────────────────────────────────────
    "الكاف": "الكاف",             "الكاف الشرقية": "الكاف",
    "الكاف الغربية": "الكاف",     "تاجروين": "الكاف",
    "الدهماني": "الكاف",          "السرس": "الكاف",
    "نبر": "الكاف",               "قلعة سنان": "الكاف",
    "ساقية سيدي يوسف": "الكاف",   "الجريصة": "الكاف",
    "القلعة الخصبة": "الكاف",     "الطويرف": "الكاف",
    # ── 11. سليانة ───────────────────────────────────────────────
    "سليانة": "سليانة",           "سليانة الشمالية": "سليانة",
    "سليانة الجنوبية": "سليانة",  "الكريب": "سليانة",
    "بوعرادة": "سليانة",          "قعفور": "سليانة",
    "الروحية": "سليانة",          "برقو": "سليانة",
    "مكثر": "سليانة",             "كسرى": "سليانة",
    "سيدي بورويس": "سليانة",      "العروسة": "سليانة",
    # ── 12. القيروان ─────────────────────────────────────────────
    "القيروان": "القيروان",        "القيروان الشمالية": "القيروان",
    "القيروان الجنوبية": "القيروان","الشبيكة": "القيروان",
    "السبيخة": "القيروان",        "الوسلاتية": "القيروان",
    "حفوز": "القيروان",           "العلا": "القيروان",
    "نصر الله": "القيروان",       "حاجب العيون": "القيروان",
    "منزل المهيري": "القيروان",   "الشراردة": "القيروان",
    "بوحجلة": "القيروان",         "عين جلولة": "القيروان",
    # ── 13. القصرين ──────────────────────────────────────────────
    "القصرين": "القصرين",         "قصرين": "القصرين",
    "القصرين الشمالية": "القصرين","القصرين الجنوبية": "القصرين",
    "سبيبة": "القصرين",           "سبيطلة": "القصرين",
    "تالة": "القصرين",            "حاسي الفريد": "القصرين",
    "فوسانة": "القصرين",          "فريانة": "القصرين",
    "ماجل بلعباس": "القصرين",     "جدليان": "القصرين",
    "العيون": "القصرين",          "حيدرة": "القصرين",
    # ── 14. سيدي بوزيد ───────────────────────────────────────────
    "سيدي بوزيد": "سيدي بوزيد",   "سيدي بوزيد الغربية": "سيدي بوزيد",
    "سيدي بوزيد الشرقية": "سيدي بوزيد", "الرقاب": "سيدي بوزيد",
    "المكناسي": "سيدي بوزيد",     "منزل بوزيان": "سيدي بوزيد",
    "بئر الحفي": "سيدي بوزيد",    "جلمة": "سيدي بوزيد",
    "السبالة": "سيدي بوزيد",      "المزونة": "سيدي بوزيد",
    "السوق الجديد": "سيدي بوزيد", "أولاد حفوز": "سيدي بوزيد",
    "السعيدة": "سيدي بوزيد",
    # ── 15. سوسة ─────────────────────────────────────────────────
    "سوسة": "سوسة",               "سوسة المدينة": "سوسة",
    "سوسة جوهرة": "سوسة",         "سوسة الرياض": "سوسة",
    "سوسة سيدي عبد الحميد": "سوسة","مساكن": "سوسة",
    "القلعة الكبرى": "سوسة",      "القلعة الصغرى": "سوسة",
    "أكودة": "سوسة",              "حمام سوسة": "سوسة",
    "هرقلة": "سوسة",              "كندار": "سوسة",
    "النفيضة": "سوسة",
    # ── 16. المنستير ─────────────────────────────────────────────
    "المنستير": "المنستير",        "قصر هلال": "المنستير",
    "قصيبة المديوني": "المنستير",  "طبلبة": "المنستير",
    "المكنين": "المنستير",         "جمال": "المنستير",
    "زرمدين": "المنستير",          "بني حسان": "المنستير",
    "وردانين": "المنستير",         "الساحلين": "المنستير",
    "صيادة": "المنستير",           "لمطة": "المنستير",
    "بوحجر": "المنستير",
    # ── 17. المهدية ──────────────────────────────────────────────
    "المهدية": "المهدية",          "قصور الساف": "المهدية",
    "الشابة": "المهدية",           "ملولش": "المهدية",
    "سيدي علوان": "المهدية",       "أولاد الشامخ": "المهدية",
    "بومرداس": "المهدية",          "هبيرة": "المهدية",
    "السواسي": "المهدية",          "كركر": "المهدية",
    "البرادعة": "المهدية",         "الجم": "المهدية",
    # ── 18. صفاقس ────────────────────────────────────────────────
    "صفاقس": "صفاقس",             "صفاقس المدينة": "صفاقس",
    "صفاقس الغربية": "صفاقس",     "صفاقس الجنوبية": "صفاقس",
    "ساقية الزيت": "صفاقس",       "ساقية الدائر": "صفاقس",
    "جبنيانة": "صفاقس",           "العامرة": "صفاقس",
    "المحرس": "صفاقس",            "عقارب": "صفاقس",
    "قرقنة": "صفاقس",             "منزل شاكر": "صفاقس",
    "بئر علي بن خليفة": "صفاقس",  "الصخيرة": "صفاقس",
    "الغريبة": "صفاقس",           "الحنشة": "صفاقس",
    "منزل شكار": "صفاقس",
    # ── 19. قفصة ─────────────────────────────────────────────────
    "قفصة": "قفصة",               "قفصة الشمالية": "قفصة",
    "قفصة الجنوبية": "قفصة",      "الرديف": "قفصة",
    "المتلوي": "قفصة",            "أم العرائس": "قفصة",
    "المظيلة": "قفصة",            "سيدي عيش": "قفصة",
    "القطار": "قفصة",             "بلخير": "قفصة",
    "زانوش": "قفصة",              "السند": "قفصة",
    # ── 20. توزر ─────────────────────────────────────────────────
    "توزر": "توزر",               "دقاش": "توزر",
    "نفطة": "توزر",               "تمغزة": "توزر",
    "حامة الجريد": "توزر",
    # ── 21. قبلي ─────────────────────────────────────────────────
    "قبلي": "قبلي",               "قبلي الشمالية": "قبلي",
    "قبلي الجنوبية": "قبلي",      "سوق الأحد": "قبلي",
    "دوز الشمالية": "قبلي",       "دوز الجنوبية": "قبلي",
    "الفوار": "قبلي",             "رجيم معتوق": "قبلي",
    "دوز": "قبلي",
    # ── 22. قابس ─────────────────────────────────────────────────
    "قابس": "قابس",               "قابس المدينة": "قابس",
    "قابس الغربية": "قابس",       "قابس الجنوبية": "قابس",
    "الحامة": "قابس",             "مارث": "قابس",
    "مطماطة": "قابس",             "مطماطة الجديدة": "قابس",
    "غنوش": "قابس",               "وذرف": "قابس",
    "منزل الحبيب": "قابس",
    # ── 23. مدنين ────────────────────────────────────────────────
    "مدنين": "مدنين",             "مدنين الشمالية": "مدنين",
    "مدنين الجنوبية": "مدنين",    "جرجيس": "مدنين",
    "بن قردان": "مدنين",          "بنقردان": "مدنين",
    "جربة حومة السوق": "مدنين",   "حومة السوق": "مدنين",
    "جربة ميدون": "مدنين",        "جربة أجيم": "مدنين",
    "سيدي مخلوف": "مدنين",        "بني خداش": "مدنين",
    "زرزيس": "مدنين",             "بوقرارة": "مدنين",
    "دڤاش": "توزر",
    # ── 24. تطاوين ───────────────────────────────────────────────
    "تطاوين": "تطاوين",           "تطاوين الشمالية": "تطاوين",
    "تطاوين الجنوبية": "تطاوين",  "غمراسن": "تطاوين",
    "رمادة": "تطاوين",            "البئر الأحمر": "تطاوين",
    "ذهيبة": "تطاوين",            "الصمار": "تطاوين",
}

# ── Patterns regex (fallback uniquement) ─────────────────────
INTENT_PATTERNS = {
    "عطل في الشبكه":              [r"ريزو|réseau|شبكة|كونيكسيون|4g|5g|3g|سيغنال|signal|باغ|ما عندي شبكة"],
    "بطء في الانترنت":             [r"بطي|lent|ما يمشيش|يقطع|تحميل|تنزيل|débits?|download|upload|vitesse|سرعة"],
    "انقطاع الانترنت":             [r"قطع|coupure|انقطع|ما عندي.*internet|ما فماش.*internet"],
    "مشكله في اشاره الويفي":       [r"وايفي|wifi|wi-fi|بوكس|box|livebox|routeur|راوتر"],
    "مشكله في الدفع":              [r"خلص|paiement|دفع|payé|facture|فاتورة|MyTT|virement|recharge"],
    "اعتراض على الفاتوره":         [r"فاتورة.*غالية|contestation|اعتراض.*فاتورة|مش عادل|erreur.*facture"],
    "استفسار عن الرصيد":           [r"رصيد|solde|كريديت|crédit|ما بقاش|consommation|استهلاك"],
    "استفسار عن العروض":           [r"عرض|offre|forfait|formule|abonnement|أبونمو|promotion"],
    "مشكله في الجوال":             [r"roaming|تجوال|برا|l'étranger|international|données.*itinérance"],
    "تاخير في التركيب":            [r"تركيب|installation|technicien|تقني|تأخير|date.*visite|موعد"],
    "تبديل شريحه":                 [r"sim|شريحة|بدل|remplacement|perdu|مفقودة|cassé|مكسورة"],
    "تغيير الخدمه":                [r"تغيير|changer|migration|upgrader|basculer|formule"],
    "عطب في الجهاز":               [r"جهاز|appareil|décodeur|IPTV|téléviseur|تلفزة|boîtier"],
    "استفسار عن التغطيه":          [r"تغطية|couverture|منطقة|zone|بعيد|rural|campagne|ريف"],
}

STOP_PATTERNS = [
    # Formules de clôture / adieu classiques (arabe + translittération + français)
    r"وداعا|باي|بسلامة|yezzi|خلاص|شكرن|merci|au revoir|fin|سلام",
    # Formules de remerciement en arabe (darija tunisienne) — avec et sans diacritiques
    #   يعطيك الصحة / يعطيك ألف صحة / يعطيك ألف الصحة / يعطيك صحة
    r"يعطيك\s*(?:الف)?\s*(?:ال)?\s*صحة",
    #   عيشك / يعيشك
    r"\bعيشك\b|\bيعيشك\b",
    #   يرحم والديك (+ variantes والدينك, والدك)
    r"يرحم\s*والد(?:ي|ي?ن)?ك|يرحم\s*بوك",
    #   بارك الله فيك
    r"بارك\s*الله\s*فيك",
    #   ربي يفضلك
    r"ربي\s*يفضلك|ربي\s*يعطيك|ربي\s*يبارك",
    #   شكرا / شكراً (diacritiques retirés par _normalize)
    r"\bشكرا\b|\bشكراً\b",
    # Translittérations latines (tout est comparé en lowercase par _normalize)
    r"\byaatik(?:\s+(?:el\s+)?s?saha|\s+alf\s+saha)?\b",
    r"\b(?:3)?aychek\b|\ba[iy]chek\b",
    r"\byarhem\s+weldik\b|\byarhem\s+bouk\b",
    r"\bbarak?a\s*(?:allah|l+ah)(?:ou?)?\s*(?:fi|fe)k\b",
    r"\brabbi\s+(?:y?fadhlek|y?baraklek|y?aatik)\b",
    r"\bchokran\b|\bshokran\b",
    r"\bmerci\s+beaucoup\b|\bthanks?\b|\bthank\s+you\b",
]


class NLUModule:
    """
    Module NLU hybride : ML.ipynb + règles regex de secours.

    Méthode principale : analyze(text) → dict complet
    avec intent, entités, sentiment, localisation, action, décision.
    """

    def __init__(self, config, ml_predictor=None):
        """
        Args:
            config:        Configuration globale
            ml_predictor:  Instance de MLPredictor (peut être None si
                           les modèles ne sont pas encore générés)
        """
        self.config       = config
        self.ml           = ml_predictor  # Injecté depuis voicebot_main.py
        self._patterns    = self._compile_patterns()
        self._stop_re     = re.compile("|".join(STOP_PATTERNS), re.IGNORECASE | re.UNICODE)

        if self.ml and self.ml.is_available:
            logger.info("NLU → Mode ML actif (modèles ML.ipynb chargés).")
        else:
            logger.warning("NLU → Mode règles regex (modèles ML.ipynb non disponibles).")

    # ─────────────────────────────────────────────────────────
    # Compilation des patterns regex
    # ─────────────────────────────────────────────────────────
    def _compile_patterns(self) -> dict:
        """Compile les regex pour de meilleures performances."""
        compiled = {}
        for intent, pats in INTENT_PATTERNS.items():
            compiled[intent] = re.compile("|".join(pats), re.IGNORECASE | re.UNICODE)
        return compiled

    # ─────────────────────────────────────────────────────────
    # Analyse principale
    # ─────────────────────────────────────────────────────────
    def analyze(self, text: str) -> dict:
        """
        Analyse complète d'un utterance client.

        Stratégie :
          - Si MLPredictor disponible → utilise generate_ai_output()
            de ML.ipynb pour toutes les prédictions
          - Sinon → fallback sur les règles regex

        Returns:
            {
                intent, confidence, sentiment, entities,
                wilaya, delegation, action, decision,
                is_stop, text, ml_used
            }
        """
        if not text:
            return self._empty_result(text)

        # Détection mot de clôture (prioritaire dans tous les cas)
        is_stop = bool(self._stop_re.search(self._normalize(text)))
        if is_stop:
            return {**self._empty_result(text), "is_stop": True}

        # ── Voie principale : Modèles ML (ML.ipynb) ───────────
        # Seuil minimum : si ML donne < 30% de confiance → regex plus fiable
        ML_MIN_CONFIDENCE = 0.30

        if self.ml and self.ml.is_available:
            try:
                ml_result = self._analyze_with_ml(text, is_stop=False)
                ml_conf   = ml_result.get("confidence", 0.0)

                if ml_conf >= ML_MIN_CONFIDENCE:
                    return ml_result

                # ML trop incertain → fusionner avec regex pour corriger l'intent
                import logging as _lg
                _lg.getLogger("nlu").info(
                    f"ML conf {ml_conf:.2f} < {ML_MIN_CONFIDENCE} → fusion regex"
                )
                regex_result = self._analyze_with_rules(text, is_stop=False)
                # Garder les entités ML (wilaya, délégation) mais prendre l'intent regex
                if regex_result.get("intent") not in ("غير محدد", "", None):
                    ml_result["intent"]      = regex_result["intent"]
                    ml_result["confidence"]  = regex_result.get("confidence", ml_conf)
                    ml_result["all_intents"] = regex_result.get("all_intents", [regex_result["intent"]])
                    # Garder les entités ML si regex n'en a pas détecté
                    for k in ("wilaya", "delegation", "service_type"):
                        if not ml_result["entities"].get(k) and regex_result["entities"].get(k):
                            ml_result["entities"][k] = regex_result["entities"][k]
                return ml_result

            except Exception as _ml_err:
                import logging as _lg
                _lg.getLogger("nlu").warning(
                    f"ML analyze failed ({type(_ml_err).__name__}) → fallback regex"
                )
                # Désactiver ML pour les prochains appels (éviter l'erreur répétée)
                try:
                    self.ml._loaded = False
                    self.ml._backend = None
                except Exception:
                    pass

        # ── Fallback : Règles regex ────────────────────────────
        return self._analyze_with_rules(text, is_stop=False)

    # ─────────────────────────────────────────────────────────
    # Analyse via MLPredictor (mode principal)
    # ─────────────────────────────────────────────────────────
    def _analyze_with_ml(self, text: str, is_stop: bool) -> dict:
        """Utilise les modèles de ML.ipynb pour l'analyse complète."""
        ml_output = self.ml.generate_ai_output(text)

        # Convertir la décision ML en flag d'escalade
        escalate = (ml_output["decision"] == "escalade_agent_humain")

        # Construire les entités ML d'abord
        entities = {
            "wilaya":         ml_output["wilaya"],
            "delegation":     ml_output["delegation"],
            "service_type":   ml_output["service_type"],
            "phone_number":   self._extract_phone(text),
            "transaction_id": self._extract_transaction(text),
        }

        # Correction : si l'user mentionne une ville/délégation dans son texte,
        # on corrige wilaya et delegation (le ML prédit souvent "تونس" par défaut)
        entities = self._fix_location_from_text(text, entities)

        # Cohérence ML : si aucune localisation explicite dans le texte mais que
        # le ML a prédit une délégation présente dans la map, on corrige la wilaya.
        # Exemple : ML prédit delegation="الشابة" wilaya="تونس" → on force wilaya="المهدية"
        if not entities.get("location_explicit", False):
            ml_deleg = entities.get("delegation", "")
            if ml_deleg and ml_deleg in DELEGATION_WILAYA_MAP:
                correct_wilaya = DELEGATION_WILAYA_MAP[ml_deleg]
                if entities.get("wilaya") != correct_wilaya:
                    logger.info(
                        f"[NLU] Cohérence ML : wilaya '{entities.get('wilaya')}' → '{correct_wilaya}' "
                        f"(délégation ML='{ml_deleg}' trouvée dans la map)"
                    )
                    entities["wilaya"] = correct_wilaya

        result = {
            # Champs NLU principaux
            "intent":       ml_output["issue_type"],
            "confidence":   ml_output["issue_confidence"],
            "all_intents":  [ml_output["issue_type"]],

            # Sentiment (prédit par ML.ipynb)
            "sentiment":    ml_output["sentiment"],

            # Entités corrigées
            "entities":     entities,

            # Décision et action recommandée
            "action":       ml_output["recommended_action"],
            "ml_response":  ml_output["ml_response"],   # Réponse directe ML
            "escalate":     escalate,
            "decision":     ml_output["decision"],

            # Métadonnées
            "is_stop":      is_stop,
            "text":         text,
            "ml_used":      True,
        }

        logger.debug(
            f"NLU (ML) → intent='{result['intent']}' "
            f"conf={result['confidence']:.2f} "
            f"sentiment='{result['sentiment']}' "
            f"decision='{result['decision']}'"
        )
        return result

    # ─────────────────────────────────────────────────────────
    # Fallback : Règles regex
    # ─────────────────────────────────────────────────────────
    def _analyze_with_rules(self, text: str, is_stop: bool) -> dict:
        """Analyse basée sur les règles regex (fallback)."""
        text_norm      = self._normalize(text)
        matched        = [i for i, p in self._patterns.items() if p.search(text_norm)]
        primary_intent = matched[0] if matched else "غير محدد"
        confidence     = min(0.75, 0.4 + 0.12 * len(matched)) if matched else 0.2

        sentiment      = self._rule_sentiment(text_norm)
        phone          = self._extract_phone(text)
        txn            = self._extract_transaction(text)
        service        = self._rule_service(text_norm)

        entities = {
            "wilaya":         None,
            "delegation":     None,
            "service_type":   service,
            "phone_number":   phone,
            "transaction_id": txn,
        }
        # Correction localisation depuis le texte brut (même en mode règles)
        entities = self._fix_location_from_text(text, entities)

        result = {
            "intent":      primary_intent,
            "confidence":  confidence,
            "all_intents": matched,
            "sentiment":   sentiment,
            "entities":    entities,
            "action":       "",
            "ml_response":  "",
            "escalate":     confidence < 0.5,
            "decision":     "reponse_automatique" if confidence >= 0.5 else "escalade_agent_humain",
            "is_stop":      is_stop,
            "text":         text,
            "ml_used":      False,
        }

        logger.debug(f"NLU (règles) → intent='{primary_intent}' conf={confidence:.2f}")
        return result

    # ─────────────────────────────────────────────────────────
    # Injection du MLPredictor (appelée après son chargement)
    # ─────────────────────────────────────────────────────────
    def set_ml_predictor(self, ml_predictor):
        """
        Permet d'injecter le MLPredictor après l'initialisation.
        Utile si les modèles sont générés en cours d'exécution.
        """
        self.ml = ml_predictor
        if self.ml and self.ml.is_available:
            logger.info("NLU → MLPredictor injecté avec succès.")

    # ─────────────────────────────────────────────────────────
    # Correction de localisation par scan du texte brut
    # ─────────────────────────────────────────────────────────
    @staticmethod
    def _normalize_ar(s: str) -> str:
        """
        Normalisation arabe pour la comparaison de localisation :
          - Supprime les diacritiques (تشكيل) : ً ٌ ٍ َ ُ ِ ّ ْ ...
          - Normalise les variantes de Alef : إ أ آ → ا
        Permet de matcher "قَصْر هِلال" = "قصر هلال", "أريانة" = "اريانة", etc.
        """
        s = re.sub(r'[\u064B-\u065F\u0670]', '', s)   # diacritiques
        s = re.sub(r'[إأآ]', 'ا', s)                   # normalisation alef
        return s

    def _fix_location_from_text(self, text: str, entities: dict) -> dict:
        """
        Post-traitement : si l'user mentionne explicitement une délégation/ville
        connue dans son texte, on corrige wilaya et delegation dans les entités,
        même si le modèle ML les a mal prédites.

        Priorité : texte brut > prédiction ML (le ML prédit souvent "تونس" par défaut).

        Stratégie en 2 passes :
          Passe 1 — Vraies délégations (clé ≠ valeur dans la map) : ex "قصر هلال"→"المنستير"
          Passe 2 — Capitales de wilaya (clé = valeur) : ex "المنستير"→"المنستير"
        Cette séparation garantit que "قصر هلال" est toujours reconnu en tant que
        délégation AVANT que "المنستير" (capitale de même longueur) ne soit testé.

        La normalisation arabe (diacritiques, alef) permet de matcher les
        transcriptions Whisper qui peuvent ajouter des voyelles.
        """
        if not text:
            return entities

        text_norm = self._normalize_ar(text)

        # Séparer en vraies délégations (clé ≠ valeur) et capitales de wilaya (clé = valeur)
        true_delegations = {k: v for k, v in DELEGATION_WILAYA_MAP.items() if k != v}
        wilaya_capitals  = {k: v for k, v in DELEGATION_WILAYA_MAP.items() if k == v}

        # Passe 1 : vraies délégations (le plus long d'abord pour "منزل بورقيبة" > "منزل")
        # Passe 2 : capitales de wilaya
        for mapping in (true_delegations, wilaya_capitals):
            for deleg in sorted(mapping.keys(), key=len, reverse=True):
                deleg_norm = self._normalize_ar(deleg)
                if deleg_norm in text_norm:
                    wilaya_found = mapping[deleg]
                    old_wilaya   = entities.get("wilaya", "")
                    old_deleg    = entities.get("delegation", "")

                    entities["delegation"]        = deleg
                    entities["wilaya"]            = wilaya_found
                    # Marqueur : localisation trouvée EXPLICITEMENT dans le texte
                    # → utilisé par _update_entities pour ne pas écraser
                    entities["location_explicit"] = True

                    if old_wilaya != wilaya_found or old_deleg != deleg:
                        logger.info(
                            f"[NLU] Location corrigée depuis texte : "
                            f"délégation='{old_deleg}'→'{deleg}' "
                            f"wilaya='{old_wilaya}'→'{wilaya_found}'"
                        )
                    return entities   # On s'arrête au premier match

        # Aucune localisation explicite dans le texte → on marque False
        # pour empêcher l'écrasement des valeurs accumulées correctes
        entities["location_explicit"] = False
        return entities

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _normalize(self, text: str) -> str:
        """Normalisation légère du darija.

        - Retire la ponctuation usuelle (arabe + latine).
        - Retire les diacritiques arabes (تشكيل) pour que شكراً ≡ شكرا.
        - Normalise les variantes de alef (إ أ آ → ا).
        - Normalise les ta marbouta finales (ة → ه) pour assouplir le matching.
        - Collapse les espaces, trim, lowercase.
        """
        text = re.sub(r'[؟!،,\.\?\!\:\;\|]', ' ', text)
        # Diacritiques arabes (fatha/damma/kasra/shadda/sukun/tanween/alef khanjariya)
        text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
        # Normalisation alef + ta marbouta
        text = re.sub(r'[إأآ]', 'ا', text)
        return re.sub(r'\s+', ' ', text).strip().lower()

    def _extract_phone(self, text: str) -> str:
        """Extrait un numéro de téléphone tunisien (8 chiffres)."""
        match = re.search(r'\b([259]\d{7})\b', re.sub(r'\s', '', text))
        return match.group(1) if match else None

    def _extract_transaction(self, text: str) -> str:
        """Extrait un identifiant de transaction."""
        match = re.search(r'\b([A-Z]{2,4}\d{6,12})\b', text.upper())
        return match.group(1) if match else None

    def _rule_sentiment(self, text_norm: str) -> str:
        """Sentiment par règles (fallback)."""
        neg = len(re.findall(r"مش|ما|ميش|غضبان|زعلان|خايب|نول|مزيان\sمش", text_norm))
        pos = len(re.findall(r"برابر|مزيان|شكرن|يعيشك|parfait|merci|excellent", text_norm))
        return "سلبي" if neg > pos else ("إيجابي" if pos > 0 else "محايد")

    def _rule_service(self, text_norm: str) -> str:
        """Détection du service par règles (fallback)."""
        if re.search(r"موبيل|mobile|gsm", text_norm):          return "Mobile"
        if re.search(r"adsl|فيكس|fixe", text_norm):             return "ADSL/Fixe"
        if re.search(r"fibre|فيبر", text_norm):                  return "Fibre Optique"
        if re.search(r"5g|4g|ريزو|réseau", text_norm):          return "5G/Réseau"
        if re.search(r"فاتورة|facture|billing", text_norm):     return "Billing"
        return ""

    def _empty_result(self, text: str) -> dict:
        """Résultat vide standard."""
        return {
            "intent": "غير محدد", "confidence": 0.0, "all_intents": [],
            "sentiment": "محايد", "entities": {},
            "action": "", "ml_response": "", "escalate": False,
            "decision": "reponse_automatique",
            "is_stop": False, "text": text, "ml_used": False,
        }
