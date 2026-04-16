@echo off
:: ============================================================
::  TOUT_RELANCER.cmd
::  Relance TOUT en une seule fois :
::    1. Arrete user_app.py (s'il tourne)
::    2. Arrete et redémarre Asterisk dans WSL (méthode sécurisée)
::    3. Vérifie que MicroSIP peut s'enregistrer
::    4. Relance user_app.py
::
::  Double-cliquez sur ce fichier pour tout relancer proprement.
:: ============================================================

title Relancer Tout - Tunisie Telecom VoiceBot
color 0A

echo.
echo  =====================================================
echo   TOUT RELANCER - Tunisie Telecom VoiceBot
echo  =====================================================
echo.

:: ── Récupérer le chemin WSL du dossier PFE ─────────────────
set "PFE_WIN=%~dp0"
set "PFE_WIN=%PFE_WIN:~0,-1%"
for /f "tokens=*" %%i in ('wsl wslpath -a "%PFE_WIN%"') do set "PFE_WSL=%%i"

echo  Dossier : %PFE_WIN%
echo.

:: ══════════════════════════════════════════════════
::  ÉTAPE 1 — Arrêter user_app.py s'il tourne
:: ══════════════════════════════════════════════════
echo  [1/4] Arret de user_app.py...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq user_app*" >nul 2>&1
:: Fermer par port 5001 si nécessaire
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5001 " 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo  [OK] Processus Python arretes (si existants)
echo.

:: ══════════════════════════════════════════════════
::  ÉTAPE 2 — Redémarrer Asterisk proprement dans WSL
:: ══════════════════════════════════════════════════
echo  [2/4] Redemarrage Asterisk dans WSL...
echo.

:: Tuer Asterisk et nettoyer
wsl -u root -- bash -c "pkill -KILL asterisk 2>/dev/null; sleep 1; rm -f /var/run/asterisk/asterisk.pid /tmp/asterisk.pid 2>/dev/null; echo 'Arret OK'"

:: Démarrer Asterisk en daemon (méthode sécurisée — PAS service restart)
echo  Demarrage Asterisk daemon...
wsl -u root -- bash -c "asterisk -g 2>/dev/null; echo 'Demarrage lance'"
timeout /t 6 /nobreak >nul

:: Forcer le rechargement du module AMI
echo  Rechargement module AMI...
wsl -u root -- bash -c "asterisk -rx 'manager reload' 2>/dev/null && echo 'AMI reload OK' || echo 'AMI reload: attente...'"
timeout /t 3 /nobreak >nul

:: Vérifier qu'Asterisk tourne
wsl -u root -- pgrep -x asterisk >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERREUR] Asterisk ne tourne pas !
    echo  Essai demarrage alternatif...
    wsl -u root -- bash -c "nohup asterisk > /tmp/ast_boot.log 2>&1 &"
    timeout /t 5 /nobreak >nul
    wsl -u root -- pgrep -x asterisk >nul 2>&1
    if %errorlevel% neq 0 (
        color 0C
        echo  [ERREUR CRITIQUE] Asterisk ne demarre pas.
        echo  Lancez : wsl -u root -- tail -20 /var/log/asterisk/full
        goto :show_peers
    )
)
echo  [OK] Asterisk tourne
echo.

:: Test AMI depuis WSL (connexion interne WSL vers WSL)
echo  Test AMI depuis WSL...
wsl -u root -- bash -c "exec 3<>/dev/tcp/127.0.0.1/5038 2>/dev/null && read -t 3 b <&3 && echo \"AMI OK: $b\" && exec 3>&- || echo 'AMI: connexion impossible'"
echo.

:show_peers
:: Afficher les peers SIP
echo  Peers SIP enregistres :
wsl -u root -- asterisk -rx "sip show peers" 2>nul
echo.

:: ══════════════════════════════════════════════════
::  ÉTAPE 3 — Rappel MicroSIP
:: ══════════════════════════════════════════════════
echo  [3/4] Verification MicroSIP...
echo.
echo  >>> VERIFIEZ que MicroSIP affiche [Disponible 1001]
echo  >>> Si MicroSIP affiche autre chose :
echo       1. Clic droit sur le compte 1001 dans MicroSIP
echo       2. Deconnexion
echo       3. Connexion
echo  >>> Attendez 10 secondes avant de continuer.
echo.
timeout /t 8 /nobreak >nul

:: ══════════════════════════════════════════════════
::  ÉTAPE 4 — Relancer user_app.py
:: ══════════════════════════════════════════════════
echo  [4/4] Lancement user_app.py (port 5001)...
echo.

:: Chercher python dans le PATH
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERREUR] Python non trouve dans le PATH.
        echo  Lancez manuellement : python user_app.py
        pause
        exit /b 1
    )
    set PYTHON_CMD=python3
) else (
    set PYTHON_CMD=python
)

:: Lancer user_app.py dans une nouvelle fenêtre
start "user_app - TT VoiceBot" cmd /k "cd /d "%PFE_WIN%" && %PYTHON_CMD% user_app.py"

:: Attendre que user_app démarre
echo  Attente demarrage user_app.py (10 secondes)...
timeout /t 10 /nobreak >nul

:: Vérifier que le port 5001 est ouvert
netstat -an | findstr ":5001 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] user_app.py tourne sur le port 5001
) else (
    echo  [WARN] Port 5001 pas encore ouvert - verifiez la fenetre user_app
)

:: ══════════════════════════════════════════════════
::  RÉSUMÉ FINAL
:: ══════════════════════════════════════════════════
echo.
echo  =====================================================
echo   TOUT EST RELANCE !
echo.
echo   Test AMI depuis Python (Windows) :
echo    Ouvrez dans Chrome : http://localhost:5001/api/user/ami_debug
echo.
echo   Pour tester l'appel :
echo    1. Allez sur : http://localhost:5001
echo    2. Connectez-vous avec votre compte
echo    3. Dans le chat, tapez : je veux parler a un agent
echo    4. MicroSIP doit SONNER
echo  =====================================================
echo.
pause
