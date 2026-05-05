@echo off
:: Ouvre le port UDP 5002 (découverte automatique mobile) dans le pare-feu Windows
:: Doit être lancé en tant qu'Administrateur (clic droit → "Exécuter en tant qu'administrateur")

echo.
echo ========================================================
echo   Ouverture du port UDP 5002 — Auto-Discovery Mobile
echo ========================================================
echo.

:: Supprimer l'ancienne règle si elle existe (évite les doublons)
netsh advfirewall firewall delete rule name="TT-Espace-Discovery-UDP" >nul 2>&1

:: Ajouter la règle pour le port UDP 5002
netsh advfirewall firewall add rule ^
  name="TT-Espace-Discovery-UDP" ^
  dir=in ^
  action=allow ^
  protocol=UDP ^
  localport=5002 ^
  description="Découverte automatique du serveur user_app.py par l'app mobile"

if %errorlevel% == 0 (
    echo [OK] Port UDP 5002 autorisé dans le pare-feu Windows.
    echo      L'app mobile peut maintenant trouver le serveur automatiquement.
) else (
    echo [ERREUR] Impossible d'ajouter la règle.
    echo          Assurez-vous de lancer ce script en tant qu'Administrateur.
)

echo.
echo Appuyez sur une touche pour fermer...
pause >nul
