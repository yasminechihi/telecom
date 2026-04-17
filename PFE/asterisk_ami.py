#!/usr/bin/env python3
# ============================================================
#  asterisk_ami.py — Intégration Asterisk via WSL
#
#  ARCHITECTURE :
#    Windows (Python/Flask)
#        │
#        ├─ wsl -u root -- asterisk -rx "database put ..."
#        ├─ wsl -u root -- asterisk -rx "originate SIP/1001 ..."
#        │        ↓ (Unix socket WSL — toujours accessible)
#        │   Asterisk dans WSL
#        │        │
#        │   [Dialplan tt-transfer]
#        │     1. Lit CLIENT_PROBLEM depuis AstDB
#        │     2. Joue le fichier TTS du problème (WAV 8kHz)
#        │     3. Enregistre la réponse vocale de l'agent
#        │        │
#        ├─ Thread watcher (Windows Python)
#        │     • Détecte l'enregistrement dans WSL
#        │     • Transcrit avec Whisper (STT)
#        │     • POST → user_app /api/internal/agent_reply
#        │     • Bot apprend la réponse pour la session
#
#  TTS : edge-tts (ar-SA-HamedNeural) ou gTTS (fallback)
#  STT : faster_whisper (small, ar) — installé avec l'app Flask
# ============================================================

import os
import subprocess
import time
import logging
import threading
import tempfile
import json as _json
import urllib.request
import urllib.error

logger = logging.getLogger("asterisk_ami")

# ════════════════════════════════════════════════════════════
#  CONFIGURATION
# ════════════════════════════════════════════════════════════

AGENT_EXTEN      = "1001"
AMI_CONTEXT      = "tt-transfer"
AMI_EXTEN        = "notify"
CALL_TIMEOUT_SEC = 30

CALLER_ID_NAME   = "Tunisie Telecom Bot"
CALLER_ID_NUMBER = "0800100200"

AMI_PORT   = 5038
AMI_USER   = "ttadmin"
AMI_SECRET = "TT@2026"

# Répertoire sons Asterisk dans WSL (doit exister)
_WSL_SOUNDS_CUSTOM = "/usr/share/asterisk/sounds/custom"
# Répertoire enregistrements Asterisk dans WSL
_WSL_MONITOR_DIR   = "/var/spool/asterisk/monitor"
# Secret partagé avec user_app.py pour l'endpoint interne
_INTERNAL_SECRET   = "tt_backoffice_2026"
# URL de l'endpoint interne user_app
_USER_APP_REPLY_URL = "http://127.0.0.1:5001/api/internal/agent_reply"

# Cache Whisper (chargé une seule fois)
_whisper_model = None
_whisper_lock  = threading.Lock()


# ════════════════════════════════════════════════════════════
#  HELPERS WSL
# ════════════════════════════════════════════════════════════

