#!/data/data/com.termux/files/usr/bin/bash
# Menu interactif de lancement, simplifie pour un usage terrain a 3 choix :
# Demarrer / Etat / Arreter. Le choix "Demarrer" ouvre ensuite le sous-menu
# des profils (SIMPLE/ALERTE/ALLO_BRUIT/TOUTES_OPTIONS), inchange par
# rapport a avant. Le choix retenu est memorise dans ~/.pfe_last_profile,
# relu ensuite par termux/resume.sh et termux/boot/start_pfe_boot.sh.
#
# Usage :
#   ./termux/deploy_menu.sh
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
STATE_FILE="$HOME/.pfe_last_profile"

echo "=== BIOFISH ==="
echo "  1) ▶️  Démarrer"
echo "  2) 📊 État"
echo "  3) ⏹️  Arrêter"
read -rp "Choix [1-3] : " action

case "$action" in
    2)
        bash "$PFE_REPO/termux/pfe_status.sh"
        exit 0
        ;;
    3)
        bash "$PFE_REPO/termux/stop.sh"
        exit 0
        ;;
    1)
        : # on continue ci-dessous vers le choix du profil
        ;;
    *)
        echo "Choix invalide."
        exit 1
        ;;
esac

echo ""
echo "=== BIOFISH — Choix du profil de déploiement ==="
echo "  1) SIMPLE          — enregistrement seul, aucun SMS/appel"
echo "  2) ALERTE          — + SMS bateaux/batterie"
echo "  3) ALLO_BRUIT      — + appel téléphonique (détections de forte confiance)"
echo "  4) TOUTES_OPTIONS  — tout activé (SMS + appel + GPS + dashboard)"
read -rp "Choix [1-4] (défaut 2 = ALERTE) : " choix

case "${choix:-2}" in
    1) PROFILE=SIMPLE ;;
    2) PROFILE=ALERTE ;;
    3) PROFILE=ALLO_BRUIT ;;
    4) PROFILE=TOUTES_OPTIONS ;;
    *) echo "Choix invalide — ALERTE utilisé par défaut."; PROFILE=ALERTE ;;
esac

echo "$PROFILE" > "$STATE_FILE"
echo "Profil retenu : $PROFILE (mémorisé dans $STATE_FILE)"
export PROFILE
exec "$PFE_REPO/termux/start_deployment.sh"