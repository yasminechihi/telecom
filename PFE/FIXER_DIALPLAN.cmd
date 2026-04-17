@echo off
:: ============================================================
::  FIXER_DIALPLAN.cmd — Mise à jour complète du dialplan
::  + Création des répertoires Asterisk nécessaires
::  + Vérification packages Python TTS/STT
:: ============================================================
title Fixer Dialplan Asterisk - TT VoiceBot

echo.
echo  =====================================================
echo   Mise a jour dialplan Asterisk + TTS/STT Setup
echo  =====================================================
echo.

set "PFE_WIN=%~dp0"
set "PFE_WIN=%PFE_WIN:~0,-1%"
for /f "tokens=*" %%i in ('wsl wslpath -a "%PFE_WIN%"') do set "PFE_WSL=%%i"

echo  Dossier PFE : %PFE_WSL%
echo.

if not exist "%PFE_WIN%\extensions_new.conf" (
    echo  [ERREUR] extensions_new.conf non trouve
    pause
    exit /b 1
)

:: [1] Créer les répertoires Asterisk nécessaires dans WSL
echo  [1/5] Creation des repertoires Asterisk...
wsl -u root -- mkdir -p /usr/share/asterisk/sounds/custom
wsl -u root -- mkdir -p /var/spool/asterisk/monitor
wsl -u root -- chown -R asterisk:asterisk /var/spool/asterisk/monitor 2>nul
wsl -u root -- chown -R asterisk:asterisk /usr/share/asterisk/sounds/custom 2>nul
wsl -u root -- chmod 777 /var/spool/asterisk/monitor
wsl -u root -- chmod 777 /usr/share/asterisk/sounds/custom
echo  [OK] Repertoires crees

:: [1b] Installer ffmpeg dans WSL si absent (nécessaire pour TTS MP3→WAV)
echo.
echo  [1b] Verification ffmpeg dans WSL...
wsl -u root -- bash -c "ffmpeg -version >nul 2>&1 && echo PRESENT || (echo Installation ffmpeg... && apt-get install -y ffmpeg -q)"
echo  [OK] ffmpeg WSL verifie

:: [2] Copier le dialplan dans WSL
echo.
echo  [2/5] Copie du dialplan vers /etc/asterisk/extensions.conf ...
wsl -u root -- cp "%PFE_WSL%/extensions_new.conf" /etc/asterisk/extensions.conf
if %errorlevel% neq 0 (
    echo  [ERREUR] Copie echouee
    pause
    exit /b 1
)
echo  [OK] Fichier copie

:: [3] Vérifier le dialplan
echo.
echo  [3/5] Verification dialplan...
wsl -u root -- grep -c "notify" /etc/asterisk/extensions.conf
wsl -u root -- grep "TTS_FILE\|Record\|ExecIf" /etc/asterisk/extensions.conf
echo  [OK] Verification OK

:: [4] Recharger le dialplan Asterisk
echo.
echo  [4/5] Rechargement du dialplan dans Asterisk...
wsl -u root -- asterisk -rx "dialplan reload"
timeout /t 2 /nobreak >nul
wsl -u root -- asterisk -rx "dialplan show tt-transfer"
echo  [OK] Dialplan rechargé

:: [5] Vérifier les packages Python TTS/STT (côté Windows)
echo.
echo  [5/5] Verification packages Python TTS/STT...
python -c "import edge_tts; print('  [OK] edge-tts disponible')" 2>nul || echo  [?] edge-tts absent - installer avec : pip install edge-tts
python -c "from gtts import gTTS; print('  [OK] gTTS disponible')" 2>nul || echo  [?] gTTS absent - installer avec : pip install gtts
python -c "from faster_whisper import WhisperModel; print('  [OK] faster-whisper disponible')" 2>nul || echo  [?] faster-whisper absent - installer avec : pip install faster-whisper
python -c "import pydub; print('  [OK] pydub disponible')" 2>nul || echo  [?] pydub absent - installer avec : pip install pydub
python -c "import ffmpeg; print('  [OK] ffmpeg-python disponible')" 2>nul || echo  [?] ffmpeg-python absent (optionnel)
where ffmpeg >nul 2>&1 && echo   [OK] ffmpeg dans PATH || echo  [!] ffmpeg non trouve dans PATH - installer : https://ffmpeg.org ou choco install ffmpeg

echo.
echo  =====================================================
echo   SETUP COMPLET !
echo.
echo   PACKAGES MANQUANTS ? Installer avec :
echo     pip install edge-tts gtts faster-whisper pydub
echo     (et ffmpeg : choco install ffmpeg)
echo.
echo   PROCHAINE ETAPE :
echo     Redemarrer user_app.py et app.py
echo  =====================================================
echo.
pause
