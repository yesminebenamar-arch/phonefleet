#!/data/data/com.termux/files/usr/bin/bash
# Affiche le statut condensé (etat, profil, site, cycle, batterie, analyse,
# confiance, autonomie) - equivalent lisible du "BIOFISH STATUS" demande
# pour un usage terrain simple.
#
# Usage :
#   ./termux/pfe_status.sh
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
cd "$PFE_REPO" || exit 1
export PYTHONPATH="$PFE_REPO"
exec python -m android.pretty_status