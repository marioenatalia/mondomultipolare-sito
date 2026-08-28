#!/usr/bin/env bash
# ------------------------------------------------------------
#  Aggiornamento del sito dal canale Telegram (Linux / NAS / macOS)
#  Esempio di riga crontab, ogni 15 minuti:
#    */15 * * * * /volume1/web/telegram-news-site/scripts/aggiorna.sh
# ------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")/.."

PY=python3
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

mkdir -p data
{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] avvio aggiornamento"
  "$PY" run.py aggiorna
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] fine"
} >> data/aggiornamenti.log 2>&1
