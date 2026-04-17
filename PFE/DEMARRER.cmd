@echo off
chcp 65001 >nul
title VoiceBot Tunisie Telecom - Interface Web
color 0A

cd /d "%~dp0"

set PY=C:\Users\Yasmine\anaconda3\envs\whisper_env\python.exe

if not exist "%PY%" (
    echo.
    echo  [ERREUR] Python introuvable : %PY%
    pause
    exit /b 1
)

echo.
echo  =====================================================
echo   VoiceBot Tunisie Telecom
echo  =====================================================
echo.
echo  Demarrage en cours...
echo.
echo  IMPORTANT : Le chargement peut prendre 1 a 3 minutes.
echo  Le navigateur s'ouvrira AUTOMATIQUEMENT quand c'est pret.
echo.
echo  NE FERMEZ PAS CETTE FENETRE !
echo  =====================================================
echo.

"%PY%" app_launcher.py

echo.
echo  Serveur arrete.
pause
