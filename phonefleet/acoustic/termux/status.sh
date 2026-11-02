#!/data/data/com.termux/files/usr/bin/bash
# Statut d'autonomie (point 3) - lancable a tout moment, meme si receiver
# tourne en arriere-plan. Affiche MEMORY_LIMIT / BATTERY_LIMIT / date de recup.
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
cd "$PFE_REPO" || exit 1
export PYTHONPATH="$PFE_REPO"
exec python -m android.status "$@"