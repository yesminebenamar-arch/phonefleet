"""Déploie le code Android sur le Fairphone et lance le receiver en arrière-plan.

Usage : python -m pc.launch
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.logging_utils import get_logger
from pc import ssh_client

log = get_logger("launch")

REPO_ROOT = Path(__file__).resolve().parent.parent
REMOTE_HOME = config.TERMUX_HOME
REMOTE_REPO = f"{REMOTE_HOME}/pfe"


def main() -> None:
    # Demande le site + le piézo s'ils ne sont pas encore renseignés (côté PC),
    # puis persiste dans .env qui sera déployé sur le Fairphone juste après.
    config.setup_interactive()

    log.info("=== LANCEMENT EXPÉRIENCE — site=%s, piézo=%s (SN %s) ===",
             config.SITE, config.PIEZO_MODEL, config.PIEZO_SERIAL)

    if not (config.PHONE_HOST or config.PHONE_IP):
        raise SystemExit("PHONE_HOST (ou PHONE_IP) manquant dans .env")

    with ssh_client.connect() as ssh:
        # Préparer dossier distant
        ssh_client.run(ssh, f"mkdir -p {REMOTE_REPO} {config.TERMUX_DATA}")

        # Uploader le code (core + android + termux + .env)
        ssh_client.upload_dir(ssh, REPO_ROOT / "core", f"{REMOTE_REPO}/core")
        ssh_client.upload_dir(ssh, REPO_ROOT / "android", f"{REMOTE_REPO}/android")
        ssh_client.upload_dir(ssh, REPO_ROOT / "termux", f"{REMOTE_REPO}/termux")
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            ssh_client.upload(ssh, env_path, f"{REMOTE_REPO}/.env")

        # Tuer un éventuel ancien processus
        ssh_client.run(ssh, "pkill -f android.receiver 2>/dev/null || true")
        time.sleep(1)

        # Lancer en arrière-plan avec nohup
        log_path = f"{REMOTE_HOME}/receiver.log"
        cmd = (
            f"cd {REMOTE_REPO} && "
            f"nohup python -m android.receiver > {log_path} 2>&1 &"
        )
        ssh_client.run(ssh, cmd)
        log.info("Receiver lancé (log : %s)", log_path)

        # Vérification
        time.sleep(3)
        code, out, _ = ssh_client.run(ssh, "pgrep -a -f android.receiver")
        if out:
            log.info("Processus actif : %s", out)
        else:
            log.warning("Aucun processus receiver détecté — vérifier %s", log_path)

    log.info("Lancez maintenant la collecte :  python -m pc.collect")


if __name__ == "__main__":
    main()
