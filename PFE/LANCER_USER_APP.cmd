@echo off
chcp 65001 > nul
title Mon Espace TT — Interface Utilisateur (Port 5001)
color 5F

:: ── Auto-élévation en Administrateur ─────────────────────
:: Nécessaire pour que netsh (port forwarding WSL) fonctionne
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo  Elevation en administrateur requise pour le port forwarding Asterisk...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

echo.
echo  ============================================
echo   Mon Espace TT — Interface Utilisateur
echo   http://localhost:5001
echo  ============================================
echo.

cd /d "%~dp0"

:: ── Vérifier serviceAccountKey.json ─────────────────────
if not exist "serviceAccountKey.json" (
    echo  [ERREUR] serviceAccountKey.json introuvable !
    echo.
    echo  Pour le creer :
    echo    1. https://console.firebase.google.com
    echo    2. Votre projet ^> Project Settings ^> Service Accounts
    echo    3. Generate new private key ^> sauvegarder ici sous :
    echo       %~dp0serviceAccountKey.json
    echo.
    pause
    exit /b 1
)

:: ── Installer les dépendances si manquantes ───────────────
echo  Verification des dependances...
pip show flask >nul 2>&1         || pip install flask werkzeug --quiet
pip show firebase-admin >nul 2>&1 || pip install firebase-admin --quiet
pip show numpy >nul 2>&1          || pip install numpy --quiet
pip show scikit-learn >nul 2>&1   || pip install scikit-learn --quiet
pip show faster-whisper >nul 2>&1 || pip install faster-whisper --quiet
pip show edge-tts >nul 2>&1       || pip install edge-tts --quiet
echo  [OK] Dependances verifiees
echo.
echo  Demarrage...
echo  (Asterisk WSL se lance automatiquement en arriere-plan)
echo.

python user_app.py

pause
