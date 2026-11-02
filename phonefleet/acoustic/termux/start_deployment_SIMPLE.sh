#!/data/data/com.termux/files/usr/bin/bash
# Profil SIMPLE : enregistrement + classification IA journalisee, AUCUN SMS.
export PROFILE=SIMPLE
exec "${PFE_REPO:-$HOME/pfe}/termux/start_deployment.sh"
