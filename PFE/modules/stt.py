# ============================================================
#  modules/stt.py — Module Speech-to-Text (Whisper)
#  Transcription de la voix en texte darija tunisien
# ============================================================

import os
import io
import time
import logging
import threading
import queue
import numpy as np

# sounddevice et soundfile sont optionnels (non nécessaires pour l'API Flask)
# Ils ne sont utilisés que pour l'enregistrement micro en ligne de commande.
try:
    import sounddevice as sd
    import soundfile as sf
    _AUDIO_AVAILABLE = True
except ImportError:
    sd = None
    sf = None
    _AUDIO_AVAILABLE = False

logger = logging.getLogger(__name__)


class STTModule:
    """
    Module de transcription vocale utilisant OpenAI Whisper (faster-whisper).
    Optimisé pour le darija tunisien (arabe dialectal + français).

    Flux :
        Microphone → Buffer audio → Whisper → Texte darija
    """

    def __init__(self, config):
        self.config  = config
        self.model   = None
        self._loaded = False

        # File d'attente audio pour le streaming
        self._audio_queue  = queue.Queue()
        self._is_recording = False

        self._load_model()

    # ─────────────────────────────────────────────────────────
    # Chargement du modèle Whisper
    # ─────────────────────────────────────────────────────────
    def _load_model(self):
        """Charge faster-whisper avec le modèle configuré."""
        try:
            from faster_whisper import WhisperModel
            logger.info(f"Chargement Whisper '{self.config.STT_MODEL}' sur {self.config.STT_DEVICE}...")
            self.model = WhisperModel(
                self.config.STT_MODEL,
                device=self.config.STT_DEVICE,
                compute_type="int8"  # Efficace sur CPU
            )
            self._loaded = True
            logger.info("Whisper chargé avec succès.")
        except ImportError:
            logger.warning("faster-whisper non installé. Tentative avec openai-whisper...")
            self._load_openai_whisper()
        except Exception as e:
            logger.error(f"Erreur chargement Whisper: {e}")
            raise

    def _load_openai_whisper(self):
        """Fallback vers openai-whisper classique."""
        try:
            import whisper
            self.model = whisper.load_model(self.config.STT_MODEL)
            self._loaded = True
            self._use_openai = True
            logger.info("openai-whisper chargé (fallback).")
        except ImportError:
            raise RuntimeError("Aucun moteur Whisper disponible. Installe faster-whisper ou openai-whisper.")

    # ─────────────────────────────────────────────────────────
    # Enregistrement audio depuis le microphone
    # ─────────────────────────────────────────────────────────
    def _audio_callback(self, indata, frames, time_info, status):
        """Callback sounddevice — alimente la file audio."""
        if status:
            logger.debug(f"STT audio status: {status}")
        self._audio_queue.put(indata.copy())

    def record_until_silence(self) -> np.ndarray:
        """
        Enregistre jusqu'à détection de silence ou timeout.
        Retourne un tableau numpy (float32, mono).
        """
        sample_rate  = self.config.AUDIO_SAMPLE_RATE
        silence_secs = self.config.STT_SILENCE_TIMEOUT
        max_secs     = self.config.MAX_RECORD_SECONDS

        audio_chunks  = []
        silent_frames = 0
        total_frames  = 0
        frames_per_sec = sample_rate // self.config.AUDIO_CHUNK_SIZE

        silence_threshold = 0.005   # Amplitude RMS (ajuster selon micro — valeur basse = plus sensible)
        silence_frames_needed = int(silence_secs * frames_per_sec)

        self._audio_queue = queue.Queue()

        if not _AUDIO_AVAILABLE:
            raise RuntimeError("sounddevice/soundfile non installés — pip install sounddevice soundfile")

        with sd.InputStream(
            samplerate=sample_rate,
            channels=self.config.AUDIO_CHANNELS,
            dtype="float32",
            blocksize=self.config.AUDIO_CHUNK_SIZE,
            callback=self._audio_callback
        ):
            logger.debug("Écoute en cours...")
            while True:
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                audio_chunks.append(chunk)
                total_frames += 1

                # Détection silence
                rms = float(np.sqrt(np.mean(chunk**2)))
                if rms < silence_threshold:
                    silent_frames += 1
                else:
                    silent_frames = 0  # Reset si son détecté

                # Conditions d'arrêt
                if silent_frames >= silence_frames_needed and total_frames > frames_per_sec:
                    logger.debug(f"Silence détecté après {total_frames} frames.")
                    break
                if total_frames >= max_secs * frames_per_sec:
                    logger.debug("Durée max atteinte.")
                    break

        if not audio_chunks:
            return np.array([], dtype=np.float32)

        audio = np.concatenate(audio_chunks, axis=0).flatten()
        return audio

    # ─────────────────────────────────────────────────────────
    # Transcription
    # ─────────────────────────────────────────────────────────
    def transcribe_audio(self, audio: np.ndarray) -> str:
        """
        Transcrit un tableau numpy en texte arabe/darija.

        Args:
            audio: Signal audio float32 à 16kHz

        Returns:
            Texte transcrit (str) ou chaîne vide si échec.
        """
        if not self._loaded or audio is None or len(audio) < 100:
            return ""

        try:
            if hasattr(self, "_use_openai"):
                return self._transcribe_openai(audio)
            else:
                return self._transcribe_faster(audio)
        except Exception as e:
            logger.error(f"Erreur transcription: {e}")
            return ""

    def _transcribe_faster(self, audio: np.ndarray) -> str:
        """Transcription avec faster-whisper."""
        segments, info = self.model.transcribe(
            audio,
            language=self.config.STT_LANGUAGE,
            beam_size=self.config.STT_BEAM_SIZE,
            vad_filter=self.config.STT_VAD_FILTER,
            word_timestamps=False,
            # Prompt initial pour guider vers le darija tunisien
            initial_prompt="مرحبا تليكوم تونس، عندي مشكلة في الخدمة"
        )
        text = " ".join(seg.text.strip() for seg in segments)
        logger.debug(f"STT (faster-whisper) → '{text}' [lang:{info.language} prob:{info.language_probability:.2f}]")
        return text.strip()

    def _transcribe_openai(self, audio: np.ndarray) -> str:
        """Transcription avec openai-whisper (fallback)."""
        result = self.model.transcribe(
            audio,
            language=self.config.STT_LANGUAGE,
            initial_prompt="مرحبا تليكوم تونس، عندي مشكلة في الخدمة"
        )
        text = result.get("text", "").strip()
        logger.debug(f"STT (openai-whisper) → '{text}'")
        return text

    def transcribe_file(self, filepath: str) -> str:
        """Transcrit un fichier audio (wav/mp3/ogg)."""
        try:
            if not _AUDIO_AVAILABLE:
                raise RuntimeError("soundfile non installé — pip install soundfile")
            audio, sr = sf.read(filepath, dtype="float32")
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)  # Stéréo → mono
            if sr != self.config.AUDIO_SAMPLE_RATE:
                import resampy
                audio = resampy.resample(audio, sr, self.config.AUDIO_SAMPLE_RATE)
            return self.transcribe_audio(audio)
        except Exception as e:
            logger.error(f"Erreur transcription fichier {filepath}: {e}")
            return ""

    # ─────────────────────────────────────────────────────────
    # Interface principale : écouter + transcrire
    # ─────────────────────────────────────────────────────────
    def listen_and_transcribe(self) -> str:
        """
        Méthode principale : écoute le micro et retourne le texte.
        Utilisée par le DialogManager à chaque tour de parole.
        """
        logger.info("En attente de la voix du client...")
        audio = self.record_until_silence()

        if len(audio) < self.config.AUDIO_SAMPLE_RATE * 0.5:
            logger.debug("Audio trop court — ignoré.")
            return ""

        text = self.transcribe_audio(audio)
        if text:
            logger.info(f"Client dit: '{text}'")
        return text
