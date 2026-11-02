#!/data/data/com.termux/files/usr/bin/bash
# Profil ALLO_BRUIT : ALERTE + alerte dediee classe biologique / poisson
# (seuil BIO_MIN_CONFIDENCE + notification "[ALLO BRUIT]").
export PROFILE=ALLO_BRUIT
exec "${PFE_REPO:-$HOME/pfe}/termux/start_deployment.sh"
