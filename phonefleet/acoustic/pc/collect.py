"""
Collecte SFTP des enregistrements BIOFISH depuis le Fairphone.
Version production (corrigée) :
- Site unique : banyuls
- Téléchargement sécurisé WAV/TXT
- Vérification taille distante/local
- Protection contre fichiers incomplets
- Filtre de date --depuis (ignore tout ce qui est antérieur à une date donnée)

CORRECTIF (30/07) : file_is_stable() n'avale plus les erreurs réseau en
silence. Avant, toute exception (timeout SSH, coupure Tailscale, etc.)
pendant la vérification de stabilité était traitée exactement comme un
fichier "encore en écriture" -> un message trompeur pour des centaines de
fichiers vieux de plusieurs jours, qui ne pouvaient objectivement pas être
en cours d'enregistrement. Maintenant :
  - la vraie erreur réseau est loggée explicitement
  - une deuxième tentative est faite avant d'abandonner le fichier pour
    cette passe (pour absorber un simple aléa réseau ponctuel)
  - un résumé de fin de passe distingue clairement :
      téléchargés / vraiment en écriture / erreurs réseau / autres échecs

AJOUT (30/07) : argument --depuis AAAA-MM-JJ[THH:MM] pour ne parcourir/
télécharger que les fichiers à partir de cette date (et heure optionnelle,
inclus). Utile pour reprendre la collecte à partir du 20 juillet sans
retélécharger ou recompter les données antérieures (ex. avant le
déploiement du correctif persistence_tracker.py).
  - Le tri par JOUR (dossier YYYY/MM/DD) élimine d'abord les journées
    entières hors périmètre, sans même les lister côté serveur.
  - Le tri par HEURE (si précisée) se fait ensuite uniquement sur le
    jour-frontière, via l'horodatage réel du fichier côté serveur
    (sftp.stat().st_mtime) — pas de dépendance à un format de nom de
    fichier particulier.
"""

import argparse
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.logging_utils import get_logger
from pc import ssh_client


log = get_logger("collect")

POLL_EVERY_S = 30
SITE = "banyuls"

# Date minimale par défaut (peut être surchargée par --depuis)
DEPUIS_PAR_DEFAUT = None  # ex: date(2026, 7, 20)


def remote_data_root() -> str:
    return config.TERMUX_DATA


def local_root() -> Path:
    p = Path(config.OUTPUT_FOLDER)
    p.mkdir(parents=True, exist_ok=True)
    return p


def already_local() -> set[str]:
    """Retourne les fichiers déjà présents et valides (ignore les 0 octet)."""
    result = set()
    for p in local_root().rglob("*"):
        if p.is_file():
            try:
                if p.stat().st_size > 0:
                    result.add(p.relative_to(local_root()).as_posix())
            except Exception:
                pass
    return result


def _parse_depuis(valeur: str) -> datetime:
    """Parse l'argument --depuis. Accepte deux formats :
      - AAAA-MM-JJ            -> équivaut à minuit ce jour-là (00:00)
      - AAAA-MM-JJTHH:MM      -> date ET heure précises
    Ex: --depuis 2026-07-20  ou  --depuis 2026-07-20T14:30
    """
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(valeur, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Date/heure invalide '{valeur}'. Formats acceptés : "
        "AAAA-MM-JJ (ex: 2026-07-20) ou AAAA-MM-JJTHH:MM (ex: 2026-07-20T14:30)"
    )


def _jour_valide(annee: str, mois: str, jour: str, depuis: datetime | None) -> bool:
    """Vérifie que le dossier YYYY/MM/DD correspond à un jour >= depuis.date().
    Filtre GROSSIER (élimine des journées entières sans lister leur contenu).
    Le filtre fin sur l'heure se fait ensuite dans _fichier_apres_depuis().
    Si le nom de dossier n'est pas un nombre valide ou si depuis est None,
    on n'exclut rien (comportement historique)."""
    if depuis is None:
        return True
    try:
        d = date(int(annee), int(mois), int(jour))
    except (ValueError, TypeError):
        # Nom de dossier non standard : on ne filtre pas, on laisse passer
        # plutôt que de risquer de perdre des données silencieusement.
        return True
    return d >= depuis.date()


