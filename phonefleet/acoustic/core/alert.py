"""Envoi d'alerte SMS via Termux:API avec cooldown anti-spam.
"""

import os
import subprocess
from datetime import datetime

from core import config
from core.logging_utils import get_logger

log = get_logger("alert")

_last_alert: dict[str, datetime] = {}
_last_call: dict[str, datetime] = {}


def is_termux() -> bool:
    return os.path.exists("/data/data/com.termux")


def send_sms(phone: str, message: str, timeout: int = 15) -> bool:
    """Envoi SMS via Termux:API. Retourne True si succès."""
    if not is_termux():
        log.info("[SIMULATION SMS] %s → %s", phone, message.replace("\n", " | "))
        return True
    try:
        subprocess.run(
            ["termux-sms-send", "-n", phone, message],
            timeout=timeout, check=True
        )
        log.info("SMS envoyé à %s", phone)
        return True
    except FileNotFoundError:
        log.error("termux-sms-send introuvable — Termux:API requis")
    except subprocess.CalledProcessError as e:
        log.error("Échec envoi SMS : %s", e)
    except subprocess.TimeoutExpired:
        log.error("Timeout envoi SMS")
    return False


def maybe_send_detection_alert(result: dict,
                                site: str = config.SITE,
                                phone: str = config.ALERT_PHONE,
                                min_confidence: float = config.MIN_CONFIDENCE,
                                cooldown_minutes: int = config.COOLDOWN_MINUTES) -> bool:
    """Envoie un SMS si le résultat IA mérite une alerte (avec cooldown)."""
    if not result.get("alert"):
        return False

    conf = result.get("confidence", 0.0)
    if conf < min_confidence:
        log.info("Confiance %.0f%% < seuil %.0f%% — pas d'alerte",
                 conf * 100, min_confidence * 100)
        return False

    class_name = result.get("class_name", "?")
    now = datetime.now()
    last = _last_alert.get(class_name)
    if last and (now - last).total_seconds() < cooldown_minutes * 60:
        log.info("Cooldown actif pour '%s'", class_name)
        return False

    probs = result.get("probs_mean", {})
    top3 = sorted(probs.items(), key=lambda x: -x[1])[:3]
    top3_str = " | ".join(
        f"{k.split('(')[0].strip()}: {v:.0%}" for k, v in top3
    )

    message = (
        f"[ALERTE BIOACOUSTIQUE]\n"
        f"Site       : {site.upper()}\n"
        f"Heure      : {now.strftime('%d/%m %H:%M')}\n"
        f"Détection  : {class_name}\n"
        f"Confiance  : {conf:.0%} (cohérence {result.get('file_ratio', 0):.0%})\n"
        f"Top classes: {top3_str}\n"
        f"Fichier    : {result.get('wav_file', '?')}"
    )

    if send_sms(phone, message):
        _last_alert[class_name] = now
        return True
    return False


def make_call(phone: str, timeout: int = 15) -> bool:
    """Déclenche un appel téléphonique via Termux:API."""

    if not is_termux():
        log.info("[SIMULATION APPEL] %s", phone)
        return True

    try:
        result = subprocess.run(
            ["termux-telephony-call", phone],
            timeout=timeout,
            capture_output=True,
            text=True
        )
        log.info("CALL returncode=%s", result.returncode)
        log.info("CALL stdout=%s", result.stdout.strip())
        log.info("CALL stderr=%s", result.stderr.strip())

        if result.returncode == 0:
            log.info("Demande d'appel envoyée vers %s", phone)
            return True

        return False

    except FileNotFoundError:
        log.error("termux-telephony-call introuvable — Termux:API requis")

    except subprocess.CalledProcessError as e:
        log.error("Échec appel : %s", e)

    except subprocess.TimeoutExpired:
        log.error("Timeout appel")

    return False

def maybe_call_alert(result: dict,
                      phone: str = config.ALERT_PHONE,
                      min_confidence: float = config.CALL_MIN_CONFIDENCE,
                      cooldown_minutes: int = config.CALL_COOLDOWN_MINUTES) -> bool:
    """Déclenche un appel si le résultat IA dépasse le seuil dédié (profil ALLO_BRUIT).'
    Seuil et cooldown VOLONTAIREMENT séparés de ceux du SMS (voir
    config.CALL_MIN_CONFIDENCE / CALL_COOLDOWN_MINUTES) : un appel est plus
    intrusif qu'un SMS, donc réservé aux détections de très forte confiance,
    avec un anti-spam plus long.
    """
    if not result.get("alert"):
        return False

    conf = result.get("confidence", 0.0)
    if conf < min_confidence:
        return False

    class_name = result.get("class_name", "?")
    now = datetime.now()
    last = _last_call.get(class_name)
    if last and (now - last).total_seconds() < cooldown_minutes * 60:
        log.info("Cooldown appel actif pour '%s'", class_name)
        return False

    if make_call(phone):
        _last_call[class_name] = now
        return True
    return False


def send_battery_alert(percentage, voltage_mv, site: str = config.SITE,
                       phone: str = config.ALERT_PHONE,
                       gps: dict | None = None) -> bool:
    """Envoie une alerte batterie, avec position GPS optionnelle jointe.

    `gps` : dict au format renvoyé par android.receiver.get_gps(),
    Si `gps` vaut None (paramètre non fourni), le
    message est envoyé sans mention de position.
    Si `gps` est fourni mais sans coordonnées exploitables,
    le message le signale explicitement plutôt que de rester silencieux.
    """
    msg = f"[{site.upper()}] Batterie faible : {percentage}% ({voltage_mv} mV)"

    lat = gps.get("latitude") if gps else None
    lon = gps.get("longitude") if gps else None
    if lat is not None and lon is not None:
        msg += f"\nPosition : https://maps.google.com/?q={lat},{lon}"
    elif gps is not None:
        msg += "\nPosition : indisponible (GPS/réseau)"

    return send_sms(phone, msg)