#!/data/data/com.termux/files/usr/bin/bash
# Launcher commun de deploiement PFE (point 2).
# Ne pas lancer directement : utilise par les wrappers start_deployment_<PROFIL>.sh
# (ou par deploy_menu.sh / resume.sh / start_pfe_boot.sh) qui exportent
# PROFILE avant de l'appeler.
#
# Variables (surchargables) :
#   PFE_REPO             racine du repo sur le telephone (defaut : $HOME/pfe)
#   PROFILE              SIMPLE | ALERTE | ALLO_BRUIT | TOUTES_OPTIONS
#   PFE_NONINTERACTIVE=1 force le mode non interactif (pas de setup, ex. au boot)
#
# Resilience : la boucle d'enregistrement (android.receiver) est demarree
# via termux/supervisor.sh, elle-meme lancee en arriere-plan et DETACHEE du
# terminal (setsid + nohup + disown). Consequences :
#   - une coupure de connexion (SSH, Tailscale) ne tue plus l'enregistrement :
#     le processus continue independamment du terminal qui l'a lance ;
#     s'il venait quand meme a s'arreter (crash), le superviseur le relance
#     automatiquement au bout de 10s ;
#   - au reboot, start_pfe_boot.sh rappelle ce meme script, qui relance donc
#     le superviseur normalement ;
#   - un arret est TOUJOURS volontaire et definitif : seul termux/stop.sh
#     pose le drapeau ~/.pfe_stop_requested que le superviseur respecte.
#     Tout nouveau lancement (menu, resume, boot) efface ce drapeau, car
#     lancer une mission est par definition un choix explicite de redemarrer.

PFE_REPO="${PFE_REPO:-$HOME/pfe}"
PROFILE="${PROFILE:-TOUTES_OPTIONS}"
export PROFILE
STOP_FLAG="$HOME/.pfe_stop_requested"
LOG_FILE="$HOME/pfe_receiver.log"

if [ ! -d "$PFE_REPO" ]; then
    echo "ERREUR : repo introuvable a $PFE_REPO (definir PFE_REPO)."
    exit 1
fi
cd "$PFE_REPO" || exit 1
export PYTHONPATH="$PFE_REPO"

echo "=== Deploiement PFE - profil $PROFILE ==="

# Empeche la veille de suspendre l'enregistrement.
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock

# Configuration interactive seulement si on a un terminal (jamais au boot).
if [ -t 0 ] && [ "${PFE_NONINTERACTIVE:-0}" != "1" ]; then
    python -m android.setup --force || true
fi

# Autonomie (MEMORY_LIMIT / BATTERY_LIMIT) + marque le debut de mission.
python -m android.status --start || true

# Un lancement volontaire efface toujours le drapeau d'arret : sinon un
# "stop" precedent bloquerait ce nouveau demarrage manuel/boot.
rm -f "$STOP_FLAG"

echo ""
echo "Demarrage de l'enregistrement (profil $PROFILE)."
echo "Le processus tourne en arriere-plan et resiste aux coupures de connexion."
echo "Suivi en direct : tail -f $LOG_FILE"
echo "Pour arreter definitivement : ./termux/stop.sh (ou icone PFE_STOP)"

chmod +x "$PFE_REPO/termux/supervisor.sh" 2>/dev/null

# Garde-fou rapide (facultatif, non-atomique) : donne un message clair tout
# de suite si un superviseur tourne deja, avant meme d'en lancer un second
# qui echouerait de toute facon au verrou flock a l'interieur de
# supervisor.sh. La protection REELLE est le flock dans supervisor.sh :
# ce pgrep n'est qu'un confort d'affichage.
EXISTING_SUPERVISOR="$(pgrep -f "$PFE_REPO/termux/supervisor.sh" | head -n 1)"
if [ -n "$EXISTING_SUPERVISOR" ]; then
    echo "Un superviseur tourne deja (PID $EXISTING_SUPERVISOR) - aucun second superviseur ne sera lance."
    exit 0
fi

setsid nohup "$PFE_REPO/termux/supervisor.sh" </dev/null >>"$LOG_FILE" 2>&1 &
disown

echo "Superviseur lance en arriere-plan (PID $!)."
echo "(Le verrou flock dans supervisor.sh confirmera l'unicite - voir : cat ~/.pfe_supervisor.lock)"