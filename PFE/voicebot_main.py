#!/usr/bin/env python3
# ============================================================
#  voicebot_main.py — Point d'entrée principal du VoiceBot
#  Tunisie Telecom — Centre d'appel virtuel (Darija tunisien)
# ============================================================
#
#  Usage :
#      python voicebot_main.py                  # Mode vocal interactif
#      python voicebot_main.py --text           # Mode texte (debug)
#      python voicebot_main.py --build-index    # (Re)construire l'index RAG
#      python voicebot_main.py --stats          # Statistiques d'apprentissage
#
# ============================================================

import os
import sys
import logging
import argparse
import colorlog

# ── Ajouter le répertoire parent au path ─────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as Config
from modules.stt             import STTModule
from modules.tts             import TTSModule
from modules.nlu             import NLUModule
from modules.ml_predictor    import MLPredictor
from modules.response_engine import ResponseEngine
from modules.dialog_manager  import DialogManager
from modules.human_transfer  import HumanTransfer
from modules.learning        import LearningModule


# ─────────────────────────────────────────────────────────────
# Configuration du logging
# ─────────────────────────────────────────────────────────────
def setup_logging(level: str = "INFO"):
    """Configure le logging coloré pour la console."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s%(reset)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "cyan",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    ))

    # Logger fichier
    os.makedirs(Config.LOGS_DIR, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(Config.LOGS_DIR, "voicebot.log"),
        encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(handler)
    root.addHandler(file_handler)

    # Silencer les loggers tiers trop verbeux
    for logger_name in ["sentence_transformers", "transformers", "faiss"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Initialisation de tous les modules
# ─────────────────────────────────────────────────────────────
def initialize_modules():
    """
    Charge et initialise tous les modules dans l'ordre.
    Retourne le DialogManager prêt à l'emploi.
    """
    logger.info("=" * 55)
    logger.info("  VoiceBot Tunisie Telecom — Initialisation")
    logger.info("=" * 55)

    # Créer les répertoires nécessaires
    for d in [Config.MODELS_DIR, Config.LOGS_DIR, Config.DATA_DIR]:
        os.makedirs(d, exist_ok=True)

    # 1. Module d'apprentissage (pas de dépendances)
    logger.info("[1/7] Module d'apprentissage...")
    learning = LearningModule(Config)

    # 2. Module TTS (lecture des messages système)
    logger.info("[2/7] Module TTS (Text-to-Speech)...")
    tts = TTSModule(Config)

    # 3. Module STT (Whisper) — le plus long à charger
    logger.info("[3/7] Module STT (Whisper)...")
    stt = STTModule(Config)

    # 4. Module NLU : MLPredictor (ML.ipynb) + règles regex
    logger.info("[4/6] Module NLU + MLPredictor (modèles ML.ipynb)...")
    ml_predictor = MLPredictor(Config)
    nlu = NLUModule(Config, ml_predictor=ml_predictor)

    if ml_predictor.is_available:
        logger.info("  ✅ Modèles ML.ipynb actifs (TF-IDF + LogisticRegression)")
    else:
        logger.warning("  ⚠️  Modèles ML.ipynb absents — fallback règles regex")
        logger.warning("  → Exécute la dernière cellule de ML.ipynb pour les générer.")

    # 5. Moteur RAG (embeddings + FAISS)
    logger.info("[5/7] Moteur RAG (construction index si besoin)...")
    engine = ResponseEngine(Config)

    # 6. Module de transfert humain
    logger.info("[6/7] Module transfert humain...")
    transfer = HumanTransfer(Config)

    # Assemblage du DialogManager
    dm = DialogManager(
        config   = Config,
        stt      = stt,
        tts      = tts,
        nlu      = nlu,
        engine   = engine,
        transfer = transfer,
        learning = learning,
    )

    logger.info("=" * 55)
    logger.info("  Initialisation terminée — VoiceBot prêt !")
    logger.info("=" * 55)
    return dm


# ─────────────────────────────────────────────────────────────
# Mode texte (debug sans micro)
# ─────────────────────────────────────────────────────────────
def run_text_mode():
    """
    Mode debug : remplace le micro par la saisie clavier.
    Utile pour tester sans micro ou en développement.
    """
    logger.info("Mode TEXTE activé (debug)")

    # Initialiser sans STT réel
    learning = LearningModule(Config)
    tts      = TTSModule(Config)
    nlu      = NLUModule(Config)
    engine   = ResponseEngine(Config)
    transfer = HumanTransfer(Config)

    print("\n" + "="*55)
    print("  VoiceBot Tunisie Telecom — MODE TEXTE")
    print("  Tape 'quit' pour terminer")
    print("="*55 + "\n")

    greeting = Config.GREETING_MESSAGE
    print(f"\n🤖 BOT: {greeting}\n")

    history = []
    turn    = 0

    while turn < Config.MAX_TURNS:
        try:
            user_input = input("🧑 Client: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "quitter"):
            print(f"\n🤖 BOT: {Config.FAREWELL_MESSAGE}\n")
            break

        turn += 1
        history.append(("user", user_input))

        # Analyse NLU
        nlu_result = nlu.analyze(user_input)

        if nlu_result.get("is_stop"):
            print(f"\n🤖 BOT: {Config.FAREWELL_MESSAGE}\n")
            break

        # Recherche RAG
        print("   [Recherche en cours...]")
        rag_result = engine.find_response(user_input, history)

        if rag_result["escalate"]:
            print(f"\n🤖 BOT: {Config.TRANSFER_MESSAGE}")
            print(f"   [Transfert — confiance RAG: {rag_result['confidence']:.2f}]")
            # Simuler réponse humaine en mode texte
            try:
                human_resp = input("👤 Agent humain (réponse): ").strip()
            except (EOFError, KeyboardInterrupt):
                human_resp = ""

            if human_resp:
                learning.learn_from_human(
                    user_text=user_input,
                    human_response=human_resp,
                    issue_type=nlu_result.get("intent", ""),
                )
                print(f"\n✅ Réponse apprise et sauvegardée.")
                if learning.should_retrain():
                    print("🔄 Seuil atteint — rechargement de l'index RAG...")
                    engine.reload_index()
                    learning.reset_counter()
            break

        response = rag_result.get("response") or Config.NOT_UNDERSTOOD_MSG
        history.append(("bot", response))

        print(f"\n🤖 BOT: {response}")
        print(f"   [intent: {nlu_result.get('intent')} | "
              f"score: {rag_result.get('confidence', 0):.2f} | "
              f"service: {rag_result.get('service_type', '')}]\n")

    stats = learning.get_stats()
    print(f"\n{'='*55}")
    print(f"  Session terminée | Appris: {stats['total_learned']} interactions")
    print(f"{'='*55}\n")


# ─────────────────────────────────────────────────────────────
# CLI Arguments
# ─────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="VoiceBot Tunisie Telecom — Darija tunisien"
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Mode texte (debug, pas de micro requis)"
    )
    parser.add_argument(
        "--build-index", action="store_true",
        help="(Re)construire l'index FAISS depuis le dataset"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Afficher les statistiques d'apprentissage"
    )
    parser.add_argument(
        "--log-level", default=Config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Niveau de log (défaut: INFO)"
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────────────────────
def main():
    args = parse_args()
    setup_logging(args.log_level)

    # ── Statistiques ──────────────────────────────────────────
    if args.stats:
        learning = LearningModule(Config)
        stats    = learning.get_stats()
        print("\n📊 Statistiques d'apprentissage VoiceBot:")
        print(f"   Total interactions apprises : {stats['total_learned']}")
        print(f"   Depuis dernier retrain       : {stats['since_last_retrain']}")
        print(f"   Seuil de réentraînement      : {stats['retrain_threshold']}")
        print(f"   Prochain retrain dans        : {stats['next_retrain_in']} interactions\n")
        return

    # ── (Re)construire l'index ────────────────────────────────
    if args.build_index:
        logger.info("Construction forcée de l'index RAG...")
        engine = ResponseEngine(Config)
        engine.reload_index()
        logger.info("Index construit avec succès.")
        return

    # ── Mode texte (debug) ────────────────────────────────────
    if args.text:
        run_text_mode()
        return

    # ── Mode vocal (production) ───────────────────────────────
    dm = initialize_modules()
    dm.run()


if __name__ == "__main__":
    main()
