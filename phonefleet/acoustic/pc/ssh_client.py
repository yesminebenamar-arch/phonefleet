"""Petit wrapper paramiko : connexion + run + upload + download.

Utilisé par pc.launch et pc.collect pour ne pas dupliquer le boilerplate.
"""

from contextlib import contextmanager
from pathlib import Path

import paramiko

from core import config
from core.logging_utils import get_logger

log = get_logger("ssh")


@contextmanager
def connect(host: str = None, user: str = None,
            port: int = None, password: str = None):
    """Context manager qui ouvre/ferme proprement une connexion SSH."""
    # PHONE_HOST = identifiant stable (IP fixe, nom .local ou nom Tailscale),
    # avec repli sur PHONE_IP pour rétro-compatibilité (voir core/config.py).
    host = host or config.PHONE_HOST or config.PHONE_IP
    user = user or config.SSH_USER
    port = port or config.SSH_PORT
    password = password or config.SSH_PASSWORD

    log.info("Connexion SSH %s@%s:%d ...", user, host, port)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=10)
    try:
        yield client
    finally:
        client.close()


def run(client: paramiko.SSHClient, cmd: str) -> tuple[int, str, str]:
    """Exécute une commande SSH, retourne (exit_code, stdout, stderr)."""
    _, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    if out:
        log.debug("[ssh] %s", out)
    if err:
        log.debug("[ssh:err] %s", err)
    return code, out, err


def upload(client: paramiko.SSHClient, local: str | Path, remote: str) -> None:
    local = Path(local)
    log.info("Upload %s → %s", local.name, remote)
    sftp = client.open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()


def upload_dir(client: paramiko.SSHClient, local_dir: str | Path,
               remote_dir: str) -> None:
    """Upload récursif d'un dossier (création des sous-dossiers)."""
    local_dir = Path(local_dir)
    sftp = client.open_sftp()
    try:
        _mkdir_p(sftp, remote_dir)
        for src in local_dir.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(local_dir).as_posix()
            dst = f"{remote_dir}/{rel}"
            _mkdir_p(sftp, dst.rsplit("/", 1)[0])
            sftp.put(str(src), dst)
    finally:
        sftp.close()


def _mkdir_p(sftp, path: str) -> None:
    parts, current = path.strip("/").split("/"), ""
    for part in parts:
        current = f"{current}/{part}" if current else f"/{part}"
        try:
            sftp.stat(current)
        except IOError:
            sftp.mkdir(current)
