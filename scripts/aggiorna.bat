@echo off
REM ------------------------------------------------------------
REM  Aggiornamento del sito dal canale Telegram (Windows)
REM  Da collegare all'Utilita' di pianificazione, ogni 15 minuti.
REM ------------------------------------------------------------

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

if not exist "data" mkdir data
echo [%date% %time%] avvio aggiornamento >> data\aggiornamenti.log
"%PY%" run.py aggiorna >> data\aggiornamenti.log 2>&1
echo [%date% %time%] fine >> data\aggiornamenti.log
