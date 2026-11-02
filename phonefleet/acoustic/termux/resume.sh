#!/data/data/com.termux/files/usr/bin/bash
# Reprend le DERNIER profil choisi via termux/deploy_menu.sh, sans repasser
# par le menu — pratique en widget "PFE_RESUME" pour un redémarrage manuel
# rapide en un seul tap (ex. après avoir arrêté le receiver par erreur).
#
# Usage :
#   ./termux/resume.sh
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
STATE_FILE="$HOME/.pfe_last_profile"

if [ ! -f "$STATE_FILE" ]; then
    echo "Aucun profil mémorisé pour l'instant."
    echo "Lance d'abord une fois : ./termux/deploy_menu.sh"
    exit 1
fi

PROFILE="$(cat "$STATE_FILE")"
echo "Reprise du profil : $PROFILE"
export PROFILE
exec "$PFE_REPO/termux/start_deployment.sh"