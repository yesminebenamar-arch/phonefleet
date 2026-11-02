#!/data/data/com.termux/files/usr/bin/bash
# Lance automatiquement par Termux:Boot apres un redemarrage du telephone
# (coupure batterie, reboot force, crash). Relit le dernier profil choisi
# via termux/deploy_menu.sh (~/.pfe_last_profile) ; ALERTE par defaut si ce
# fichier n'existe pas encore. Toujours NON interactif (pas de terminal au
# boot) et journalise dans ~/pfe_boot.log pour diagnostic a posteriori.
#
# La boucle de relance en cas de crash/coupure de connexion est desormais
# geree directement par termux/start_deployment.sh -> termux/supervisor.sh
# (relance automatique tant que ~/.pfe_stop_requested n'existe pas). Ce
# script de boot n'a donc plus besoin de sa propre boucle de retry : il se
# contente de demarrer le deploiement une fois, le superviseur prend le
# relais en arriere-plan.
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
STATE_FILE="$HOME/.pfe_last_profile"
LOG_FILE="$HOME/pfe_boot.log"

# Laisse le temps a Android/Termux de finir de demarrer (reseau, stockage
# partage monte) avant de lancer quoi que ce soit.
sleep 15

# Demarre le serveur SSH si necessaire
if ! pgrep sshd >/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Demarrage de sshd" >> "$LOG_FILE"
    sshd
fi

PROFILE="ALERTE"
[ -f "$STATE_FILE" ] && PROFILE="$(cat "$STATE_FILE")"
export PROFILE
export PFE_NONINTERACTIVE=1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Demarrage boot - profil=$PROFILE" >> "$LOG_FILE"

# start_deployment.sh efface lui-meme ~/.pfe_stop_requested (un reboot est
# un redemarrage explicite de la mission) puis lance le superviseur en
# arriere-plan et rend la main immediatement.
"$PFE_REPO/termux/start_deployment.sh" >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] start_deployment.sh termine (superviseur lance en arriere-plan)" >> "$LOG_FILE"