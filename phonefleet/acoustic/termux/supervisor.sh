#!/data/data/com.termux/files/usr/bin/bash
# Boucle de supervision : relance android.receiver automatiquement en cas
# de crash OU de coupure de connexion (SSH/Tailscale), tant qu'aucun arret
# volontaire n'a ete demande (touch de ~/.pfe_stop_requested par stop.sh).
#
# Lance en arriere-plan par termux/start_deployment.sh via
# `setsid ... nohup ... & disown` : ce script est donc detache du terminal
# qui l'a demarre. Une deconnexion SSH ne l'interrompt plus, contrairement
# a un simple `exec python -m android.receiver` lance depuis une session
# attachee.
#
# VERROU (flock) : garantit qu'une SEULE instance de ce script peut etre
# active a la fois, meme si start_deployment.sh est declenche deux fois en
# meme temps (ex. widget touche pendant le boot). Le verrou est tenu par CE
# script pendant toute sa duree de vie et libere automatiquement quand il
# se termine (sortie normale ou kill) - pas besoin de le liberer a la main.
#
# Ne pas lancer directement a la main : utilise par start_deployment.sh.
PFE_REPO="${PFE_REPO:-$HOME/pfe}"
PROFILE="${PROFILE:-TOUTES_OPTIONS}"
STOP_FLAG="$HOME/.pfe_stop_requested"
LOG_FILE="$HOME/pfe_receiver.log"
LOCK_FILE="$HOME/.pfe_supervisor.lock"

cd "$PFE_REPO" || exit 1
export PYTHONPATH="$PFE_REPO"
export PROFILE

# ============================================================
# VERROU ATOMIQUE - une seule instance de supervisor.sh possible
# ============================================================
# On ouvre le fichier de verrou sur le descripteur 200, puis on essaie de
# le verrouiller sans attendre (-n = non-blocking). Si un autre
# supervisor.sh detient deja le verrou, flock echoue immediatement (code
# different de 0) et on sort sans rien casser.
exec 200>"$LOCK_FILE"

if ! flock -n 200; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Verrou deja detenu par un autre superviseur - sortie sans demarrer." >> "$LOG_FILE"
    exit 1
fi

# On ecrit notre PID dans le lock file, uniquement pour diagnostic humain
# (cat ~/.pfe_supervisor.lock). Ce n'est pas ca qui protege, c'est flock.
echo $$ > "$LOCK_FILE"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Superviseur demarre (profil $PROFILE, PID $$), verrou acquis." >> "$LOG_FILE"

while true; do
    if [ -f "$STOP_FLAG" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Arret volontaire detecte avant lancement - supervision stoppee." >> "$LOG_FILE"
        break
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lancement receiver (profil $PROFILE)" >> "$LOG_FILE"
    python -m android.receiver >> "$LOG_FILE" 2>&1
    code=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] receiver arrete (code $code)" >> "$LOG_FILE"

    if [ -f "$STOP_FLAG" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Arret volontaire confirme - pas de relance." >> "$LOG_FILE"
        break
    fi

    # Le receiver s'est arrete tout seul (crash, coupure de connexion ayant
    # tue le process, erreur ffmpeg/termux-api...) sans demande d'arret :
    # on considere que c'est involontaire et on relance automatiquement.
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Relance automatique dans 10s (crash/deconnexion)" >> "$LOG_FILE"
    sleep 10
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fin de la supervision." >> "$LOG_FILE"
# Le verrou (fd 200) est relache automatiquement ici, a la fermeture du script.