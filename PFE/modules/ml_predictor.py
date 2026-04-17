# ============================================================
#  modules/ml_predictor.py — Prédicteur ML
#  Supporte 2 backends :
#    1. Fine-tuned AraBERT (HuggingFace) — PRIORITAIRE
#    2. TF-IDF + LogReg (ML.ipynb)       — FALLBACK
#
#  Le fine-tuned model donne 90%+ accuracy vs 9% pour TF-IDF
#  sur du texte darija mixte latin/arabe.
# ============================================================

import os
import re
import json
import logging

logger = logging.getLogger(__name__)


class MLPredictor:
    """
    Interface unifiée vers les modèles ML.

    Priorité de chargement :
      1. models/finetuned_intent/  (AraBERT fine-tuné)
      2. models/*.pkl              (TF-IDF + LogReg de ML.ipynb)

    generate_ai_output(text) retourne le même format
    quel que soit le backend utilisé.
    """

    def __init__(self, config):
        self.config         = config
        self._loaded        = False
        self._backend       = None    # "finetuned" | "tfidf"
        self._models        = {}      # Pour TF-IDF
        self._ft_model      = None    # Pour fine-tuned
        self._ft_tokenizer  = None
        self._ft_label_map  = None
        self._ft_device     = "cpu"

        # Essayer le fine-tuned d'abord, puis TF-IDF
        if self._load_finetuned():
            self._backend = "finetuned"
            self._loaded  = True
        elif self._load_tfidf():
            self._backend = "tfidf"
            self._loaded  = True
        else:
            logger.warning("⚠️  Aucun modèle ML disponible (ni fine-tuned, ni TF-IDF)")

    # ═════════════════════════════════════════════════════════
    #  CHARGEMENT — Fine-tuned AraBERT
    # ═════════════════════════════════════════════════════════
    def _load_finetuned(self) -> bool:
        """Charge le modèle fine-tuné depuis models/finetuned_intent/"""
        ft_dir = os.path.join(self.config.MODELS_DIR, "finetuned_intent")
        label_map_path = os.path.join(ft_dir, "label_map.json")

        if not os.path.exists(ft_dir) or not os.path.exists(label_map_path):
            return False

        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            logger.info(f"Chargement modèle fine-tuné depuis {ft_dir}...")

            self._ft_tokenizer = AutoTokenizer.from_pretrained(ft_dir)
            self._ft_model     = AutoModelForSequenceClassification.from_pretrained(ft_dir)
            self._ft_device    = "cuda" if torch.cuda.is_available() else "cpu"
            self._ft_model.to(self._ft_device)
            self._ft_model.eval()

            with open(label_map_path, "r", encoding="utf-8") as f:
                maps = json.load(f)
            self._ft_label_map = {int(k): v for k, v in maps["id2label"].items()}

            # Charger les métriques si disponibles
            metrics_path = os.path.join(ft_dir, "metrics.json")
            if os.path.exists(metrics_path):
                with open(metrics_path, "r", encoding="utf-8") as f:
                    metrics = json.load(f)
                logger.info(
                    f"✅ Modèle fine-tuné chargé — "
                    f"Accuracy: {metrics.get('accuracy', 0):.2%} | "
                    f"F1: {metrics.get('f1_score', 0):.2%} | "
                    f"Modèle: {metrics.get('model_name', '?')}"
                )
            else:
                logger.info("✅ Modèle fine-tuné chargé")

            return True

        except ImportError:
            logger.info("transformers/torch non installés → skip fine-tuned model")
            return False
        except Exception as e:
            logger.warning(f"Erreur chargement fine-tuned: {e}")
            return False

    def _predict_finetuned(self, text: str) -> tuple:
        """
        Prédit l'intent avec le modèle fine-tuné.
        Returns: (intent: str, confidence: float)
        """
        import torch

        inputs = self._ft_tokenizer(
            text, return_tensors="pt", truncation=True,
            max_length=128, padding=True
        ).to(self._ft_device)

        with torch.no_grad():
            outputs = self._ft_model(**inputs)
            probs   = torch.softmax(outputs.logits, dim=-1)
            conf, pred_id = probs.max(dim=-1)

        intent     = self._ft_label_map.get(pred_id.item(), "غير محدد")
        confidence = conf.item()
        return (intent, confidence)

    # ═════════════════════════════════════════════════════════
    #  CHARGEMENT — TF-IDF + LogReg (ML.ipynb)
    # ═════════════════════════════════════════════════════════
    def _load_tfidf(self) -> bool:
        """Charge les modèles TF-IDF + LogReg depuis models/*.pkl"""
        try:
            import joblib
        except ImportError:
            logger.warning("joblib non installé → skip TF-IDF models")
            return False

        models_dir = self.config.MODELS_DIR
        required_files = {
            "tfidf_issue":       "tfidf_issue.pkl",
            "model_issue":       "model_issue.pkl",
            "tfidf_sentiment":   "tfidf_sentiment.pkl",
            "model_sentiment":   "model_sentiment.pkl",
            "tfidf_service":     "tfidf_service.pkl",
            "model_service":     "model_service.pkl",
            "tfidf_geo":         "tfidf_geo.pkl",
            "model_wilaya":      "model_wilaya.pkl",
            "model_delegation":  "model_delegation.pkl",
            "tfidf_action":      "tfidf_action.pkl",
            "model_action":      "model_action.pkl",
            "model_response":    "model_response.pkl",
        }

        missing = []
        for key, filename in required_files.items():
            filepath = os.path.join(models_dir, filename)
            if os.path.exists(filepath):
                self._models[key] = joblib.load(filepath)
            else:
                missing.append(filename)

        if missing:
            logger.warning(f"⚠️  Modèles TF-IDF manquants: {missing}")
            return False

        logger.info(f"✅ Modèles TF-IDF chargés depuis '{models_dir}'")
        return True

    # ═════════════════════════════════════════════════════════
    #  PROPRIÉTÉS
    # ═════════════════════════════════════════════════════════
    @property
    def is_available(self) -> bool:
        return self._loaded

    @property
    def backend_name(self) -> str:
        if self._backend == "finetuned":
            return "AraBERT Fine-tuné"
        elif self._backend == "tfidf":
            return "TF-IDF + LogReg"
        return "Aucun"

    # ═════════════════════════════════════════════════════════
    #  NORMALISATION
    # ═════════════════════════════════════════════════════════
    def _normalize(self, text: str) -> str:
        text = str(text).lower()
        text = re.sub(r"http\S+|www\S+", "", text)
        text = re.sub(r"@\w+", "", text)
        text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ═════════════════════════════════════════════════════════
    #  PRÉDICTIONS — Interface unifiée
    # ═════════════════════════════════════════════════════════
    def predict_issue(self, text: str) -> tuple:
        """Prédit le type de réclamation. Returns: (issue_type, confidence)"""
        if self._backend == "finetuned":
            return self._predict_finetuned(text)
        if self._backend == "tfidf":
            text_clean = self._normalize(text)
            vect  = self._models["tfidf_issue"].transform([text_clean])
            issue = self._models["model_issue"].predict(vect)[0]
            proba = self._models["model_issue"].predict_proba(vect).max()
            return (issue, float(proba))
        return ("غير محدد", 0.0)

    def predict_sentiment(self, text: str) -> tuple:
        if self._backend == "tfidf" and "tfidf_sentiment" in self._models:
            text_clean = self._normalize(text)
            vect = self._models["tfidf_sentiment"].transform([text_clean])
            return (self._models["model_sentiment"].predict(vect)[0],
                    float(self._models["model_sentiment"].predict_proba(vect).max()))
        # Fine-tuned: sentiment par règles (le modèle ne prédit que l'intent)
        return self._rule_sentiment(text)

    def predict_service(self, text: str) -> tuple:
        if self._backend == "tfidf" and "tfidf_service" in self._models:
            text_clean = self._normalize(text)
            if "انترنت" in text_clean or "internet" in text_clean:
                return ("Internet", 1.0)
            vect = self._models["tfidf_service"].transform([text_clean])
            return (self._models["model_service"].predict(vect)[0],
                    float(self._models["model_service"].predict_proba(vect).max()))
        return self._rule_service(text)

    def predict_wilaya(self, text: str) -> str:
        if self._backend == "tfidf" and "tfidf_geo" in self._models:
            vect = self._models["tfidf_geo"].transform([self._normalize(text)])
            return self._models["model_wilaya"].predict(vect)[0]
        return self._extract_wilaya(text)

    def predict_delegation(self, text: str) -> str:
        if self._backend == "tfidf" and "tfidf_geo" in self._models:
            vect = self._models["tfidf_geo"].transform([self._normalize(text)])
            return self._models["model_delegation"].predict(vect)[0]
        return ""

    def predict_action(self, issue: str, sentiment: str, service: str) -> str:
        if self._backend == "tfidf" and "tfidf_action" in self._models:
            context = f"{issue} | {sentiment} | {service}"
            vect = self._models["tfidf_action"].transform([context])
            return self._models["model_action"].predict(vect)[0]
        return ""

    def predict_response_ml(self, issue: str, sentiment: str, service: str) -> str:
        if self._backend == "tfidf" and "model_response" in self._models:
            context = f"{issue} | {sentiment} | {service}"
            vect = self._models["tfidf_action"].transform([context])
            return self._models["model_response"].predict(vect)[0]
        return ""

    # ═════════════════════════════════════════════════════════
    #  GENERATE_AI_OUTPUT — Sortie unifiée (identique cell 69)
    # ═════════════════════════════════════════════════════════
    def generate_ai_output(self, text: str) -> dict:
        """
        Point d'entrée principal — même format de sortie
        que le modèle fine-tuné ou TF-IDF soit utilisé.
        """
        if not self._loaded:
            return self._empty_output()

        issue_type, issue_conf       = self.predict_issue(text)
        sentiment, _                 = self.predict_sentiment(text)
        service_type, _              = self.predict_service(text)
        wilaya                       = self.predict_wilaya(text)
        delegation                   = self.predict_delegation(text)
        recommended_action           = self.predict_action(issue_type, sentiment, service_type)
        ml_response                  = self.predict_response_ml(issue_type, sentiment, service_type)

        # Moteur de décision (cell 59)
        CRITICAL = ["عطل في الشبكه", "انقطاع الانترنت",
                     "مشكله في الدفع", "اعتراض على الفاتوره"]

        if sentiment == "سلبي" and issue_type in CRITICAL:
            decision = "escalade_agent_humain"
        elif not recommended_action or not recommended_action.strip():
            decision = "escalade_agent_humain"
        else:
            decision = "reponse_automatique"

        return {
            "issue_type":          issue_type,
            "issue_confidence":    round(issue_conf, 3),
            "service_type":        service_type,
            "sentiment":           sentiment,
            "wilaya":              wilaya,
            "delegation":          delegation,
            "recommended_action":  recommended_action,
            "ml_response":         ml_response,
            "decision":            decision,
            "ml_available":        True,
            "backend":             self._backend,
        }

    def _empty_output(self) -> dict:
        return {
            "issue_type": "غير محدد", "issue_confidence": 0.0,
            "service_type": "غير محدد", "sentiment": "محايد",
            "wilaya": "", "delegation": "",
            "recommended_action": "", "ml_response": "",
            "decision": "escalade_agent_humain",
            "ml_available": False, "backend": None,
        }

    # ═════════════════════════════════════════════════════════
    #  RÈGLES FALLBACK (pour fine-tuned qui ne prédit que l'intent)
    # ═════════════════════════════════════════════════════════
    def _rule_sentiment(self, text: str) -> tuple:
        t = self._normalize(text)
        neg = len(re.findall(r"مش|ما|ميش|غضبان|زعلان|خايب|مشكل|عطل|قطع|بطي", t))
        pos = len(re.findall(r"برابر|مزيان|شكرن|يعيشك|merci|parfait|بالباهي", t))
        if neg > pos:
            return ("سلبي", 0.7)
        elif pos > 0:
            return ("إيجابي", 0.6)
        return ("محايد", 0.5)

    def _rule_service(self, text: str) -> tuple:
        t = self._normalize(text)
        if re.search(r"موبيل|mobile|gsm", t):      return ("Mobile", 0.8)
        if re.search(r"adsl|فيكس|fixe|موديم", t):   return ("ADSL/Fixe", 0.8)
        if re.search(r"fibre|فيبر", t):              return ("Fibre Optique", 0.8)
        if re.search(r"5g|4g|ريزو|réseau|شبكة", t):  return ("5G/Réseau", 0.8)
        if re.search(r"فاتورة|facture", t):           return ("Administrative", 0.7)
        if re.search(r"wifi|وايفي|ويفي|راوتر|routeur", t): return ("ADSL/Fixe", 0.7)
        return ("", 0.0)

    def _extract_wilaya(self, text: str) -> str:
        """Extraction basique de la wilaya par mentions directes."""
        WILAYAS = [
            "تونس", "أريانة", "اريانة", "بن عروس", "منوبة",
            "نابل", "زغوان", "بنزرت", "باجة", "جندوبة",
            "الكاف", "سليانة", "القيروان", "القصرين", "سيدي بوزيد",
            "سوسة", "المنستير", "المهدية", "صفاقس", "قفصة",
            "توزر", "قبلي", "تطاوين", "مدنين", "قابس",
        ]
        for w in WILAYAS:
            if w in text:
                return w
        return ""

    # ═════════════════════════════════════════════════════════
    #  RECHARGEMENT
    # ═════════════════════════════════════════════════════════
    def reload(self):
        """Recharge les modèles depuis le disque."""
        logger.info("Rechargement des modèles ML...")
        self._models.clear()
        self._ft_model = None
        self._ft_tokenizer = None
        self._loaded = False
        self._backend = None

        if self._load_finetuned():
            self._backend = "finetuned"
            self._loaded = True
        elif self._load_tfidf():
            self._backend = "tfidf"
            self._loaded = True
