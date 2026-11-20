@echo off
rem Lance l'application Lecteur (fenêtre sans console noire).
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo L'installation n'est pas terminee : lance d'abord installer.bat
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m lecteur
