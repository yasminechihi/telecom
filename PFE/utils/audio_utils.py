# ============================================================
#  utils/audio_utils.py — Utilitaires Audio
# ============================================================

import logging
import numpy as np

logger = logging.getLogger(__name__)


def record_audio(duration: float, sample_rate: int = 16000) -> np.ndarray:
    """
    Enregistre un audio de durée fixe depuis le microphone.
    Utile pour les tests.
    """
    try:
        import sounddevice as sd
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32"
        )
        sd.wait()
        return audio.flatten()
    except Exception as e:
        logger.error(f"Erreur enregistrement audio: {e}")
        return np.array([], dtype=np.float32)


def play_audio(audio: np.ndarray, sample_rate: int = 16000):
    """Joue un tableau numpy comme audio."""
    try:
        import sounddevice as sd
        sd.play(audio, sample_rate)
        sd.wait()
    except Exception as e:
        logger.error(f"Erreur lecture audio: {e}")


def audio_to_numpy(filepath: str, target_sr: int = 16000) -> np.ndarray:
    """Charge un fichier audio et retourne un tableau numpy normalisé."""
    try:
        import soundfile as sf
        audio, sr = sf.read(filepath, dtype="float32")
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)
        if sr != target_sr:
            try:
                import resampy
                audio = resampy.resample(audio, sr, target_sr)
            except ImportError:
                logger.warning("resampy non installé — rééchantillonnage ignoré.")
        return audio
    except Exception as e:
        logger.error(f"Erreur chargement audio {filepath}: {e}")
        return np.array([], dtype=np.float32)


def save_audio(audio: np.ndarray, filepath: str, sample_rate: int = 16000):
    """Sauvegarde un tableau numpy en fichier WAV."""
    try:
        import soundfile as sf
        sf.write(filepath, audio, sample_rate)
        logger.debug(f"Audio sauvegardé: {filepath}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde audio {filepath}: {e}")


def get_audio_duration(audio: np.ndarray, sample_rate: int = 16000) -> float:
    """Retourne la durée d'un audio en secondes."""
    return len(audio) / sample_rate if len(audio) > 0 else 0.0


def compute_rms(audio: np.ndarray) -> float:
    """Calcule le niveau RMS (volume) d'un segment audio."""
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio**2)))
