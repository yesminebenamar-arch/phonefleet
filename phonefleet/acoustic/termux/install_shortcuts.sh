#!/data/data/com.termux/files/usr/bin/bash
# Installe les raccourcis Termux:Widget (icones ecran d'accueil) et Termux:Boot.
# A lancer une fois sur le telephone :  bash termux/install_shortcuts.sh
#
# Prerequis cote telephone :
#   pkg install termux-api
#   Applications Termux:Widget et Termux:Boot installees (F-Droid)
set -e
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
SHORTCUTS="$HOME/.shortcuts"
BOOT="$HOME/.termux/boot"

mkdir -p "$SHORTCUTS" "$BOOT"

# Icone recommandee : menu de choix de profil (pas besoin de retenir un nom
# de script), mémorise le choix pour PFE_RESUME et le démarrage auto.
ln -sf "$PFE_REPO/termux/deploy_menu.sh" "$SHORTCUTS/PFE_MENU.sh"
# Icone de reprise rapide : relance le DERNIER profil choisi, sans repasser
# par le menu (pratique après un arret accidentel).
ln -sf "$PFE_REPO/termux/resume.sh" "$SHORTCUTS/PFE_RESUME.sh"

# Icones directes par profil (toujours disponibles si tu preferes ne pas
# passer par le menu).
for p in SIMPLE ALERTE ALLO_BRUIT TOUTES_OPTIONS; do
    ln -sf "$PFE_REPO/termux/start_deployment_${p}.sh" "$SHORTCUTS/PFE_${p}.sh"
done

# Icone statut
ln -sf "$PFE_REPO/termux/status.sh" "$SHORTCUTS/PFE_STATUS.sh"
# Icone arret propre : un tap = SIGINT au receiver en cours (equivalent
# Ctrl+C), peu importe comment il a ete lance (widget, menu, boot auto).
ln -sf "$PFE_REPO/termux/stop.sh" "$SHORTCUTS/PFE_STOP.sh"
# Demarrage automatique au boot
ln -sf "$PFE_REPO/termux/boot/start_pfe_boot.sh" "$BOOT/start_pfe_boot.sh"

chmod +x "$PFE_REPO"/termux/*.sh "$PFE_REPO"/termux/boot/*.sh 2>/dev/null || true

echo "Raccourcis installes :"
echo "  Widget : $SHORTCUTS"
echo "     PFE_MENU (recommande)   PFE_RESUME   PFE_STATUS   PFE_STOP"
echo "     PFE_SIMPLE  PFE_ALERTE  PFE_ALLO_BRUIT  PFE_TOUTES_OPTIONS"
echo "  Boot   : $BOOT/start_pfe_boot.sh"
echo ""
echo "Ajoutez le widget Termux:Widget a l'ecran d'accueil pour voir les icones."