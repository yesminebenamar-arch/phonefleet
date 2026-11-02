#!/data/data/com.termux/files/usr/bin/bash
# Profil TOUTES_OPTIONS : tout active (alertes toutes classes, batterie, bio,
# GPS, statut local deployment_status.txt).
export PROFILE=TOUTES_OPTIONS
exec "${PFE_REPO:-$HOME/pfe}/termux/start_deployment.sh"
