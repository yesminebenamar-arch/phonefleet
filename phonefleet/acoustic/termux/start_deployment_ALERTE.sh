#!/data/data/com.termux/files/usr/bin/bash
# Profil ALERTE : SMS sur toutes les classes d'alerte + SMS batterie faible.
export PROFILE=ALERTE
exec "${PFE_REPO:-$HOME/pfe}/termux/start_deployment.sh"