def _wsl_rx(command: str, timeout: int = 10) -> tuple:
    """
    Exécute une commande Asterisk via 'wsl asterisk -rx'.
    Returns: (success: bool, stdout: str, stderr: str)
    """
    try:
        r = subprocess.run(
            ["wsl", "-u", "root", "--", "asterisk", "-rx", command],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return False, "", "WSL non installé"
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout ({timeout}s)"
    except Exception as e:
        return False, "", str(e)


def _wsl_sh(command: str, timeout: int = 10) -> tuple:
    """Exécute une commande shell dans WSL (pas via asterisk -rx)."""
    try:
        r = subprocess.run(
            ["wsl", "-u", "root", "--", "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout
        )
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return False, "", "WSL non installé"
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout ({timeout}s)"
    except Exception as e:
        return False, "", str(e)


def _win_path_to_wsl(win_path: str) -> str:
    """
    Convertit un chemin Windows → chemin WSL /mnt/<drive>/...
    Ex : C:\\Users\\X\\temp\\foo.wav → /mnt/c/Users/X/temp/foo.wav
    """
    win_path = os.path.abspath(win_path)
    drive = win_path[0].lower()
    rest  = win_path[2:].replace("\\", "/")
    return f"/mnt/{drive}{rest}"


def check_asterisk_available() -> dict:
    """Vérifie si Asterisk tourne dans WSL via socket Unix."""
    ok, stdout, stderr = _wsl_rx("core show version", timeout=6)
    if ok and "Asterisk" in stdout:
        return {"available": True, "host": "wsl_cli", "via": "wsl_cli",
                "banner": stdout[:80]}
    return {"available": False, "host": "wsl_cli",
            "error": stderr or "Asterisk ne répond pas"}


# ════════════════════════════════════════════════════════════
#  TTS — Synthèse vocale du problème client
# ════════════════════════════════════════════════════════════

def _generate_problem_tts(problem_text: str, ticket_id: str) -> str:
    """
    Génère un fichier audio TTS du texte du problème client et le place
    dans le répertoire sons d'Asterisk dans WSL.

    Stratégie (sans dépendance à Windows ffmpeg) :
      1. Générer le MP3 sur Windows (edge-tts ou gTTS)
      2. Copier le MP3 vers /tmp dans WSL via _win_path_to_wsl
      3. Convertir MP3→WAV 8kHz avec ffmpeg/sox/avconv dans WSL
      4. Déplacer le WAV vers /usr/share/asterisk/sounds/custom/

    Returns: nom du son Asterisk (ex: 'custom/tt_problem_abc123')
             ou '' en cas d'échec.
    """
    if not problem_text.strip():
        return ""

    filename = f"tt_problem_{ticket_id}" if ticket_id else "tt_problem_tmp"
    mp3_path = os.path.join(tempfile.gettempdir(), f"{filename}.mp3")

    # ── Étape 1 : Générer le TTS → MP3 (Windows Python) ─────────

    tts_ok = False

    # Essai A : edge-tts module Python (voix arabe haute qualité)
    try:
        import edge_tts, asyncio

        async def _do_edge_tts():
            communicate = edge_tts.Communicate(problem_text, "ar-SA-HamedNeural")
            await communicate.save(mp3_path)

        # Créer une nouvelle boucle dans un thread pour éviter les conflits Flask
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(asyncio.run, _do_edge_tts()).result(timeout=25)

        if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500:
            tts_ok = True
            logger.info(f"[TTS] edge-tts (module) OK → {mp3_path}")
    except Exception as e:
        logger.warning(f"[TTS] edge-tts module échoué : {e}")

    # Essai B : edge-tts en ligne de commande
    if not tts_ok:
        try:
            r = subprocess.run(
                ["edge-tts", "--voice", "ar-SA-HamedNeural",
                 "--text", problem_text, "--write-media", mp3_path],
                capture_output=True, timeout=25
            )
            if r.returncode == 0 and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500:
                tts_ok = True
                logger.info(f"[TTS] edge-tts CLI OK → {mp3_path}")
        except Exception as e:
            logger.warning(f"[TTS] edge-tts CLI échoué : {e}")

    # Essai C : gTTS (fallback internet)
    if not tts_ok:
        try:
            from gtts import gTTS
            gTTS(problem_text, lang="ar").save(mp3_path)
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500:
                tts_ok = True
                logger.info(f"[TTS] gTTS OK → {mp3_path}")
        except Exception as e:
            logger.warning(f"[TTS] gTTS échoué : {e}")

    if not tts_ok:
        logger.error("[TTS] Tous les moteurs TTS ont échoué")
        return ""

    # ── Étape 2 : Copier le MP3 vers WSL /tmp ────────────────────
    wsl_mp3 = _win_path_to_wsl(mp3_path)
    wsl_mp3_tmp = f"/tmp/{filename}.mp3"
    wsl_wav_dst = f"{_WSL_SOUNDS_CUSTOM}/{filename}.wav"

    # S'assurer que le répertoire de destination existe
    _wsl_sh(f"mkdir -p {_WSL_SOUNDS_CUSTOM}", timeout=5)

    ok_cp, _, err_cp = _wsl_sh(
        f"cp '{wsl_mp3}' '{wsl_mp3_tmp}'", timeout=10
    )
    if not ok_cp:
        logger.error(f"[TTS] Copie MP3 vers WSL échouée : {err_cp}")
        return ""

    # ── Étape 3 : Convertir MP3 → WAV 8kHz dans WSL ─────────────
    # Essayer ffmpeg, sox, avconv dans l'ordre
    conv_ok = False

    # Essai ffmpeg (installé par défaut dans Ubuntu WSL)
    ok_ff, _, err_ff = _wsl_sh(
        f"ffmpeg -y -i '{wsl_mp3_tmp}' "
        f"-ar 8000 -ac 1 -acodec pcm_s16le '{wsl_wav_dst}' 2>/dev/null",
        timeout=30
    )
    if ok_ff:
        # Vérifier que le fichier WAV a été créé et n'est pas vide
        ok_test, out_test, _ = _wsl_sh(
            f"test -s '{wsl_wav_dst}' && echo ok", timeout=5
        )
        if ok_test and "ok" in out_test:
            conv_ok = True
            logger.info(f"[TTS] Conversion ffmpeg (WSL) OK → {wsl_wav_dst}")
    if not conv_ok:
        logger.warning(f"[TTS] ffmpeg WSL : {err_ff[:80]}")

    # Essai sox (alternative légère)
    if not conv_ok:
        ok_sox, _, err_sox = _wsl_sh(
            f"sox '{wsl_mp3_tmp}' -r 8000 -c 1 -b 16 '{wsl_wav_dst}' 2>/dev/null",
            timeout=30
        )
        if ok_sox:
            ok_test, out_test, _ = _wsl_sh(
                f"test -s '{wsl_wav_dst}' && echo ok", timeout=5
            )
            if ok_test and "ok" in out_test:
                conv_ok = True
                logger.info(f"[TTS] Conversion sox (WSL) OK → {wsl_wav_dst}")
        if not conv_ok:
            logger.warning(f"[TTS] sox WSL : {err_sox[:80]}")

    # Essai avconv (alias ffmpeg sur certains systèmes)
    if not conv_ok:
        ok_av, _, _ = _wsl_sh(
            f"avconv -y -i '{wsl_mp3_tmp}' "
            f"-ar 8000 -ac 1 -acodec pcm_s16le '{wsl_wav_dst}' 2>/dev/null",
            timeout=30
        )
        if ok_av:
            ok_test, out_test, _ = _wsl_sh(
                f"test -s '{wsl_wav_dst}' && echo ok", timeout=5
            )
            if ok_test and "ok" in out_test:
                conv_ok = True
                logger.info(f"[TTS] Conversion avconv (WSL) OK → {wsl_wav_dst}")

    # Nettoyage du MP3 temporaire dans WSL et Windows
    _wsl_sh(f"rm -f '{wsl_mp3_tmp}'", timeout=5)
    try:
        os.remove(mp3_path)
    except Exception:
        pass

    if not conv_ok:
        logger.error(
            "[TTS] Conversion WAV dans WSL échouée. "
            "Installer ffmpeg dans WSL : sudo apt-get install -y ffmpeg"
        )
        return ""

    logger.info(f"[TTS] Son Asterisk prêt → custom/{filename}")
    return f"custom/{filename}"


def _convert_to_asterisk_wav(src_path: str, dst_path: str) -> bool:
    """(Conservé pour compatibilité — non utilisé dans le flux principal.)"""
    try:
        from pydub import AudioSegment
        sound = AudioSegment.from_file(src_path)
        sound = sound.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        sound.export(dst_path, format="wav")
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
            return True
    except Exception as e:
        logger.warning(f"[TTS] pydub échoué : {e}")

    return False


# ════════════════════════════════════════════════════════════
#  STT — Transcription de la réponse vocale de l'agent
# ════════════════════════════════════════════════════════════

def _get_whisper_model():
    """Charge le modèle Whisper une seule fois (lazy loading, thread-safe)."""
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            try:
                from faster_whisper import WhisperModel
                _whisper_model = WhisperModel(
                    "small", device="cpu", compute_type="int8"
                )
                logger.info("[STT] faster_whisper 'small' chargé")
            except Exception as e:
                logger.warning(f"[STT] faster_whisper non disponible : {e}")
                _whisper_model = None
        return _whisper_model


def _transcribe_wav(win_wav_path: str) -> str:
    """
    Transcrit un fichier WAV avec Whisper (arabe).
    Returns: texte transcrit ou ''.
    """
    # Essai 1 : faster_whisper (installé dans l'env Flask)
    model = _get_whisper_model()
    if model is not None:
        try:
            segments, _ = model.transcribe(win_wav_path, language="ar")
            text = " ".join(s.text.strip() for s in segments).strip()
            logger.info(f"[STT] Transcription faster_whisper : '{text[:80]}'")
            return text
        except Exception as e:
            logger.warning(f"[STT] faster_whisper transcription échouée : {e}")

    # Essai 2 : openai-whisper
    try:
        import whisper
        m = whisper.load_model("small")
        result = m.transcribe(win_wav_path, language="ar")
        text = result.get("text", "").strip()
        logger.info(f"[STT] Transcription openai-whisper : '{text[:80]}'")
        return text
    except Exception as e:
        logger.warning(f"[STT] openai-whisper échoué : {e}")

    # Essai 3 : whisper via WSL Python
    try:
        wsl_wav_path = _win_path_to_wsl(win_wav_path)
        ok, stdout, _ = _wsl_sh(
            f"python3 -c \""
            f"import whisper; m=whisper.load_model('small'); "
            f"r=m.transcribe('{wsl_wav_path}', language='ar'); "
            f"print(r['text'].strip())\"",
            timeout=90
        )
        if ok and stdout:
            logger.info(f"[STT] Transcription WSL whisper : '{stdout[:80]}'")
            return stdout.strip()
    except Exception as e:
        logger.warning(f"[STT] WSL whisper échoué : {e}")

    return ""


def _post_agent_reply(ticket_id: str, session_id: str, response_text: str):
    """POST la réponse transcrite à user_app pour que le bot l'apprenne."""
    payload = _json.dumps({
        "ticket_id":  ticket_id,
        "response":   response_text,
        "session_id": session_id,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            _USER_APP_REPLY_URL,
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "X-Internal-Secret": _INTERNAL_SECRET,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            logger.info(f"[STT] Réponse agent apprise → user_app : {body[:100]}")
            return True
    except urllib.error.HTTPError as e:
        logger.warning(f"[STT] POST user_app HTTP {e.code} : {e.read().decode()[:100]}")
    except Exception as e:
        logger.error(f"[STT] POST user_app échoué : {e}")
    return False


def _watch_and_transcribe(ticket_id: str, session_id: str,
                           timeout_secs: int = 600):
    """
    Thread daemon — attend le fichier d'enregistrement de l'agent dans WSL,
    le transcrit avec Whisper et envoie la réponse à user_app.

    L'enregistrement est produit par Asterisk via l'app Record() dans le dialplan.
    Chemin WSL : /var/spool/asterisk/monitor/agent_reply_<ticket_id>.wav
    """
    wsl_rec_path = f"{_WSL_MONITOR_DIR}/agent_reply_{ticket_id}.wav"
    tmp_wav      = os.path.join(tempfile.gettempdir(), f"agent_reply_{ticket_id}.wav")
    wsl_tmp      = _win_path_to_wsl(tmp_wav)

    logger.info(f"[STT] Watcher démarré — en attente de : {wsl_rec_path}")

    deadline = time.time() + timeout_secs
    while time.time() < deadline:
        time.sleep(4)  # Vérification toutes les 4 secondes

        # Vérifier si le fichier existe ET est non-vide dans WSL
        ok, out, _ = _wsl_sh(
            f"test -f '{wsl_rec_path}' && test -s '{wsl_rec_path}' && echo yes",
            timeout=5
        )
        if not (ok and "yes" in out):
            continue

        # Attendre 1 seconde pour que Asterisk finisse d'écrire le fichier
        time.sleep(1)

        logger.info(f"[STT] Enregistrement détecté : {wsl_rec_path}")

        # Copier le fichier de WSL vers Windows (pour que Whisper y accède)
        ok2, _, err2 = _wsl_sh(
            f"cp '{wsl_rec_path}' '{wsl_tmp}'", timeout=10
        )
        if not ok2:
            logger.warning(f"[STT] Copie WSL → Windows échouée : {err2}")
            # Essayer de transcrire directement via WSL
            transcript = ""
            ok3, out3, _ = _wsl_sh(
                f"python3 -c \"import whisper; m=whisper.load_model('small'); "
                f"r=m.transcribe('{wsl_rec_path}', language='ar'); "
                f"print(r['text'].strip())\"",
                timeout=120
            )
            if ok3 and out3:
                transcript = out3.strip()
        else:
            # Transcrire depuis le chemin Windows
            transcript = _transcribe_wav(tmp_wav)
            # Nettoyage tmp Windows
            try:
                if os.path.exists(tmp_wav):
                    os.remove(tmp_wav)
            except Exception:
                pass

        if transcript:
            logger.info(f"[STT] Transcription finale : '{transcript}'")
            _post_agent_reply(ticket_id, session_id, transcript)
        else:
            logger.warning(f"[STT] Transcription vide pour ticket {ticket_id}")

        # Supprimer l'enregistrement WSL
        _wsl_sh(f"rm -f '{wsl_rec_path}'", timeout=5)
        return

    logger.warning(
        f"[STT] Timeout {timeout_secs}s — aucun enregistrement reçu "
        f"pour ticket '{ticket_id}'"
    )


# ════════════════════════════════════════════════════════════
#  ORIGINATE — Déclenchement de l'appel MicroSIP
# ════════════════════════════════════════════════════════════

def originate_call(caller_number: str,
                   ticket_id: str = "",
                   user_name: str = "",
                   problem_text: str = "",
                   session_id: str = "") -> dict:
    """
    Déclenche un appel MicroSIP via Asterisk CLI (wsl asterisk -rx).

    Flux :
      1. Vérifier qu'Asterisk tourne
      2. Générer le TTS du problème client → WAV → Asterisk sounds
      3. Stocker les infos dans AstDB (incluant TTS_FILE)
      4. Lancer originate → MicroSIP sonne
      5. L'agent décroche, entend le TTS du problème
      6. L'agent parle → Asterisk enregistre
      7. Watcher transcrit → bot apprend la réponse (session)

    Returns: {"success": bool, "message": str}
    """
    if not caller_number or caller_number.strip() in ("", "—"):
        return {"success": False, "message": "Numéro de téléphone client manquant"}

    # ── Normaliser le numéro ─────────────────────────────────
    num = caller_number.strip().replace(" ", "").replace("-", "")
    if num.startswith("00216"):
        num = num[2:]
    elif num.startswith("+"):
        num = num[1:]
    elif num.startswith("0") and len(num) == 9:
        num = "216" + num[1:]

    safe_name = (user_name or "Client") \
        .replace('"', "").replace("'", "").replace(";", "").replace("&", "")
    safe_ticket  = (ticket_id or "").replace('"', "").replace("'", "")
    safe_problem = (problem_text or "")[:120] \
        .replace('"', "").replace("'", "").replace(";", "").replace("&", "")

    # ── 1. Vérifier Asterisk ─────────────────────────────────
    status = check_asterisk_available()
    if not status["available"]:
        msg = f"Asterisk non accessible : {status.get('error', '?')}"
        logger.warning(f"[AMI] {msg}")
        return {"success": False, "message": msg}

    logger.info(f"[AMI] Asterisk OK — client={num} ticket={safe_ticket}")

    def _call_thread():
        """Thread async : TTS → AstDB → Originate → Watcher STT."""

        # ── 2. Générer TTS du problème ───────────────────────
        tts_sound = ""
        if safe_problem:
            logger.info(f"[TTS] Génération pour : '{safe_problem[:60]}'...")
            # Créer le répertoire sons custom si besoin
            _wsl_sh(f"mkdir -p {_WSL_SOUNDS_CUSTOM}", timeout=5)
            _wsl_sh(f"mkdir -p {_WSL_MONITOR_DIR}", timeout=5)
            tts_sound = _generate_problem_tts(safe_problem, safe_ticket or num)
            if tts_sound:
                logger.info(f"[TTS] Son prêt : {tts_sound}")
            else:
                logger.warning("[TTS] TTS non généré — l'agent n'entendra pas le problème")

        # ── 3. Stocker les variables dans AstDB ─────────────
        _wsl_rx(f'database put TT CLIENT_NUM "{num}"', timeout=5)
        _wsl_rx(f'database put TT CLIENT_NAME "{safe_name}"', timeout=5)
        _wsl_rx(f'database put TT TICKET_ID "{safe_ticket}"', timeout=5)
        if safe_problem:
            _wsl_rx(f'database put TT CLIENT_PROBLEM "{safe_problem}"', timeout=5)
        if tts_sound:
            _wsl_rx(f'database put TT TTS_FILE "{tts_sound}"', timeout=5)
        else:
            _wsl_rx('database put TT TTS_FILE ""', timeout=5)

        # ── 4. Originate → MicroSIP sonne ───────────────────
        originate_cmd = (
            f"originate SIP/{AGENT_EXTEN} "
            f"extension {AMI_EXTEN}@{AMI_CONTEXT}"
        )
        ok, stdout, stderr = _wsl_rx(originate_cmd, timeout=CALL_TIMEOUT_SEC + 5)

        if ok:
            logger.info(f"[AMI] Originate OK → MicroSIP sonne (client={num})")
        else:
            logger.warning(
                f"[AMI] Originate échoué : stdout={stdout[:80]} stderr={stderr[:80]}"
            )

        # ── 5. Démarrer le watcher STT (enregistrement → transcription) ──
        # session_id = conv_id_db complet (clé de user_conv_state) ; fallback sur safe_ticket
        _real_session_id = session_id or safe_ticket
        if safe_ticket:
            watcher = threading.Thread(
                target=_watch_and_transcribe,
                args=(safe_ticket, _real_session_id),
                daemon=True,
                name=f"stt-watcher-{safe_ticket}",
            )
            watcher.start()
            logger.info(f"[STT] Watcher démarré pour ticket '{safe_ticket}'")

    t = threading.Thread(target=_call_thread, daemon=True,
                         name=f"asterisk-call-{num}")
    t.start()

    return {
        "success": True,
        "method":  "wsl_cli",
        "message": f"Appel initié → MicroSIP (client: {num}, ticket: {safe_ticket})",
        "problem": safe_problem,
    }


# ════════════════════════════════════════════════════════════
#  COMPATIBILITÉ
# ════════════════════════════════════════════════════════════

def get_wsl_ip() -> str:
    return "wsl_cli"


# ════════════════════════════════════════════════════════════
#  TEST DIRECT
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=== Test check_asterisk_available ===")
    s = check_asterisk_available()
    print(s)

    if s["available"]:
        print("\n=== Test TTS ===")
        tts = _generate_problem_tts("عندي مشكل في الإنترنت ما يخدمش", "TEST01")
        print(f"TTS sound: {tts}")

        print("\n=== Test originate (MicroSIP doit sonner) ===")
        result = originate_call(
            "21698000000", "TEST01", "Test User",
            problem_text="عندي مشكل في الإنترنت ما يخدمش"
        )
        print(result)
        time.sleep(10)
    else:
        print("Asterisk non accessible — lancez : sudo asterisk -g")
