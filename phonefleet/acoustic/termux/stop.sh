#!/data/data/com.termux/files/usr/bin/bash
# Arrete proprement et DEFINITIVEMENT le receiver en cours, peu importe
# comment il a ete lance (widget PFE_MENU/PFE_RESUME, ./termux/deploy_menu.sh
# a la main, ou demarrage automatique au boot).
#
# Pose d'abord un drapeau ~/.pfe_stop_requested que termux/supervisor.sh
# verifie avant chaque relance : sans ce drapeau, le superviseur relancerait
# automatiquement le receiver quelques secondes apres l'avoir tue (c'est
# justement son role en cas de crash/coupure de connexion). Le drapeau est
# ce qui distingue "arret involontaire a relancer" de "arret voulu par
# l'utilisateur, definitif".
#
# Envoie ensuite SIGINT (equivalent Ctrl+C), capte par le bloc
# try/except KeyboardInterrupt d'android/receiver.py, qui ferme donc
# proprement (pas de coupure brutale en plein enregistrement).
#
# Usage :
#   ./termux/stop.sh
STOP_FLAG="$HOME/.pfe_stop_requested"

# IMPORTANT : poser le drapeau AVANT de tuer le process, pour que le
# superviseur le voie des qu'il constate l'arret du receiver.
touch "$STOP_FLAG"

PID="$(pgrep -f 'android.receiver' | head -n 1)"

if [ -z "$PID" ]; then
    echo "Aucun receiver en cours (rien a arreter)."
    echo "Le drapeau d'arret est pose : un superviseur en cours de demarrage ne relancera pas."
    exit 0
fi

echo "Arret du receiver (PID $PID)..."
kill -INT "$PID"

# Laisse le temps au cycle en cours de se terminer proprement (le WAV en
# cours d'enregistrement + la conversion ffmpeg peuvent prendre jusqu'a
# une quinzaine de secondes a se finaliser selon le moment du signal).
for _ in $(seq 1 15); do
    sleep 1
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "Arrete proprement."
        exit 0
    fi
done

echo "Toujours actif apres 15s - arret force."
kill -9 "$PID" 2>/dev/null
echo "Arrete (force)."