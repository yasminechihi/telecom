# ============================================================
#  modules/tts.py — Module Text-to-Speech
#  Synthèse vocale en arabe / darija tunisien
# ============================================================

import os
import io
import time
import logging
import tempfile
import threading

logger = logging.getLogger(__name__)


class TTSModule:
    """
    Module de synthèse vocale (TTS).
    Moteurs supportés :
        - gTTS (Google, en ligne, qualité naturelle)
        - pyttsx3 (hors-ligne, fallback)

    Le texte darija est directement envoyé à l'API Google TTS
    avec la langue 'ar' — résultat très naturel pour l'arabe
    dialectal tunisien.
    """

    def __init__(self, config):
        self.config = config
        self._pygame_init = False
        self._init_audio_player()
        logger.info(f"TTS initialisé — moteur: {config.TTS_ENGINE}")

    # ─────────────────────────────────────────────────────────
    # Initialisation du lecteur audio
    # ─────────────────────────────────────────────────────────
    def _init_audio_player(self):
        """Initialise pygame pour la lecture audio."""
        try:
            import pygame
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=1, buffer=2048)
            pygame.mixer.init()
            self._pygame_init = True
        except Exception as e:
            logger.warning(f"pygame non disponible: {e}. Utilisation de playsound/aplay.")

    # ─────────────────────────────────────────────────────────
    # Synthèse et lecture
    # ─────────────────────────────────────────────────────────
    def speak(self, text: str, blocking: bool = True):
        """
        Synthétise le texte en parole et le joue.

        Args:
            text: Texte en darija/arabe à lire
            blocking: Si True, attend la fin de la lecture
        """
        if not text or not text.strip():
            return

        logger.info(f"BOT dit: '{text}'")

        engine = self.config.TTS_ENGINE.lower()
        if engine == "gtts":
            self._speak_gtts(text, blocking)
        elif engine == "pyttsx3":
            self._speak_pyttsx3(text)
        else:
            logger.warning(f"Moteur TTS inconnu: {engine}. Fallback gTTS.")
            self._speak_gtts(text, blocking)

    def _speak_gtts(self, text: str, blocking: bool = True):
        """Synthèse via Google TTS (en ligne requis)."""
        try:
            from gtts import gTTS
            import pygame

            tts = gTTS(
                text=text,
                lang=self.config.TTS_LANGUAGE,
                slow=self.config.TTS_SLOW
            )

            # Sauvegarde temporaire
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
                tts.save(tmp_path)

            self._play_file(tmp_path, blocking=blocking)

            # Nettoyage
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Erreur gTTS: {e}")
            # Fallback pyttsx3
            self._speak_pyttsx3(text)

    def _speak_pyttsx3(self, text: str):
        """Synthèse hors-ligne via pyttsx3."""
        try:
            import pyttsx3
            engine = pyttsx3.init()

            # Cherche une voix arabe
            voices = engine.getProperty('voices')
            for voice in voices:
                if 'arab' in voice.name.lower() or 'ar' in voice.id.lower():
                    engine.setProperty('voice', voice.id)
                    break

            engine.setProperty('rate', 150)   # Vitesse de parole
            engine.setProperty('volume', 0.9)
            engine.say(text)
            engine.runAndWait()

        except Exception as e:
            logger.error(f"Erreur pyttsx3: {e}")
            # Dernier recours : imprimer dans la console
            print(f"\n[BOT]: {text}\n")

    def _play_file(self, filepath: str, blocking: bool = True):
        """Joue un fichier audio MP3/WAV."""
        try:
            import pygame
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            if blocking:
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
        except Exception:
            # Fallback : aplay (Linux) ou playsound
            try:
                import playsound
                playsound.playsound(filepath, block=blocking)
            except Exception:
                try:
                    os.system(f"aplay '{filepath}' 2>/dev/null || afplay '{filepath}' 2>/dev/null")
                except Exception as e:
                    logger.error(f"Impossible de jouer l'audio: {e}")

    # ─────────────────────────────────────────────────────────
    # Sauvegarde audio
    # ─────────────────────────────────────────────────────────
    def save_speech(self, text: str, output_path: str) -> bool:
        """
        Sauvegarde la synthèse vocale dans un fichier MP3.
        Utile pour les messages pré-enregistrés.
        """
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang=self.config.TTS_LANGUAGE, slow=self.config.TTS_SLOW)
            tts.save(output_path)
            logger.info(f"Audio sauvegardé: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur sauvegarde TTS: {e}")
            return False

    # ─────────────────────────────────────────────────────────
    # Messages prédéfinis du VoiceBot
    # ─────────────────────────────────────────────────────────
    def speak_greeting(self):
        self.speak(self.config.GREETING_MESSAGE)

    def speak_farewell(self):
        self.speak(self.config.FAREWELL_MESSAGE)

    def speak_transfer(self):
        self.speak(self.config.TRANSFER_MESSAGE)

    def speak_not_understood(self):
        self.speak(self.config.NOT_UNDERSTOOD_MSG)

    def speak_wait(self):
        self.speak("إستنى لحظة من فضلك...")
