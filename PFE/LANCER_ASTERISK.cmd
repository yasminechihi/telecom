@echo off
:: ============================================================
::  LANCER_ASTERISK.cmd
::  Lance Asterisk dans WSL pour le VoiceBot Tunisie Telecom
::  Double-cliquez sur ce fichier pour demarrer Asterisk.
:: ============================================================

title Asterisk WSL - Tunisie Telecom

echo.
echo  =====================================================
echo   Asterisk WSL -- Tunisie Telecom VoiceBot
echo  =====================================================
echo.

:: Verifier que WSL est installe
where wsl >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERREUR] WSL n'est pas installe sur ce PC.
    echo  Installez WSL : wsl --install
    pause
    exit /b 1
)

:: Verifier qu'Asterisk est installe dans WSL
wsl -u root -- which asterisk >nul 2>&1
if %errorlevel% neq 0 (
    echo  [INFO] Asterisk n'est pas encore installe dans WSL.
    echo  Lancement du script de configuration...
    echo.

    :: Calculer le chemin WSL du dossier PFE
    set "PFE_WIN=%~dp0"
    set "PFE_WIN=%PFE_WIN:~0,-1%"

    :: Convertir le chemin Windows en chemin WSL
    for /f "tokens=*" %%i in ('wsl wslpath -a "%PFE_WIN%"') do set "PFE_WSL=%%i"

    echo  Chemin WSL detecte : %PFE_WSL%
    echo.
    echo  Installation en cours (peut prendre quelques minutes)...
    wsl -u root -- bash "%PFE_WSL%/setup_asterisk_wsl.sh"
    if %errorlevel% neq 0 (
        echo  [ERREUR] Le script d'installation a echoue.
        echo  Ouvrez WSL manuellement et tapez :
        echo    sudo bash /mnt/c/.../PFE/setup_asterisk_wsl.sh
        pause
        exit /b 1
    )
    goto :check_ami
)

:: Asterisk installe : verifier s'il tourne deja
echo  Verification statut Asterisk...
wsl -u root -- pgrep -x asterisk >nul 2>&1
if %errorlevel% equ 0 (
    echo  [OK] Asterisk est deja en cours d'execution.
    goto :check_ami
)

:: Demarrer Asterisk (methode securisee — evite le bug AMI banner)
echo  Demarrage d'Asterisk dans WSL...
set "PFE_WIN=%~dp0"
set "PFE_WIN=%PFE_WIN:~0,-1%"
for /f "tokens=*" %%i in ('wsl wslpath -a "%PFE_WIN%"') do set "PFE_WSL_LANCER=%%i"

:: Demarrer en daemon proprement (pas "service start" qui bogue l'AMI dans WSL2)
wsl -u root -- bash -c "asterisk -g 2>/dev/null; sleep 1"
timeout /t 5 /nobreak >nul

:: Verifier
wsl -u root -- pgrep -x asterisk >nul 2>&1
if %errorlevel% neq 0 (
    echo  [WARN] Tentative via script safe...
    wsl -u root -- bash -c "chmod +x '%PFE_WSL_LANCER%/restart_asterisk_safe.sh' && bash '%PFE_WSL_LANCER%/restart_asterisk_safe.sh'" 2>nul
    timeout /t 8 /nobreak >nul
    wsl -u root -- pgrep -x asterisk >nul 2>&1
    if %errorlevel% neq 0 (
        echo  [ERREUR] Asterisk ne demarre pas.
        echo  Verifiez les logs WSL : wsl -u root -- tail -30 /var/log/asterisk/full
        pause
        exit /b 1
    )
)

:: Attendre que l'AMI soit initialise
timeout /t 4 /nobreak >nul

echo  [OK] Asterisk est en cours d'execution.

:check_ami
:: Attendre que l'AMI soit pret
echo.
echo  Attente disponibilite AMI (port 5038)...
timeout /t 3 /nobreak >nul

:: Test connexion AMI
python -c "from asterisk_ami import check_asterisk_available; r=check_asterisk_available(); print('[OK] AMI disponible !' if r['available'] else '[WARN] AMI non accessible : '+str(r.get('error','')))" 2>nul
if %errorlevel% neq 0 (
    echo  [INFO] Test AMI : Python ou asterisk_ami.py non disponible ici.
    echo  Le test sera fait au lancement de user_app.py.
)

:: Afficher le statut des peers SIP
echo.
echo  Peers SIP enregistres :
wsl -u root -- asterisk -rx "sip show peers" 2>nul
echo.

echo  =====================================================
echo   Asterisk est pret !
echo.
echo   Ensuite :
echo    1. Verifier que MicroSIP affiche [Registered 1001]
echo    2. Lancer user_app.py (LANCER_USER_APP.cmd)
echo    3. Tester un transfert dans le chat
echo  =====================================================
echo.
pause
