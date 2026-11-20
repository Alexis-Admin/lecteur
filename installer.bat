@echo off
rem Installe (ou met a jour) les composants de Lecteur dans le dossier .venv. A lancer une fois.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe. Installe Python 3.12 depuis python.org puis relance ce fichier.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
git config core.hooksPath outils/hooks 2>nul
echo.
echo Installation terminee. Double-clique sur Lecteur.bat pour lancer l'application.
pause
