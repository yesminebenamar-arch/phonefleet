"""Statut condensé et lisible du système BIOFISH — pensé pour un usage
terrain simple (un tap = un affichage clair), plutôt qu'un flux de logs.

Usage :
    python -m android.pretty_status
"""
import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core import autonomy


def is_running() -> bool:
    """Vrai si android.receiver tourne actuellement (peu importe qui l'a lancé)."""
    try:
        out = subprocess.check_output(["pgrep", "-f", "android.receiver"])
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def current_profile() -> str:
    """Lit le dernier profil mémorisé par deploy_menu.sh, sinon celui du .env."""
    profile_file = Path(config.TERMUX_HOME) / ".pfe_last_profile"
    if profile_file.exists():
        val = profile_file.read_text().strip()
        if val:
            return val
    return config.PROFILE


def last_cycle_row() -> dict | None:
    """Dernière ligne de cycle_log.csv pour le site/jour courant, si elle existe."""
    now = datetime.now()
    day_dir = (Path(config.TERMUX_DATA) / config.SITE
               / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d"))
    csv_path = day_dir / "cycle_log.csv"
    if not csv_path.exists():
        return None
    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None


def format_timestamp(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return ts or "N/A"


def format_confidence(conf) -> str:
    try:
        return f"{float(conf) * 100:.0f}%"
    except (TypeError, ValueError):
        return "N/A"


def main() -> None:
    running = is_running()
    profile = current_profile()
    row = last_cycle_row()

    print("=== BIOFISH STATUS ===")
    print(f"État          : {'EN COURS' if running else 'ARRÊTÉ'}")
    print(f"Profil        : {profile}")
    print(f"Site          : {config.SITE}")

    if row:
        print(f"Cycle         : {row.get('cycle', '?')}")
        print(f"Dernier enr.  : {format_timestamp(row.get('timestamp', ''))}")
        pct = row.get("bat_pct", "?")
        mv = row.get("bat_voltage_mv", "?")
        temp = row.get("bat_temp", "?")
        print(f"Batterie      : {pct}% ({mv} mV, {temp}°C)")
        detection = row.get("detection_class") or "N/A"
        print(f"Analyse       : {detection}")
        print(f"Confiance     : {format_confidence(row.get('detection_conf'))}")
    else:
        print("Cycle         : aucun enregistrement aujourd'hui pour ce site")

    print("")
    for line in autonomy.format_summary().splitlines():
        print(line)


if __name__ == "__main__":
    main()