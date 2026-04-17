#!/usr/bin/env python3
# ============================================================
#  app_launcher.py  —  Lanceur robuste VoiceBot Tunisie Telecom
# ============================================================

import sys, os, warnings, traceback, threading, time, subprocess

# ── 0. Répertoire de travail ──────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

# ── Log fichier + console ─────────────────────────────────────
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(HERE, "launcher.log"), encoding="utf-8", mode="w"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("launcher")
log.info("=" * 55)
log.info("  VoiceBot Tunisie Telecom — Lanceur")
log.info(f"  Python  : {sys.version}")
log.info(f"  Dossier : {HERE}")
log.info("=" * 55)

# ── Patch 1 : LRScheduler ────────────────────────────────────
log.info("[Patch 1] LRScheduler torch...")
try:
    import torch.optim.lr_scheduler as _lrs
    if not hasattr(_lrs, "LRScheduler"):
        _lrs.LRScheduler = _lrs._LRScheduler
        log.info("  ✓ Alias LRScheduler créé.")
    else:
        log.info("  ✓ OK.")
except ImportError:
    log.warning("  torch non disponible.")

# ── Patch 2 : Warnings ───────────────────────────────────────
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*InconsistentVersionWarning.*")
warnings.filterwarnings("ignore", message=".*Trying to unpickle estimator.*")
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TOKENIZERS_PARALLELISM"]  = "false"

# ── Patch 3 : Installation + activation Whisper STT ──────────
log.info("[Patch 3] Vérification faster-whisper...")

_fw_ok = False
try:
    import faster_whisper
    _fw_ok = True
    log.info(f"  ✓ faster-whisper {faster_whisper.__version__} présent.")
except ImportError:
    log.info("  faster-whisper absent — installation automatique...")
    try:
        _r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "faster-whisper", "-q"],
            capture_output=True, text=True, timeout=300
        )
        if _r.returncode == 0:
            import faster_whisper
            _fw_ok = True
            log.info("  ✓ faster-whisper installé.")
        else:
            log.warning(f"  Échec installation : {_r.stderr[:200]}")
    except Exception as _e:
        log.warning(f"  Impossible d'installer faster-whisper : {_e}")