def _fichier_apres_depuis(sftp, remote_path: str, depuis: datetime | None) -> bool:
    """Filtre FIN sur l'heure : ne s'applique que si depuis a une heure non
    nulle (00:00 minuit = pas besoin, le filtre par jour suffit déjà).
    Compare l'horodatage réel du fichier côté serveur (mtime) à depuis.
    En cas d'erreur réseau sur le stat, on laisse passer le fichier plutôt
    que de le perdre silencieusement (le pipeline habituel le retriera de
    toute façon lors du téléchargement)."""
    if depuis is None or (depuis.hour == 0 and depuis.minute == 0):
        return True
    try:
        mtime = sftp.stat(remote_path).st_mtime
        return datetime.fromtimestamp(mtime) >= depuis
    except Exception as e:
        log.warning("Impossible de vérifier l'horodatage de %s (%s), "
                    "fichier conservé par précaution", remote_path, e)
        return True


def list_remote_tree(sftp, depuis: date | None = None) -> dict[str, str]:
    """Parcourt uniquement /data/.../banyuls/YYYY/MM/DD/.
    Si depuis est fourni, ignore les dossiers de jour antérieurs à cette
    date (comparaison sur la date réelle, pas sur le tri alphabétique)."""
    tree = {}
    root = f"{remote_data_root()}/{SITE}"

    try:
        years = sftp.listdir(root)
    except Exception as e:
        log.error("Impossible accès %s : %s", root, e)
        return {}

    for year in years:
        yp = f"{root}/{year}"
        try:
            months = sftp.listdir(yp)
        except Exception:
            continue

        for month in months:
            mp = f"{yp}/{month}"
            try:
                days = sftp.listdir(mp)
            except Exception:
                continue

            for day in days:
                if not _jour_valide(year, month, day, depuis):
                    continue

                dp = f"{mp}/{day}"
                try:
                    files = sftp.listdir(dp)
                except Exception:
                    continue

                for name in files:
                    rel = f"{SITE}/{year}/{month}/{day}/{name}"
                    tree[rel] = f"{dp}/{name}"

    return tree


# ─────────────────────────────────────────────────────────────────────────
# CORRECTIF PRINCIPAL : on distingue maintenant 3 résultats possibles,
# au lieu de tout confondre sous "False" :
#   "stable"       -> la taille n'a pas changé, fichier prêt à télécharger
#   "en_ecriture"  -> la taille a réellement changé entre les deux stat()
#   "erreur"       -> une exception réseau est survenue (PAS un fichier
#                      en cours d'écriture, un vrai problème de connexion)
# ─────────────────────────────────────────────────────────────────────────

def verifier_stabilite(sftp, remote_path: str, tentatives: int = 2) -> str:
    """Vérifie si la taille distante est stable. Retourne 'stable',
    'en_ecriture' ou 'erreur'. Réessaie une fois en cas d'erreur réseau
    avant de conclure à une vraie erreur (absorbe les aléas ponctuels).
    """
    for tentative in range(1, tentatives + 1):
        try:
            s1 = sftp.stat(remote_path).st_size
            time.sleep(2)
            s2 = sftp.stat(remote_path).st_size
            return "stable" if s1 == s2 else "en_ecriture"
        except Exception as e:
            if tentative < tentatives:
                log.warning("Erreur réseau sur %s (tentative %d/%d), "
                            "on réessaie : %s", remote_path, tentative,
                            tentatives, e)
                time.sleep(1)
                continue
            log.error("Erreur réseau persistante sur %s après %d tentatives : %s",
                       remote_path, tentatives, e)
            return "erreur"
    return "erreur"


def safe_download(sftp, remote_path, local_path) -> bool:
    """Téléchargement sécurisé : fichier temporaire, comparaison taille,
    validation finale."""
    try:
        remote_size = sftp.stat(remote_path).st_size

        if remote_size <= 0:
            log.warning("Fichier vide ignoré : %s", remote_path)
            return False

        tmp = local_path.with_suffix(local_path.suffix + ".part")
        tmp.unlink(missing_ok=True)

        sftp.get(remote_path, str(tmp))
        local_size = tmp.stat().st_size

        if local_size != remote_size:
            log.error("Erreur taille %s distant=%d local=%d",
                       remote_path, remote_size, local_size)
            tmp.unlink(missing_ok=True)
            return False

        tmp.rename(local_path)
        return True

    except Exception as e:
        log.error("Erreur transfert %s : %s", remote_path, e)
        return False


