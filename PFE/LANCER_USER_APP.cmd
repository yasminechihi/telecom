@echo off
chcp 65001 > nul
title Mon Espace TT — Interface Utilisateur (Port 5001)
color 1F

echo.
echo  ============================================
echo   Mon Espace TT — Interface Utilisateur
echo   http://localhost:5001
echo  ============================================
echo.
echo  PREREQUIS :
echo   [1] EasyPHP doit etre demarre (MySQL actif)
echo   [2] Importer create_db.sql via phpMyAdmin
echo   [3] pip install mysql-connector-python
echo.
echo  Demarrage...
echo.

cd /d "%~dp0"

:: Installer les dépendances manquantes
pip show flask >nul 2>&1 || pip install flask werkzeug
pip show mysql-connector-python >nul 2>&1 || pip install mysql-connector-python

python user_app.py

pause
