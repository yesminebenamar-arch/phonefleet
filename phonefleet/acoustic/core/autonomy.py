"""Estimation d'autonomie du déploiement : stockage et batterie 

Deux indicateurs :
    - MEMORY_LIMIT : nombre de jours avant saturation du stockage, déduit de
      l'espace disque libre, de la taille d'un cycle d'enregistrement (durée,
      fréquence, WAV 16 bits mono) et du nombre de cycles par jour.
    - BATTERY_LIMIT : nombre de jours avant batterie vide. Si le téléphone est
      en charge / sur secteur → None (illimité, affiché "no"). Sinon estimation
      HYBRIDE : conso calibrée (config.BATTERY_DRAIN_PCT_PER_DAY) au démarrage,
      puis bascule sur le taux de décharge réellement observé depuis le début de
      la mission dès qu'on a assez de recul (voir OBSERVE_MIN_HOURS/PCT).

 dépendances **stdlib uniquement** (pas de numpy) :
utilisable sur Termux comme sur PC. Sur le téléphone il lit termux-battery-status 
"""

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from core import config

# ── Constantes de calcul ─────────────────────────────────────────────────────
WAV_HEADER_BYTES = 44          # en-tête WAV PCM canonique
WAV_BITS = 16                  # termux-microphone-record -e wav → PCM 16 bits
WAV_CHANNELS = 1               # -c 1 (mono)
META_OVERHEAD_BYTES = 600      # .txt de métadonnées + ligne CSV par cycle (approx.)

# Bascule calibré → observé : on n'utilise le taux observé qu'après un minimum
# de temps ET une baisse minimale, pour éviter le bruit des premières minutes.
OBSERVE_MIN_HOURS = 2.0
OBSERVE_MIN_DROP_PCT = 3.0

_CHARGING_STATES = {"CHARGING", "FULL"}


# ── Emplacement du fichier d'état de mission 
def _state_dir() -> Path:
    """~ sur Termux (si présent), sinon racine du repo (PC / dev)."""
    termux_home = Path(config.TERMUX_HOME)
    return termux_home if termux_home.exists() else config.REPO_ROOT


def mission_state_path() -> Path:
    return _state_dir() / ".pfe_mission.json"


def data_dir() -> Path:
    """Dossier où sont écrits les enregistrements (mesure de l'espace disque)."""
    termux_data = Path(config.TERMUX_DATA)
    return termux_data if termux_data.exists() else config.REPO_ROOT


# ── Stockage : MEMORY_LIMIT 
def bytes_per_cycle(record_duration: int | None = None,
                    sample_rate: int | None = None) -> int:
    """Taille disque approximative d'un cycle (WAV + métadonnées)."""
    record_duration = record_duration if record_duration is not None else config.RECORD_DURATION
    sample_rate = sample_rate if sample_rate is not None else config.SAMPLE_RATE
    wav = WAV_HEADER_BYTES + sample_rate * record_duration * WAV_CHANNELS * WAV_BITS // 8
    return wav + META_OVERHEAD_BYTES


def cycles_per_day(record_duration: int | None = None,
                   sleep_duration: int | None = None) -> float:
    record_duration = record_duration if record_duration is not None else config.RECORD_DURATION
    sleep_duration = sleep_duration if sleep_duration is not None else config.SLEEP_DURATION
    period = max(record_duration + sleep_duration, 1)
    return 86400.0 / period


def disk_free_bytes(path: Path | None = None) -> int:
    path = path or data_dir()
    try:
        return shutil.disk_usage(str(path)).free
    except OSError:
        return 0


def memory_limit_days(path: Path | None = None) -> float:
    """Jours de stockage restants au rythme d'enregistrement courant."""
    per_day = bytes_per_cycle() * cycles_per_day()
    if per_day <= 0:
        return float("inf")
    return disk_free_bytes(path) / per_day


# ── Batterie : BATTERY_LIMIT 
def battery_status() -> dict:
    """Lit termux-battery-status (JSON). Hors Termux → dict vide."""
    try:
        out = subprocess.check_output(["termux-battery-status"], timeout=15)
        return json.loads(out)
    except Exception:
        return {}


def is_charging(battery: dict) -> bool:
    """Vrai si le téléphone est sur secteur / en charge (BATTERY_LIMIT = no)."""
    status = str(battery.get("status", "")).upper()
    if status in _CHARGING_STATES:
        return True
    plugged = str(battery.get("plugged", "")).upper()
    return plugged not in ("", "UNPLUGGED", "NONE", "0", "FALSE")


def start_mission(battery: dict | None = None, *, reset: bool = False) -> dict:
    """Enregistre (une seule fois) le début de mission : horodatage + batterie %.
    Idempotent : ne réécrit pas l'état s'il existe déjà (sauf reset=True), pour
    que le taux de décharge observé se calcule bien depuis le VRAI départ.
    """
    path = mission_state_path()
    if path.exists() and not reset:
        return load_mission()
    if battery is None:
        battery = battery_status()
    state = {
        "start_iso": datetime.now().isoformat(timespec="seconds"),
        "start_pct": battery.get("percentage"),
        "profile": config.PROFILE,
        "site": config.SITE,
    }
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass
    return state


