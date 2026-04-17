@echo off
chcp 65001 >nul
title Installation Coqui TTS
color 0B

cd /d "%~dp0"

REM ══════════════════════════════════════════════════════════════
REM  INSTALLER_COQUI_TTS.cmd
REM  A executer UNE SEULE FOIS avant de demarrer le voicebot
REM
REM  L'erreur "Failed to build TTS" est due aux C++ Build Tools
REM  manquants sous Windows. Ce script essaie plusieurs methodes.
REM ══════════════════════════════════════════════════════════════

set PY=C:\Users\Yasmine\anaconda3\envs\whisper_env\python.exe
set CONDA=C:\Users\Yasmine\anaconda3\Scripts\conda.exe

echo.
echo  =========================================================
echo   Installation de Coqui TTS (arabe + fine-tuning tunisien)
echo  =========================================================
echo.

if not exist "%PY%" (
    echo  [ERREUR] Environnement whisper_env introuvable : %PY%
    pause
    exit /b 1
)

echo  Python : %PY%
echo.

REM ── Methode 1 : conda install (binaires pre-compiles, pas de C++) ──
echo  [1/3] Tentative via conda (recommande sur Windows)...
if exist "%CONDA%" (
    "%CONDA%" install -c conda-forge tts -n whisper_env -y
    if not errorlevel 1 (
        echo.
        echo  ✓ Coqui TTS installe via conda !
        goto :success
    )
    echo  conda n'a pas fonctionne, essai methode suivante...
    echo.
) else (
    echo  conda non trouve, on passe a pip...
    echo.
)

REM ── Methode 2 : pip install avec --only-binary (evite la compilation) ──
echo  [2/3] Tentative via pip (binaires pre-compiles uniquement)...
"%PY%" -m pip install TTS --only-binary=:all:
if not errorlevel 1 (
    echo.
    echo  ✓ Coqui TTS installe via pip (binaires) !
    goto :success
)
echo  pip binaires n'a pas fonctionne, essai methode suivante...
echo.

REM ── Methode 3 : pip install version specifique stable ──
echo  [3/3] Tentative pip version 0.22.0 (stable Windows)...
"%PY%" -m pip install TTS==0.22.0
if not errorlevel 1 (
    echo.
    echo  ✓ Coqui TTS 0.22.0 installe !
    goto :success
)

REM ── Echec total : instructions manuelles ──
echo.
echo  =========================================================
echo  [ERREUR] Toutes les methodes automatiques ont echoue.
echo.
echo  SOLUTION MANUELLE (une seule fois) :
echo.
echo  1. Installez Visual C++ Build Tools :
echo     https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo     Choisir : "C++ build tools" dans le selecteur
echo.
echo  2. Redemarrez ce script apres l'installation des Build Tools.
echo.
echo  OU : utilisez conda directement dans Anaconda Prompt :
echo     conda activate whisper_env
echo     conda install -c conda-forge tts
echo  =========================================================
echo.
pause
exit /b 1

:success
echo.
echo  =========================================================
echo   Coqui TTS installe dans whisper_env !
echo  =========================================================
echo.
echo  PREMIER DEMARRAGE :
echo  Le modele arabe sera telecharge (~50 Mo) au 1er appel TTS.
echo.
echo  FINE-TUNING TUNISIEN (optionnel) :
echo  Apres entrainement, renseignez dans config.py :
echo    COQUI_TTS_CUSTOM_MODEL  = "models/tts_tunisian/best_model.pth"
echo    COQUI_TTS_CUSTOM_CONFIG = "models/tts_tunisian/config.json"
echo.
echo  Vous pouvez maintenant lancer DEMARRER.cmd
echo.
pause
