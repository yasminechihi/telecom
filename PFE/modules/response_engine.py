# ============================================================
#  modules/response_engine.py — Moteur RAG (Retrieval-Augmented)
#  Dialogue naturel en 2 étapes, fidèle au dataset
#
#  Étape 1 : User décrit problème → Bot pose une QUESTION
#            (extraite du dataset, pas d'une map statique)
#  Étape 2 : User répond → Bot donne la RÉPONSE finale
#            (cherchée dans les conversations complètes)
#
#  Le dataset a ce format :
#    USER: salut | BOT: salut | USER: problème | BOT: question | USER: réponse
#    → response: réponse finale
# ============================================================

import os
import json
import pickle
import logging
import re
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseEngine:
    """
    Moteur de réponse RAG avec dialogue naturel en 2 étapes.

    Fonctionnement :
        1. Au démarrage : parse le dataset en conversations structurées,
           encode les messages utilisateur → index FAISS
        2. Étape 1 (find_clarification) : encode la plainte initiale
           → trouve les conversations similaires → retourne la QUESTION
           que le bot pose dans le dataset
        3. Étape 2 (find_response) : encode la conversation complète
           → trouve la meilleure réponse finale avec filtrage par intent
    """

    def __init__(self, config):
        self.config     = config
        self.model      = None
        self.index      = None          # Index FAISS principal
        self.records    = []            # Enregistrements parsés
        self.embeddings = None

        # Index séparé pour les premières plaintes (étape 1)
        self.problem_index      = None
        self.problem_embeddings = None

        self._load_embedding_model()
        self._build_or_load_index()

    # ─────────────────────────────────────────────────────────
    # Modèle d'embedding
    # ─────────────────────────────────────────────────────────
    def _load_embedding_model(self):
        try:
            import os
            from sentence_transformers import SentenceTransformer
            logger.info(f"Chargement modèle embedding: {self.config.EMBEDDING_MODEL}")
            # Essayer d'abord en mode offline (cache local) pour éviter
            # les erreurs de connexion à HuggingFace Hub
            try:
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_HUB_OFFLINE"] = "1"
                self.model = SentenceTransformer(self.config.EMBEDDING_MODEL)
                logger.info("Modèle embedding chargé depuis le cache local.")
            except Exception:
                # Fallback : tenter en mode connecté (premier lancement)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_HUB_OFFLINE", None)
                self.model = SentenceTransformer(self.config.EMBEDDING_MODEL)
                logger.info("Modèle embedding chargé depuis HuggingFace Hub.")
        except ImportError:
            # sentence-transformers absent → mode dégradé (TF-IDF uniquement)
            logger.warning(
                "sentence-transformers non installé — embedding désactivé. "
                "Le bot fonctionnera en mode TF-IDF (sans similarité sémantique)."
            )
            self.model = None
        except Exception as e:
            # DLL manquante, version PyTorch incompatible, etc.
            # NE PAS planter le serveur — continuer sans embedding.
            logger.warning(
                f"Embedding non disponible ({e}). "
                "Le bot fonctionnera en mode TF-IDF avec l'index FAISS existant."
            )
            self.model = None

    # ─────────────────────────────────────────────────────────
    # Construction de l'index FAISS
    # ─────────────────────────────────────────────────────────
    def _build_or_load_index(self):
        if (os.path.exists(self.config.FAISS_INDEX_PATH) and
                os.path.exists(self.config.DATASET_CACHE_PATH)):
            self._load_index()
        elif self.model is None:
            # Embedding non disponible ET pas d'index préconstruit
            # → continuer sans FAISS (mode dégradé TF-IDF uniquement)
            logger.warning(
                "Modèle embedding absent et aucun index FAISS en cache. "
                "Le bot fonctionne en mode TF-IDF pur (sans RAG sémantique)."
            )
            self.records    = self._load_dataset() or []
            self.index      = None
            self.embeddings = None
        else:
            logger.info("Index FAISS absent — construction depuis le dataset...")
            self._build_index()

    def _load_index(self):
        try:
            import faiss
            self.index = faiss.read_index(self.config.FAISS_INDEX_PATH)
            with open(self.config.DATASET_CACHE_PATH, "rb") as f:
                cache = pickle.load(f)
            self.records    = cache["records"]
            self.embeddings = cache["embeddings"]

            # Reconstruire l'index problème à partir du cache
            self._build_problem_index()

            logger.info(f"Index FAISS chargé — {self.index.ntotal} vecteurs.")
        except Exception as e:
            logger.warning(f"Erreur chargement index: {e}. Reconstruction...")
            self._build_index()

    def _build_index(self):
        import faiss

        # 1. Charger et parser le dataset
        self.records = self._load_dataset()
        if not self.records:
            raise ValueError(f"Dataset vide : {self.config.DATASET_PATH}")

        logger.info(f"Encodage de {len(self.records)} conversations...")

        # 2. Encoder les textes utilisateur pour l'index principal
        #    (problème + réponse clarification combinés)
        texts = []
        for rec in self.records:
            # Combiner issue_type + service_type + problème + réponse
            # Double ancrage (catégorie + service) → FAISS retrouve le bon voisin
            issue   = rec.get("issue_type", "")
            service = rec.get("service_type", "")
            problem = rec.get("user_problem", "")
            answer  = rec.get("user_answer", "")
            combined = f"{issue} {service} {problem} {answer}".strip()
            texts.append(combined if combined else rec.get("instruction", ""))

        # 3. Encodage par batchs
        batch_size = 64
        all_embs   = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            embs  = self.model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
            all_embs.append(embs)
            if i % 500 == 0:
                logger.info(f"  {i}/{len(texts)} encodés...")

        self.embeddings = np.vstack(all_embs).astype("float32")

        # 4. Index FAISS (cosine = Inner Product sur vecteurs normalisés)
        dim   = self.embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(self.embeddings)
        self.index = index

        # 5. Construire l'index séparé pour les problèmes (étape 1)
        self._build_problem_index()

        # 6. Sauvegarde
        os.makedirs(self.config.MODELS_DIR, exist_ok=True)
        faiss.write_index(self.index, self.config.FAISS_INDEX_PATH)
        with open(self.config.DATASET_CACHE_PATH, "wb") as f:
            pickle.dump({"records": self.records, "embeddings": self.embeddings}, f)

        logger.info(f"Index FAISS construit — {len(self.records)} vecteurs.")

    def _build_problem_index(self):
        """
        Construit un index FAISS séparé uniquement sur les
        premières plaintes utilisateur (pour l'étape 1 : clarification).
        On préfixe chaque texte avec l'issue_type pour que la recherche
        sémantique distingue mieux les catégories de problèmes.
        """
        import faiss

        problem_texts = []
        for rec in self.records:
            issue   = rec.get("issue_type", "")
            service = rec.get("service_type", "")
            problem = rec.get("user_problem", "")
            # Ancrage double : issue_type + service_type + texte
            text = f"{issue} {service} {problem}".strip() if (issue or service) else (problem or "")
            problem_texts.append(text)

        # Encoder les problèmes
        batch_size = 64
        all_embs = []
        for i in range(0, len(problem_texts), batch_size):
            batch = problem_texts[i: i + batch_size]
            embs = self.model.encode(batch, show_progress_bar=False, normalize_embeddings=True)
            all_embs.append(embs)

        self.problem_embeddings = np.vstack(all_embs).astype("float32")
        dim = self.problem_embeddings.shape[1]
        self.problem_index = faiss.IndexFlatIP(dim)
        self.problem_index.add(self.problem_embeddings)

        logger.info(f"Index problèmes (étape 1) construit — {self.problem_index.ntotal} vecteurs.")

    # ─────────────────────────────────────────────────────────
    # Chargement et PARSING du dataset
    # ─────────────────────────────────────────────────────────
    def _parse_record(self, rec: dict) -> dict | None:
        """Parse un enregistrement brut (JSONL ou Firebase) en record structuré."""
        if not rec.get("instruction") or not rec.get("response"):
            return None
        turns = self._parse_turns(rec["instruction"])
        rec["user_greeting"] = turns.get("user_1", "")
        rec["user_problem"]  = turns.get("user_2", "")
        rec["bot_question"]  = turns.get("bot_2", "")
        rec["user_answer"]   = turns.get("user_3", "")
        return rec

    def _load_dataset(self) -> list:
        """
        Charge le dataset et parse chaque conversation en tours structurés.

        Ordre de priorité :
          1. Firebase Firestore (collection dataset_nlp) — si USE_FIREBASE_DATASET=True
             et que la connexion est disponible.
          2. Fichier JSONL local (DATASET_PATH) — fallback automatique si Firebase
             est indisponible ou désactivé.
          Dans tous les cas, learned_interactions.jsonl est ajouté en complément.
        """
        records = []

        # ── Essai 1 : Firebase Firestore ──────────────────────────────────────
        _use_fb = getattr(self.config, "USE_FIREBASE_DATASET", True)
        if _use_fb:
            try:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from firebase_config import dataset_load_all
                raw_records = dataset_load_all()
                if raw_records:
                    for rec in raw_records:
                        parsed = self._parse_record(rec)
                        if parsed:
                            records.append(parsed)
                    logger.info(f"Dataset chargé depuis Firebase : {len(records)} conversations.")
            except Exception as _fb_err:
                logger.warning(
                    f"Firebase dataset indisponible ({_fb_err}) "
                    "→ fallback fichier JSONL local."
                )
                records = []   # reset pour que le fallback JSONL prenne le relais

        # ── Fallback (ou complément) : fichier JSONL local ────────────────────
        if not records:
            paths = [self.config.DATASET_PATH]
            for path in paths:
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec    = json.loads(line)
                            parsed = self._parse_record(rec)
                            if parsed:
                                records.append(parsed)
                        except json.JSONDecodeError:
                            continue
            if records:
                logger.info(f"Dataset chargé depuis JSONL local : {len(records)} conversations.")

        # ── Complément : learned_interactions.jsonl (toujours ajouté) ─────────
        if os.path.exists(self.config.LEARNED_DATA_PATH):
            extra = 0
            with open(self.config.LEARNED_DATA_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec    = json.loads(line)
                        parsed = self._parse_record(rec)
                        if parsed:
                            records.append(parsed)
                            extra += 1
                    except json.JSONDecodeError:
                        continue
            if extra:
                logger.info(f"  + {extra} interactions apprises ajoutées.")

        logger.info(f"Dataset total parsé : {len(records)} conversations.")
        return records

    def _parse_turns(self, instruction: str) -> dict:
        """
        Parse une instruction multi-tour en tours nommés.

        Format: USER: salut | BOT: salut | USER: problème | BOT: question | USER: réponse

        Returns:
            {
                "user_1": "salut",           # salutation
                "bot_1":  "مرحبا بيك...",    # salutation bot
                "user_2": "problème...",      # PROBLÈME PRINCIPAL
                "bot_2":  "question?",        # QUESTION DE CLARIFICATION
                "user_3": "réponse..."        # RÉPONSE À LA CLARIFICATION
            }
        """
        parts = instruction.split("|")
        result = {}
        user_count = 0
        bot_count  = 0

        for part in parts:
            part = part.strip()
            if part.upper().startswith("USER:"):
                user_count += 1
                result[f"user_{user_count}"] = part[5:].strip()
            elif part.upper().startswith("BOT:"):
                bot_count += 1
                result[f"bot_{bot_count}"] = part[4:].strip()

        return result

    # ═════════════════════════════════════════════════════════
    #  ÉTAPE 1 : Trouver la question de clarification
    # ═════════════════════════════════════════════════════════
    # Mapping service_type NLU → valeurs dataset
    _SERVICE_MAP = {
        "adsl":          "adsl/fixe",
        "adsl/fixe":     "adsl/fixe",
        "mobile":        "mobile",
        "mobil":         "mobile",
        "5g":            "5g/réseau",
        "5g/réseau":     "5g/réseau",
        "réseau":        "5g/réseau",
        "vdsl":          "vdsl",
        "fibre":         "fibre optique",
        "fibre optique": "fibre optique",
        "billing":       "billing",
        "administrative":"administrative",
        "admin":         "administrative",
    }

    def _normalize_service(self, service: str) -> str:
        if not service:
            return ""
        key = service.strip().lower()
        return self._SERVICE_MAP.get(key, key)

    def find_clarification_question(self, query: str, nlu_intent: str = None,
                                    nlu_service: str = None) -> dict:
        """
        Étape 1 du dialogue : le client décrit son problème,
        le bot pose une question de clarification.

        Cherche dans le dataset les conversations similaires
        et retourne la question que le bot pose DANS LE DATASET.

        Args:
            query:      Texte du client (problème)
            nlu_intent: Intent détecté par NLU

        Returns:
            {
                "question":   str,    # Question de clarification
                "confidence": float,  # Score de similarité
                "intent":     str,    # Issue type du record trouvé
            }
        """
        if not self.problem_index or not query.strip():
            return {"question": "", "confidence": 0.0, "intent": "", "matched_idx": -1}

        # ── GATE GLOBAL (sans préfixe intent) ─────────────────────────────────
        # On encode la requête BRUTE (sans intent) pour obtenir un score non-biaisé.
        # Si le meilleur score brut est trop bas → la requête est hors-dataset
        # → on ne pose aucune question de clarification (transfer en étape 2).
        #
        # Pourquoi c'est nécessaire :
        #   Avec le préfixe intent ("استفسار_عروض خطي مقصوص"), le score
        #   est artificiellement élevé si l'intent est faux (NLU 26% conf).
        #   La requête brute donne un score honnête de la pertinence réelle.
        raw_emb = self.model.encode(
            [query], normalize_embeddings=True
        ).astype("float32")
        raw_scores, _ = self.problem_index.search(raw_emb, 1)
        raw_best_score = float(raw_scores[0][0]) if raw_scores[0].size > 0 else 0.0

        RAW_MIN_SCORE = getattr(self.config, "CLARIFICATION_CONFIDENCE_THRESHOLD", 0.50)
        if raw_best_score < RAW_MIN_SCORE:
            logger.info(
                f"find_clarification GATE: hors dataset "
                f"(raw_best={raw_best_score:.3f} < seuil={RAW_MIN_SCORE}) → pas de question"
            )
            return {"question": "", "confidence": raw_best_score,
                    "intent": "", "matched_idx": -1}
        # ────────────────────────────────────────────────────────────────────────

        # Si l'intent NLU est disponible et fiable (non vide, non "غير محدد"),
        # on le préfixe dans la requête d'embedding.
        # L'index a été construit avec le même préfixe issue_type → meilleure cohérence.
        # NB : l'intent regex est beaucoup plus fiable que TF-IDF (13% conf).
        intent_prefix = ""
        if nlu_intent and nlu_intent not in ("غير محدد", "unknown", ""):
            intent_prefix = nlu_intent
        enriched_query = f"{intent_prefix} {query}".strip() if intent_prefix else query
        query_emb = self.model.encode(
            [enriched_query], normalize_embeddings=True
        ).astype("float32")

        K = 50
        scores, indices = self.problem_index.search(query_emb, K)

        intent_clean  = self._normalize_intent(nlu_intent or "")
        service_clean = self._normalize_service(nlu_service or "")

        # Trois niveaux de candidats :
        #  1. intent + service → meilleur match (catégorie + type de service)
        #  2. intent seul      → bon match (même catégorie, service inconnu)
        #  3. global           → fallback (tous sujets)
        best_both_q = ""; best_both_score = 0.0; best_both_iss = ""; best_both_idx = -1
        best_int_q  = ""; best_int_score  = 0.0; best_int_iss  = ""; best_int_idx  = -1
        best_any_q  = ""; best_any_score  = 0.0; best_any_iss  = ""; best_any_idx  = -1

        for score, idx in zip(scores[0], indices[0]):
            score = float(score)
            idx   = int(idx)
            if idx < 0 or idx >= len(self.records):
                continue

            rec       = self.records[idx]
            question  = rec.get("bot_question", "")
            rec_issue = self._normalize_intent(rec.get("issue_type", ""))
            rec_svc   = self._normalize_service(rec.get("service_type", ""))

            if not question:
                continue

            # Niveau 3 : global
            if score > best_any_score:
                best_any_score = score; best_any_q = question
                best_any_iss   = rec.get("issue_type", ""); best_any_idx = idx

            # Niveau 2 : intent match
            intent_match = (intent_clean and rec_issue and
                           (intent_clean in rec_issue or rec_issue in intent_clean))
            if intent_match and score > best_int_score:
                best_int_score = score; best_int_q = question
                best_int_iss   = rec.get("issue_type", ""); best_int_idx = idx

            # Niveau 1 : intent + service match
            service_match = (service_clean and rec_svc and
                            (service_clean in rec_svc or rec_svc in service_clean))
            if intent_match and service_match and score > best_both_score:
                best_both_score = score; best_both_q = question
                best_both_iss   = rec.get("issue_type", ""); best_both_idx = idx

        nlu_reliable = (nlu_intent and nlu_intent not in ("غير محدد","unknown",""))

        # Priorité 1 : intent + service → question très ciblée
        if nlu_reliable and best_both_q and best_both_score >= 0.12:
            logger.info(
                f"Clari INTENT+SVC '{nlu_intent}/{nlu_service}' "
                f"score={best_both_score:.3f} → '{best_both_q[:60]}'"
            )
            return {"question": best_both_q, "confidence": best_both_score,
                    "intent": best_both_iss, "matched_idx": best_both_idx}

        # Priorité 2 : intent seul → question dans la bonne catégorie
        if nlu_reliable and best_int_q and best_int_score >= 0.12:
            logger.info(
                f"Clari INTENT '{nlu_intent}' score={best_int_score:.3f} "
                f"→ '{best_int_q[:60]}'"
            )
            return {"question": best_int_q, "confidence": best_int_score,
                    "intent": best_int_iss, "matched_idx": best_int_idx}

        # Priorité 3 : global best
        if best_any_q and best_any_score >= 0.25:
            logger.info(
                f"Clari GLOBAL score={best_any_score:.3f} "
                f"intent='{best_any_iss}' → '{best_any_q[:60]}'"
            )
            return {"question": best_any_q, "confidence": best_any_score,
                    "intent": best_any_iss, "matched_idx": best_any_idx}

        return {"question": "", "confidence": 0.0, "intent": "", "matched_idx": -1}

    # ═════════════════════════════════════════════════════════
    #  ÉTAPE 2 : Trouver la réponse finale
    # ═════════════════════════════════════════════════════════
    def find_response(self, query: str, conversation_history: list = None,
                      nlu_intent: str = None) -> dict:
        """
        Étape 2 : après clarification, cherche la RÉPONSE finale.

        Stratégie STRICTE 2 passes :
          Pass 1 — Intent connu → cherche uniquement les records
                   dont l'issue_type correspond
          Pass 2 — Fallback → meilleur résultat sémantique global
        """
        if not query.strip():
            return self._build_result("", 0.0, escalate=False)

        enriched_query = self._enrich_query(query, conversation_history, nlu_intent)

        query_emb = self.model.encode(
            [enriched_query], normalize_embeddings=True
        ).astype("float32")

        K_search = max(40, self.config.RAG_TOP_K * 8)
        scores, indices = self.index.search(query_emb, K_search)

        intent_clean = self._normalize_intent(nlu_intent or "")
        intent_known = bool(intent_clean) and intent_clean not in (
            self._normalize_intent("غير محدد"),
            self._normalize_intent("unknown"),
        )

        # Localisation mentionnée par l'user (pour bonus de score)
        user_location = self._extract_location(enriched_query)

        # Collecter les candidats
        best_intent_record = None
        best_intent_score  = 0.0
        best_any_record    = None
        best_any_score     = 0.0

        for score, idx in zip(scores[0], indices[0]):
            score = float(score)
            idx   = int(idx)
            if idx < 0 or idx >= len(self.records):
                continue

            rec       = self.records[idx]
            rec_issue = self._normalize_intent(rec.get("issue_type", ""))

            # Bonus si le record mentionne la même localisation que l'user
            if user_location:
                rec_text = (rec.get("response", "") + " " +
                            rec.get("user_problem", "") + " " +
                            rec.get("user_answer", ""))
                if user_location in rec_text:
                    score = min(score + 0.18, 1.0)
                    logger.debug(f"Location bonus +0.18 pour '{user_location}' idx={idx}")

            if score > best_any_score:
                best_any_score  = score
                best_any_record = rec

            if intent_known and rec_issue:
                if intent_clean in rec_issue or rec_issue in intent_clean:
                    if score > best_intent_score:
                        best_intent_score  = score
                        best_intent_record = rec

        # PASS 1 : Résultat filtré par intent
        INTENT_MIN_SCORE = 0.25
        if intent_known and best_intent_record and best_intent_score >= INTENT_MIN_SCORE:
            logger.info(
                f"RAG PASS1 → intent='{nlu_intent}' "
                f"score={best_intent_score:.3f} (global={best_any_score:.3f} ignoré)"
            )
            final_record = best_intent_record
            final_score  = best_intent_score
        elif best_any_record:
            logger.info(f"RAG PASS2 → score global={best_any_score:.3f}")
            final_record = best_any_record
            final_score  = best_any_score
        else:
            return self._build_result("", 0.0, escalate=True)

        # Seuil de confiance
        threshold = (0.30 if (intent_known and final_record == best_intent_record)
                     else self.config.RAG_CONFIDENCE_THRESHOLD)

        if final_score < threshold:
            return self._build_result("", final_score, escalate=True)

        response = final_record.get("response", "")
        # Supprimer les emojis de la réponse
        response = self._strip_emojis(response)
        # Passer la query enrichie (contient le problème original + réponse clarification)
        # pour que _personalize ait accès à toutes les localisations mentionnées
        response = self._personalize(response, enriched_query)

        return self._build_result(
            response=response, confidence=final_score,
            record=final_record, escalate=False
        )

    # ─────────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────────
    def _strip_emojis(self, text: str) -> str:
        """Supprime tous les emojis et symboles non-textuels de la réponse."""
        import re
        # Supprimer les emojis (plages Unicode emoji)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"   # emoticons
            "\U0001F300-\U0001F5FF"   # symboles & pictogrammes
            "\U0001F680-\U0001F6FF"   # transport & cartes
            "\U0001F1E0-\U0001F1FF"   # drapeaux
            "\U00002500-\U00002BEF"   # divers symboles
            "\U00002702-\U000027B0"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001f926-\U0001f937"
            "\U00010000-\U0010ffff"
            "\u2640-\u2642"
            "\u2600-\u2B55"
            "\u200d"
            "\u23cf"
            "\u23e9"
            "\u231a"
            "\ufe0f"
            "\u3030"
            "]+",
            flags=re.UNICODE,
        )
        text = emoji_pattern.sub("", text)
        # Nettoyer les espaces multiples laissés par la suppression
        text = re.sub(r"  +", " ", text).strip()
        return text

    def _normalize_intent(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', '', text.strip())
        text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        text = text.replace('ة', 'ه')
        return text.lower()

    def _enrich_query(self, query: str, history: list, nlu_intent: str = None,
                      nlu_service: str = None) -> str:
        """
        Construit la requête RAG étape 2.

        On combine les 2-3 derniers tours utilisateur pour avoir un contexte
        riche (problème original + réponse à la clarification).
        Si l'intent NLU est disponible et non ambigu, on le préfixe dans
        la requête pour ancrer la recherche dans la bonne catégorie.
        """
        if not history:
            context = query
        else:
            user_turns = [t for r, t in history if r == "user"]
            context = " ".join(user_turns[-3:]).strip()
            if not context:
                context = query

        # Préfixe intent + service pour cohérence avec l'index enrichi
        prefix = ""
        if nlu_intent and nlu_intent not in ("غير محدد", "unknown", ""):
            prefix = nlu_intent
        svc_norm = self._normalize_service(nlu_service or "")
        if svc_norm:
            prefix = f"{prefix} {svc_norm}".strip()
        if prefix:
            context = f"{prefix} {context}"

        return context

    def _extract_location(self, text: str) -> str:
        """
        Extrait la première localisation tunisienne mentionnée dans le texte.
        Recherche les clés par longueur décroissante pour éviter les faux positifs
        (ex: "القصرين" avant "قصرين").
        """
        if not text or not hasattr(self.config, "TUNISIAN_LOCATIONS"):
            return ""
        locations = self.config.TUNISIAN_LOCATIONS
        # Trier par longueur décroissante pour matcher les noms longs d'abord
        for loc in sorted(locations.keys(), key=len, reverse=True):
            if loc in text:
                return locations[loc]   # retourne la forme canonique
        return ""

    def _personalize(self, response: str, query: str) -> str:
        """
        Post-traitement de la réponse RAG :
        Si le dataset a retourné une réponse qui mentionne une localisation
        différente de celle de l'utilisateur, on substitue.

        Exemple : user dit "بوحجلة", dataset répond avec "القصرين"
        → remplace "القصرين" par "بوحجلة" dans la réponse.
        """
        if not response or not query:
            return response

        user_location = self._extract_location(query)
        if not user_location:
            return response   # pas de localisation dans la query → rien à faire

        resp_location = self._extract_location(response)
        if not resp_location:
            return response   # pas de localisation dans la réponse → rien à remplacer

        if user_location == resp_location:
            return response   # même localisation → OK, rien à changer

        # Localisation différente → substituer
        logger.info(
            f"[Personalize] Substitution localisation : "
            f"'{resp_location}' → '{user_location}' dans la réponse"
        )
        # Remplacer toutes les occurrences (la clé ET sa forme dans la réponse)
        updated = response
        # Remplacer la forme canonique trouvée
        updated = updated.replace(resp_location, user_location)
        # Remplacer aussi les formes alternatives (ex: "قصرين" pour "القصرين")
        if hasattr(self.config, "TUNISIAN_LOCATIONS"):
            for key, canon in self.config.TUNISIAN_LOCATIONS.items():
                if canon == resp_location and key != resp_location and key in updated:
                    updated = updated.replace(key, user_location)
        return updated

    def _build_result(self, response, confidence, record=None, escalate=False) -> dict:
        if record:
            return {
                "response":     response,
                "confidence":   confidence,
                "issue_type":   record.get("issue_type", ""),
                "service_type": record.get("service_type", ""),
                "action":       record.get("suggested_action", ""),
                "escalate":     escalate,
            }
        return {
            "response": response, "confidence": confidence,
            "issue_type": "", "service_type": "", "action": "", "escalate": escalate,
        }

    # ─────────────────────────────────────────────────────────
    # Rechargement
    # ─────────────────────────────────────────────────────────
    def reload_index(self):
        logger.info("Rechargement de l'index RAG...")
        if os.path.exists(self.config.FAISS_INDEX_PATH):
            os.remove(self.config.FAISS_INDEX_PATH)
        if os.path.exists(self.config.DATASET_CACHE_PATH):
            os.remove(self.config.DATASET_CACHE_PATH)
        self._build_index()
        logger.info("Index RAG rechargé.")