def load_mission() -> dict:
    try:
        return json.loads(mission_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def observed_drain_pct_per_day(now_pct: float, now: datetime | None = None) -> float | None:
    """Taux de décharge observé depuis le début de mission (%/jour), ou None.

    Renvoie None tant qu'on n'a pas assez de recul (temps et baisse minimaux).
    """
    state = load_mission()
    start_iso = state.get("start_iso")
    start_pct = state.get("start_pct")
    if start_iso is None or start_pct is None:
        return None
    try:
        start_time = datetime.fromisoformat(start_iso)
        start_pct = float(start_pct)
    except (ValueError, TypeError):
        return None

    now = now or datetime.now()
    #86400 nombre de secondes par jour 
    elapsed_days = (now - start_time).total_seconds() / 86400.0 
    drop = start_pct - float(now_pct)
    if elapsed_days * 24 < OBSERVE_MIN_HOURS or drop < OBSERVE_MIN_DROP_PCT:
        return None
    if elapsed_days <= 0:
        return None
    return drop / elapsed_days


def battery_limit_days(battery: dict | None = None,
                       now: datetime | None = None) -> tuple[float | None, str]:
    """Jours d'autonomie batterie restants + source de l'estimation.

    Retourne (jours, source) où source ∈ {"charging", "observé", "calibré"}.
    jours = None si en charge (illimité).
    """
    if battery is None:
        battery = battery_status()
    if is_charging(battery):
        return None, "charging"

    pct = battery.get("percentage")
    if not isinstance(pct, (int, float)):
        # Pas de lecture batterie (hors Termux) → estimation calibrée sur 100 %.
        pct = 100.0

    observed = observed_drain_pct_per_day(pct, now=now)
    if observed and observed > 0:
        return float(pct) / observed, "observé"
    drain = max(config.BATTERY_DRAIN_PCT_PER_DAY, 0.1)
    return float(pct) / drain, "calibré"


# ── Synthèse ─────────────────────────────────────────────────────────────────
def _fmt_days(days: float | None) -> str:
    if days is None:
        return "no (sur secteur / en charge)"
    if days == float("inf"):
        return "illimite"
    if days >= 1:
        return f"{days:.1f} j"
    return f"{days * 24:.1f} h"


def summary(now: datetime | None = None) -> dict:
    """Calcule tous les indicateurs d'autonomie en une passe (pour affichage/log)."""
    now = now or datetime.now()
    battery = battery_status()

    mem_days = memory_limit_days()
    bat_days, bat_source = battery_limit_days(battery, now=now)

    # Date de récupération = min des deux contraintes (mémoire, batterie).
    limits = [d for d in (mem_days, bat_days) if d is not None and d != float("inf")]
    recovery = None
    binding = None
    if limits:
        limiting_days = min(limits)
        recovery = now + timedelta(days=limiting_days)
        binding = "batterie" if (bat_days is not None and limiting_days == bat_days) else "mémoire"

    return {
        "now": now,
        "memory_limit_days": mem_days,
        "battery_limit_days": bat_days,
        "battery_source": bat_source,
        "battery_pct": battery.get("percentage"),
        "battery_status": battery.get("status"),
        "recovery": recovery,
        "binding": binding,
        "free_gb": disk_free_bytes() / 1e9,
        "bytes_per_cycle": bytes_per_cycle(),
        "cycles_per_day": cycles_per_day(),
    }


def format_cycle_limits(now: datetime | None = None) -> str:
    """MEMORY_LIMIT / BATTERY_LIMIT en format compact (affiché avant chaque cycle).

    Appelé à chaque itération de receiver.py, juste avant record_audio().
    BATTERY_LIMIT = "no" si le téléphone est en charge / sur secteur.
    """
    now = now or datetime.now()
    battery = battery_status()
    mem_days = memory_limit_days()

    if mem_days == float("inf"):
        mem_str = "illimite"
    elif mem_days >= 1:
        mem_str = f"{mem_days:.1f} jours"
    else:
        mem_str = f"{mem_days * 24:.1f} heures"

    if is_charging(battery):
        bat_str = "no"
    else:
        bat_days, _ = battery_limit_days(battery, now=now)
        if bat_days is None:
            bat_str = "no"
        elif bat_days >= 1:
            bat_str = f"{bat_days:.1f} jours"
        else:
            bat_str = f"{bat_days * 24:.1f} heures"

    return f"MEMORY_LIMIT  = {mem_str}\nBATTERY_LIMIT = {bat_str}"


def format_summary(s: dict | None = None) -> str:
    """Rend la synthèse sous forme de texte lisible (console Termux / log)."""
    s = s or summary()
    lines = [
        "-------- Autonomie du deploiement --------",
        f"  MEMORY_LIMIT  = {_fmt_days(s['memory_limit_days'])}"
        f"   (disque libre {s['free_gb']:.1f} Go, "
        f"{s['cycles_per_day']:.0f} cycles/j, "
        f"{s['bytes_per_cycle'] / 1e6:.1f} Mo/cycle)",
    ]
    bat = _fmt_days(s["battery_limit_days"])
    if s["battery_limit_days"] is not None:
        pct = s["battery_pct"]
        pct_str = f"{pct}%" if isinstance(pct, (int, float)) else "?% (hors Termux)"
        bat += f"   (batterie {pct_str}, estimation {s['battery_source']})"
    lines.append(f"  BATTERY_LIMIT = {bat}")
    if s["recovery"] is not None:
        lines.append(
            f"  -> Recuperer l'appareil avant : "
            f"{s['recovery'].strftime('%d/%m %H:%M')} "
            f"(contrainte : {s['binding']})"
        )
    lines.append("------------------------------------------")
    return "\n".join(lines)