def fetch_new(sftp, known: set[str], depuis: datetime | None = None) -> tuple[list[str], dict[str, int]]:
    """Télécharge les nouveaux fichiers. Retourne (liste des nouveaux,
    compteur de statistiques pour le résumé de fin de passe)."""
    tree = list_remote_tree(sftp, depuis=depuis)
    new: list[str] = []
    stats = {"telecharges": 0, "en_ecriture": 0, "erreurs_reseau": 0,
              "txt_manquant": 0, "echec_transfert": 0, "avant_heure_depuis": 0}

    wavs = {k: v for k, v in tree.items() if k.endswith(".wav")}
    # Le "jour-frontière" est le seul où un filtre horaire fin peut exclure
    # des fichiers (les jours strictement après --depuis sont déjà entièrement
    # valides grâce au filtre par dossier dans list_remote_tree).
    jour_frontiere = depuis.strftime("%Y/%m/%d") if depuis else None

    for rel_wav, remote_wav in sorted(wavs.items()):
        if rel_wav in known:
            continue

        if jour_frontiere and f"/{jour_frontiere}/" in f"/{rel_wav}":
            if not _fichier_apres_depuis(sftp, remote_wav, depuis):
                stats["avant_heure_depuis"] += 1
                continue

        statut = verifier_stabilite(sftp, remote_wav)

        if statut == "en_ecriture":
            log.info("Encore en écriture : %s", rel_wav)
            stats["en_ecriture"] += 1
            continue

        if statut == "erreur":
            # On ne log PAS "encore en écriture" ici : c'est une vraie
            # erreur réseau, distincte, comptée à part.
            stats["erreurs_reseau"] += 1
            continue

        rel_txt = rel_wav.replace(".wav", ".txt")
        if rel_txt not in tree:
            log.warning("TXT manquant : %s", rel_wav)
            stats["txt_manquant"] += 1
            continue

        local_wav = local_root() / rel_wav
        local_txt = local_root() / rel_txt
        local_wav.parent.mkdir(parents=True, exist_ok=True)

        if not safe_download(sftp, remote_wav, local_wav):
            stats["echec_transfert"] += 1
            continue

        if not safe_download(sftp, tree[rel_txt], local_txt):
            local_wav.unlink(missing_ok=True)
            stats["echec_transfert"] += 1
            continue

        log.info("✓ %s (%d o)", rel_wav, local_wav.stat().st_size)
        new.extend([rel_wav, rel_txt])
        stats["telecharges"] += 1

        analyse_dir = str(local_wav).removesuffix(".wav") + "_analyse"
        subprocess.Popen(
            [sys.executable, "-m", "pc.analyze", "--wav", str(local_wav),
             "--out", analyse_dir],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    return new, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=POLL_EVERY_S)
    parser.add_argument(
        "--depuis", type=_parse_depuis, default=DEPUIS_PAR_DEFAUT,
        help="Ne collecter que les fichiers à partir de cette date/heure. "
             "Formats : AAAA-MM-JJ (ex: 2026-07-20) ou AAAA-MM-JJTHH:MM "
             "(ex: 2026-07-20T14:30)",
    )
    args = parser.parse_args()

    log.info("=== COLLECTE BIOFISH ===")
    log.info("Source : %s/%s", remote_data_root(), SITE)
    log.info("Destination : %s", local_root())
    if args.depuis:
        log.info("Filtre de date/heure actif : à partir du %s",
                  args.depuis.strftime("%Y-%m-%d %H:%M"))

    with ssh_client.connect() as ssh:
        sftp = ssh.open_sftp()
        try:
            log.info("Site détecté : %s", SITE)
            known = already_local()
            log.info("Fichiers locaux valides : %d", len(known))

            while True:
                log.info("[%s] Vérification...",
                         datetime.now().strftime("%H:%M:%S"))
                new, stats = fetch_new(sftp, known, depuis=args.depuis)
                known.update(new)
                n_new = sum(1 for x in new if x.endswith(".wav"))

                # ── Résumé clair de fin de passe ──
                log.info(
                    "Résumé passe : %d téléchargé(s), %d encore en écriture, "
                    "%d erreur(s) réseau, %d txt manquant(s), %d échec(s) transfert, "
                    "%d avant l'heure --depuis",
                    stats["telecharges"], stats["en_ecriture"],
                    stats["erreurs_reseau"], stats["txt_manquant"],
                    stats["echec_transfert"], stats["avant_heure_depuis"],
                )
                if stats["erreurs_reseau"] > 0:
                    log.warning(
                        "%d fichier(s) ignoré(s) à cause d'une erreur réseau "
                        "(pas un vrai problème d'écriture) — relance une "
                        "nouvelle passe pour les récupérer.",
                        stats["erreurs_reseau"],
                    )

                if n_new == 0 and stats["erreurs_reseau"] == 0:
                    log.info("Rien de nouveau")

                if args.once:
                    break
                time.sleep(args.interval)
        finally:
            sftp.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Arrêt utilisateur")