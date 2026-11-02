"""Configuration interactive DANS Termux.

Reprend config.setup_interactive() (site + piézo) et l'expose directement sur le téléphone, plus le
numéro d'alerte SMS s'il n'est pas encore renseigné. Tout est persisté dans .env
(source unique de vérité) via config.update_env().

    python -m android.setup            # ne demande que ce qui manque
    python -m android.setup --force    # re-demande tout
"""
import re
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config


def prompt_deployment_config() -> None:
    """Prompt inline simplifié : site, piézo, téléphone — avant chaque déploiement.
    Affiche les valeurs actuelles entre crochets.
    L'utilisateur appuie sur entrée pour conserver, ou saisit une nouvelle valeur. 
    Le numéro de téléphone est validé (format français).
    """
    print("\n=== Configuration du déploiement ===")
    updates = {}

    # ── Site ──
    current_site = config.SITE
    new_site = input(f"Site actuel [{current_site}] : ").strip()
    if new_site:
        updates["SITE"] = config._slugify(new_site)

    # ── Piézo ──
    current_piezo = config.PIEZO_MODEL
    new_piezo = input(f"Piézo actuel [{current_piezo}] : ").strip()
    if new_piezo:
        updates["PIEZO_MODEL"] = new_piezo

    # ── Numéro SMS ──
    current_phone = config.ALERT_PHONE
    while True:
        new_phone = input(f"Numéro SMS [{current_phone}] : ").strip()
        if not new_phone:
            # conserver la valeur actuelle
            break
        cleaned = re.sub(r"[^\d+]", "", new_phone)
        if re.fullmatch(r"(0[67]\d{8}|\+33[67]\d{8})", cleaned):
            updates["ALERT_PHONE"] = cleaned
            break
        print(" Numéro invalide. Format attendu : 06xxxxxxxx, "
              "07xxxxxxxx, +336xxxxxxxx")

    if updates:
        config.update_env(updates)
    print(f"✓ Configuration : site={config.SITE}, piézo={config.PIEZO_MODEL}, "
          f"tel={config.ALERT_PHONE}\n")


def prompt_alert_phone(force: bool = False) -> None:
    """Demande le numéro destinataire des SMS et vérifie son format. """
    current = config.ALERT_PHONE

    if not force and current and current != "+33XXXXXXXXX":
        return

    while True:
        saisi = input(f"  Numéro d'alerte SMS [{current}] : ").strip()

        # Conserver la valeur actuelle si l'utilisateur appuie simplement sur Entrée
        if not saisi:
            saisi = current

        # Supprime les espaces, tirets, parenthèses...
        saisi = re.sub(r"[^\d+]", "", saisi)

        # Vérifie un numéro français :
        # - 06xxxxxxxx
        # - 07xxxxxxxx
        # - +336xxxxxxxx
        # - +337xxxxxxxx
        #Les crochets signifient "un seul caractère parmi ceux-ci" 
        #\d signifie un chiffre (0 à 9) 
        # {8} Cela signifie : répéter 8 fois
        if re.fullmatch(r"(0[67]\d{8}|\+33[67]\d{8})", saisi):
            config.update_env({"ALERT_PHONE": saisi})
            print(f"✓ Numéro enregistré : {saisi}")
            return

        print(" Numéro invalide.")
        print("   Veuillez réessayer.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configuration interactive (Termux)")
    parser.add_argument("--force", action="store_true",
                        help="Re-demander site, piézo et numéro même s'ils sont renseignés")
    args = parser.parse_args()

    if args.force:
        # Mode forcé = prompt inline unifié (site + piézo + téléphone)
        prompt_deployment_config()
    else:
        # Mode classique = ne demande que ce qui manque (menu site + piézo + tel)
        print("=== Configuration du déploiement (Termux) ===")
        config.setup_interactive(force=False)
        prompt_alert_phone(force=False)

    print(f"Profil courant : {config.PROFILE}  (site={config.SITE}, "
          f"piézo={config.PIEZO_MODEL}, alerte={config.ALERT_PHONE})")
    print("Prêt. Lancez un profil, ex. : ./termux/start_deployment_ALERTE.sh\n")


if __name__ == "__main__":
    main()
