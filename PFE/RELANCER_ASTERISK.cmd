@echo off
:: ============================================================
::  RELANCER_ASTERISK.cmd
::  Redémarrage PROPRE d'Asterisk (résout le bug AMI banner)
::
::  UTILISEZ CE FICHIER à la place de "service asterisk restart"
::  car "service asterisk restart" dans WSL2 provoque :
::    • AMI ne répond plus → "Connection closed by foreign host"
::    • MicroSIP perd son enregistrement SIP
::
::  Ce script :
::    1. Arrête Asterisk proprement (core stop now)
::    2. Le redémarre en daemon
::    3. Vérifie que l'AMI répond (banner Asterisk)
::    4. Affiche les peers SIP (MicroSIP doit se ré-enregistrer)
:: ============================================================

title Relancer Asterisk - Tunisie Telecom

echo.
echo  =====================================================
echo   Redemarrage Asterisk (methode securisee WSL2)
echo   Tunisie Telecom VoiceBot
echo  =====================================================
echo.

:: Vérifier que WSL est disponible
where wsl >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERREUR] WSL n'est pas installe.
    pause
    exit /b 1
)

:: Récupérer le chemin WSL du dossier PFE
set "PFE_WIN=%~dp0"
set "PFE_WIN=%PFE_WIN:~0,-1%"
for /f "tokens=*" %%i in ('wsl wslpath -a "%PFE_WIN%"') do set "PFE_WSL=%%i"

echo  Dossier PFE (WSL) : %PFE_WSL%
echo.

:: Rendre le script bash exécutable et le lancer
echo  [1/2] Preparation du script de redemarrage...
wsl -u root -- chmod +x "%PFE_WSL%/restart_asterisk_safe.sh"

echo  [2/2] Lancement du redemarrage...
echo.
echo  ---------------------------------------------------
wsl -u root -- bash "%PFE_WSL%/restart_asterisk_safe.sh"
echo  ---------------------------------------------------
echo.

:: Test Python AMI depuis Windows
echo  Test connexion AMI depuis Python (Windows)...
python -c "from asterisk_ami import check_asterisk_available; r=check_asterisk_available(); print('  [OK] AMI disponible ! Banner: '+r.get('banner','')) if r['available'] else print('  [WARN] AMI: '+str(r.get('error','non accessible')))" 2>nul || (
    echo  [INFO] Python non disponible dans ce contexte.
    echo        Le test AMI sera effectue au lancement de user_app.py
)

echo.
echo  =====================================================
echo   Prochaines etapes :
echo.
echo   1. MicroSIP doit afficher [Disponible 1001]
echo      Si ce n'est pas le cas dans 30s :
echo        Clic droit dans MicroSIP → Deconnexion → Connexion
echo.
echo   2. Lancer l'application :
echo        LANCER_USER_APP.cmd
echo.
echo   3. Tester un transfert dans le chat
echo  =====================================================
echo.
pause
