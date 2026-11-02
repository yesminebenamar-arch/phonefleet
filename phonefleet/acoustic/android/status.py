"""Statut d'autonomie du déploiement — commande INDÉPENDANTE.

À lancer À TOUT MOMENT sur le téléphone, y compris pendant que receiver.py
tourne en arrière-plan (lecture seule, n'interrompt rien) :

    python -m android.status            # affiche MEMORY_LIMIT / BATTERY_LIMIT
    python -m android.status --start    # (re)marque le début de mission puis affiche
    python -m android.status --reset     # réinitialise le début de mission

Affiche :
    - MEMORY_LIMIT  : jours de stockage restants
    - BATTERY_LIMIT : jours d'autonomie batterie (ou "no" si sur secteur)
    - date/heure conseillée de récupération de l'appareil
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import autonomy


def main() -> None:
    parser = argparse.ArgumentParser(description="Statut d'autonomie du déploiement")
    parser.add_argument("--start", action="store_true",
                        help="Marque le début de mission (idempotent) avant d'afficher")
    parser.add_argument("--reset", action="store_true",
                        help="Réinitialise le début de mission (nouveau départ)")
    args = parser.parse_args()

    if args.reset:
        autonomy.start_mission(reset=True)
        print(f"Mission réinitialisée : {autonomy.mission_state_path()}")
    elif args.start:
        state = autonomy.start_mission()
        print(f"Début de mission : {state.get('start_iso', '?')} "
              f"(batterie {state.get('start_pct', '?')}%)")

    print(autonomy.format_summary())


if __name__ == "__main__":
    main()