if _fw_ok:
    log.info("  ✓ STT vocal activé — modèle Whisper medium (1.5 Go)")
    log.info("    sera téléchargé au démarrage si absent (10-30 min).")
    os.environ.pop("HF_HUB_OFFLINE",      None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
else:
    log.warning("  ⚠ faster-whisper indisponible → STT désactivé (texte uniquement).")
    os.environ["HF_HUB_OFFLINE"]      = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

# ── Patch 4 CRITIQUE : scikit-learn version mismatch ─────────
# Les .pkl ont été créés avec sklearn 1.7.2 mais whisper_env
# a 1.3.2 → NotFittedError au moment d'utiliser les modèles.
# Solution : mettre à jour sklearn OU activer le fallback regex.
log.info("[Patch 4] Vérification scikit-learn...")

import sklearn as _sk
_sk_version = tuple(int(x) for x in _sk.__version__.split(".")[:2])
log.info(f"  scikit-learn actuel : {_sk.__version__}")

_sklearn_ok = _sk_version >= (1, 7)

if not _sklearn_ok:
    log.info("  sklearn < 1.7 détecté — tentative de mise à jour automatique...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "scikit-learn>=1.7.0", "--upgrade", "-q"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode == 0:
            # Recharger le module pour avoir la nouvelle version
            import importlib
            import sklearn
            importlib.reload(sklearn)
            import sklearn.feature_extraction.text
            importlib.reload(sklearn.feature_extraction.text)
            log.info(f"  ✓ sklearn mis à jour — redémarrage requis pour appliquer.")
            log.info("  → Relancez DEMARRER.cmd pour utiliser sklearn 1.7+")
            # Écrire un flag pour indiquer qu'on vient de mettre à jour
            with open(os.path.join(HERE, ".sklearn_updated"), "w") as f:
                f.write("updated")
            _sklearn_ok = True
        else:
            log.warning(f"  Mise à jour sklearn échouée : {result.stderr[:200]}")
    except Exception as e:
        log.warning(f"  Impossible de mettre à jour sklearn : {e}")

if not _sklearn_ok:
    # Fallback : désactiver le MLPredictor → NLU utilise les règles regex
    log.info("  → Activation du fallback : NLU utilisera les règles regex (sklearn indisponible).")
    log.info("  → Le bot fonctionnera normalement avec 14 intents détectés par regex.")

    # Monkey-patch MLPredictor pour désactiver les modèles TF-IDF cassés
    import modules.ml_predictor as _mlmod

    class _SafeMLPredictor(_mlmod.MLPredictor):
        def _load_tfidf(self):
            return False          # Force fallback regex dans NLU
        def _load_finetuned(self):
            return False

    _mlmod.MLPredictor = _SafeMLPredictor
    log.info("  ✓ MLPredictor patché → NLU regex actif.")
else:
    log.info("  ✓ sklearn compatible — modèles ML actifs.")

# ── Vérifier packages critiques ──────────────────────────────
log.info("[Check] Packages critiques...")
MISSING = []
for pkg, pip_name in [
    ("flask",                "flask"),
    ("joblib",               "joblib"),
    ("gtts",                 "gTTS"),
    ("colorlog",             "colorlog"),
    ("numpy",                "numpy"),
    ("sentence_transformers","sentence-transformers"),
    ("faiss",                "faiss-cpu"),
    ("edge_tts",             "edge-tts"),
]:
    try:
        __import__(pkg)
        log.info(f"  ✓ {pkg}")
    except ImportError:
        log.warning(f"  ✗ {pkg} absent — installation automatique...")
        try:
            _r = subprocess.run(
                [sys.executable, "-m", "pip", "install", pip_name, "-q"],
                capture_output=True, text=True, timeout=180
            )
            if _r.returncode == 0:
                __import__(pkg)
                log.info(f"  ✓ {pkg} installé.")
            else:
                log.error(f"  Échec installation {pkg}: {_r.stderr[:100]}")
                MISSING.append(pip_name)
        except Exception as _e:
            log.error(f"  Impossible d'installer {pkg}: {_e}")
            MISSING.append(pip_name)

# Packages critiques (Flask, faiss, etc.) sont bloquants ; edge-tts ne l'est pas
CRITICAL = [p for p in MISSING if p not in ("edge-tts",)]
if CRITICAL:
    log.error(f"PACKAGES CRITIQUES MANQUANTS : pip install {' '.join(CRITICAL)}")
    input("\nAppuyez sur Entrée pour quitter...")
    sys.exit(1)

log.info("  ✓ Tous les packages présents.")

# ── Ouvrir le navigateur quand Flask EST prêt ─────────────────
def _open_browser_when_ready():
    import urllib.request
    log.info("  ⏳ Attente démarrage Flask (jusqu'à 40 min si téléchargement Whisper)...")
    for attempt in range(480):          # 480 x 5s = 40 min max
        time.sleep(5)
        try:
            urllib.request.urlopen("http://localhost:5000", timeout=2)
            import webbrowser
            webbrowser.open("http://localhost:5000")
            log.info("  ✓ Flask prêt — navigateur ouvert sur http://localhost:5000")
            return
        except Exception:
            elapsed = (attempt + 1) * 5
            if attempt % 12 == 0:      # log toutes les 60s
                log.info(f"  ... chargement ({elapsed}s) — téléchargement Whisper en cours...")
    log.warning("  Timeout 40 min dépassé — ouvrez http://localhost:5000 manuellement.")

threading.Thread(target=_open_browser_when_ready, daemon=True).start()

# ── Lancement Flask ───────────────────────────────────────────
log.info("")
log.info(">>> Lancement Flask sur http://localhost:5000 ...")
log.info(">>> Ctrl+C pour arrêter")
log.info("")

try:
    import runpy
    runpy.run_path(os.path.join(HERE, "app.py"), run_name="__main__")
except KeyboardInterrupt:
    log.info("Serveur arrêté.")
except Exception as e:
    log.error(f"ERREUR FATALE : {e}")
    log.error(traceback.format_exc())
    input("\nAppuyez sur Entrée pour quitter...")
    sys.exit(1)
