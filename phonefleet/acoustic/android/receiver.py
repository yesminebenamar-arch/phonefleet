"""Boucle d'enregistrement sur le Fairphone (Termux).

Pour chaque cycle :
    1. Lit la position GPS
    2. Enregistre N secondes d'audio dans /data/.../site/YYYY/MM/DD/log_*.wav
    3. Lit l'état batterie (%, mV, °C)
    4. Lance l'analyse IA + alerte SMS si événement
    5. Écrit le fichier .txt de métadonnées
    6. Met à jour le log CSV quotidien
    7. Alerte SMS si batterie faible

Lancement :
    SITE=sete python -m android.receiver
"""
import shutil
import json
import subprocess
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

# Permettre l'import du core depuis n'importe où via PYTHONPATH=$REPO
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core import alert
from core import autonomy
from core import metadata
from core.detector import detect
from core.logging_utils import get_logger

log = get_logger("receiver")

BASE_DIR = Path(config.TERMUX_DATA)
ALERT_FLAG = Path(config.TERMUX_HOME) / ".battery_alert_sent"
# Pose par termux/stop.sh AVANT le SIGINT : verifie ici en plus (defense en
# profondeur, independante du superviseur bash) pour sortir proprement des
# le debut du cycle courant si un arret volontaire a ete demande.
STOP_FLAG = Path(config.TERMUX_HOME) / ".pfe_stop_requested"



def day_dir() -> Path:
    """Retourne (et crée) le dossier site/YYYY/MM/DD du jour courant."""
    now = datetime.now()
    p = BASE_DIR / config.SITE / now.strftime("%Y") / now.strftime("%m") / now.strftime("%d")
    p.mkdir(parents=True, exist_ok=True)
    return p


def termux_json(cmd: list[str], timeout: int = 15) -> dict:
    """Exécute une commande Termux:API qui renvoie du JSON."""
    try:
        return json.loads(subprocess.check_output(cmd, timeout=timeout))
    except Exception as e:
        return {"error": str(e)}


def get_battery() -> dict:
    return termux_json(["termux-battery-status"])


def get_gps() -> dict:
    return termux_json(["termux-location", "-p", "network"])


def record_audio(wav_path: Path, duration: int, rate: int) -> bool:
    """Enregistre en format natif Termux (AAC/M4A) puis convertit en WAV PCM via ffmpeg.

    Pourquoi : termux-microphone-record ignore -e wav et produit toujours du MP4/AAC
    (signature b'\x00\x00\x00\x18ftypmp42'). scipy.io.wavfile ne peut pas lire ce
    format (ValueError: File format not understood). La conversion ffmpeg produit un
    vrai WAV PCM s16le lisible par scipy.

    `rate` : fréquence d'échantillonnage native (config.SAMPLE_RATE = 44100 Hz
    par défaut). Le rééchantillonnage vers 16 kHz (audio.TARGET_SR) pour le MEL
    se fait plus tard, côté core/audio.py — on enregistre bien en 44.1 kHz ici.
    """
    tmp_path = wav_path.with_suffix(".tmp.m4a")

    # Arrêt défensif : si un enregistrement précédent est resté actif (crash,
    # test manuel oublié, cycle précédent mal terminé), "-f <nouveau fichier>"
    # échoue silencieusement avec "Recording already in progress!" côté
    # termux-microphone-record, sans lever d'exception côté Python — le
    # fichier n'est alors jamais créé et TOUT le cycle échoue en cascade.
    subprocess.run(["termux-microphone-record", "-q"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)

    # Étape 1 — enregistrement en format natif Termux (MP4/AAC) à `rate` Hz (44100 par défaut)
    subprocess.Popen([
        "termux-microphone-record",
        "-f", str(tmp_path),
        "-r", str(rate),
        "-c", "1",
    ])
    time.sleep(duration + 1)
    subprocess.run(["termux-microphone-record", "-q"], check=False)
    time.sleep(1.5)

    if not tmp_path.exists() or tmp_path.stat().st_size < 1000:
        log.warning("Fichier source vide ou absent : %s", tmp_path.name)
        tmp_path.unlink(missing_ok=True)
        return False

    # Étape 2 — conversion en WAV PCM 16 bits, même fréquence (`rate`), via ffmpeg
    #
    # IMPORTANT : ffmpeg -y crée le fichier de sortie dès le début du traitement,
    # avant même de savoir s'il va réussir. Si la conversion échoue en cours de
    # route (stockage plein, micro occupé, permission refusée...), un wav_path
    # de 0 octet (ou tronqué) reste sur le disque avec le bon nom de fichier.
    # scipy.io.wavfile le voit ensuite comme "File format b'' not understood".
    # On nettoie donc explicitement wav_path dans TOUS les cas d'échec ci-dessous,
    # pour ne jamais laisser de fichier cassé derrière un cycle raté.
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", str(tmp_path),
            "-ar", str(rate),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(wav_path),
        ], timeout=60, check=True,
           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except Exception as e:
        stderr_msg = getattr(e, "stderr", None) or str(e)
        log.warning("Erreur conversion ffmpeg : %s", stderr_msg.strip()[:300])
        tmp_path.unlink(missing_ok=True)
        wav_path.unlink(missing_ok=True)
        return False
    finally:
        tmp_path.unlink(missing_ok=True)

    size = wav_path.stat().st_size if wav_path.exists() else 0
    if size < 1000:
        log.warning("WAV converti vide : %s (%d o)", wav_path.name, size)
        wav_path.unlink(missing_ok=True)
        return False

    # Validation structurelle du WAV : une taille correcte ne garantit pas
    # un fichier lisible (header valide mais 0 frame, troncature en cours
    # d'écriture, etc.) — on vérifie donc explicitement avec le module wave
    # avant de considérer le cycle comme réussi.
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            samplerate = wf.getframerate()
            frames = wf.getnframes()
        if frames == 0:
            raise ValueError("WAV vide (0 frame)")
        log.info("Validation WAV : channels=%s rate=%s frames=%s",
                 channels, samplerate, frames)
    except Exception as e:
        log.warning("WAV invalide après conversion : %s", e)
        wav_path.unlink(missing_ok=True)
        return False

    # Copie du fichier dans un dossier accessible depuis le téléphone (VLC)
    try:
        shared_dir = Path(config.AUDIO_FOLDER)
        shared_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(wav_path, shared_dir / wav_path.name)

        log.info("Copie vers %s", shared_dir)

    except Exception as e:
        log.warning("Impossible de copier le fichier vers le stockage partagé : %s", e)
        
    log.info("WAV OK : %s (%d o)", wav_path.name, size)
    return True


def maybe_alert(result: dict) -> dict:
    """Décide de l'envoi SMS (point 4) et de l'appel (profil ALLO_BRUIT/TOUTES_OPTIONS).

    Modèle à 4 classes (0/1/2 = bateaux, 3 = bruit de fond) : dès que
    ENABLE_SMS_DETECTION est actif (profil ALERTE et plus), toute classe
    d'alerte (voir core.model.ALERT_CLASSES) déclenche un SMS au seuil
    MIN_CONFIDENCE. L'appel (ENABLE_CALL_DETECTION, profil ALLO_BRUIT et
    plus) utilise un seuil et un cooldown séparés, plus stricts
    (config.CALL_MIN_CONFIDENCE / CALL_COOLDOWN_MINUTES).
    """
    sms_sent = False
    call_made = False
    if config.ENABLE_SMS_DETECTION:
        sms_sent = alert.maybe_send_detection_alert(result, site=config.SITE,
                                                    phone=config.ALERT_PHONE,
                                                    min_confidence=config.MIN_CONFIDENCE)
    if config.ENABLE_CALL_DETECTION:
        call_made = alert.maybe_call_alert(result, phone=config.ALERT_PHONE,
                                           min_confidence=config.CALL_MIN_CONFIDENCE,
                                           cooldown_minutes=config.CALL_COOLDOWN_MINUTES)
    return {"sms_sent": sms_sent, "call_made": call_made}


def analyse(wav_path: Path) -> dict:
    """Lance l'IA + envoie SMS si événement. Pardon les échecs (scipy peut manquer)."""
    try:
        result = detect(wav_path,
                        weights_path=config.MODEL_WEIGHTS or None,
                        conf_threshold=config.MIN_CONFIDENCE)
    except ImportError as e:
        log.warning("IA indisponible (%s) — analyse ignorée", e)
        return {}
    except Exception as e:
        log.exception("Erreur analyse : %s", e)
        return {}

    if "error" in result:
        log.warning("Analyse impossible : %s", result["error"])
        return result

    log.info("Classe=%s (%.0f%%, cohérence %.0f%%)",
             result["class_name"],
             result["confidence"] * 100,
             result["file_ratio"] * 100)

    alert_result = maybe_alert(result)
    result["sms_sent"] = alert_result["sms_sent"]
    result["call_made"] = alert_result["call_made"]
    if result["call_made"]:
        log.info("Appel déclenché (confiance %.0f%% ≥ seuil appel %.0f%%)",
                 result["confidence"] * 100, config.CALL_MIN_CONFIDENCE * 100)
    return result


def append_cycle_log(ts: str, cycle: int, battery: dict,
                     wav_ok: bool, ia: dict) -> None:
    log_csv = day_dir() / "cycle_log.csv"
    new_file = not log_csv.exists()
    with log_csv.open("a", encoding="utf-8") as f:
        if new_file:
            f.write("timestamp,site,cycle,bat_pct,bat_voltage_mv,"
                    "bat_temp,wav_ok,detection_class,detection_conf,alert_sent,call_sent\n")
        f.write(",".join(str(x) for x in [
            ts, config.SITE, cycle,
            battery.get("percentage", ""),
            battery.get("voltage", ""),
            battery.get("temperature", ""),
            int(wav_ok),
            ia.get("class_name", ""),
            ia.get("confidence", ""),
            int(bool(ia.get("sms_sent", False))),
            int(bool(ia.get("call_made", False))),
        ]) + "\n")


CRITICAL_ALERT_STATE = Path(config.TERMUX_HOME) / ".battery_critical_last_alert"


def check_battery_alert(battery: dict) -> None:
    """Deux paliers d'alerte batterie, avec des logiques volontairement différentes.

    - "Faible" (BATTERY_VOLTAGE_THRESHOLD_MV) : un seul SMS tant que ça reste
      sous le seuil, réarmé seulement si le voltage remonte. Suffisant pour
      une alerte préventive, pas la peine de spammer.
    - "Critique" (CRITICAL_BATTERY_PCT, 0-5% par défaut) : SMS RÉPÉTÉ toutes
      les CRITICAL_ALERT_COOLDOWN_MINUTES tant que le pourcentage reste sous
      le seuil, AVEC POSITION GPS jointe (voir core/alert.py::send_battery_alert).
      L'appareil pouvant s'éteindre à tout moment dans cette zone, on accepte
      le "spam" pour maximiser les chances qu'au moins un SMS passe, et on
      force une lecture GPS ici MÊME SI ENABLE_GPS est désactivé pour le
      profil courant : connaître la position juste avant extinction prime
      sur l'économie d'un appel GPS ponctuel (évènement rare en pratique).
    """
    if not config.ENABLE_SMS_BATTERY:
        return

    voltage = battery.get("voltage", 9999)
    # Termux peut renvoyer percentage sous forme de string (ex. "5") selon
    # les versions/appareils : isinstance(pct, (int, float)) échouerait
    # silencieusement dans ce cas et désactiverait l'alerte critique.
    try:
        pct = float(battery.get("percentage", 100))
    except (TypeError, ValueError):
        pct = 100

    # --- Palier "faible" (comportement existant, inchangé) ---
    if isinstance(voltage, (int, float)):
        if voltage < config.BATTERY_VOLTAGE_THRESHOLD_MV:
            log.warning("Voltage bas : %s mV", voltage)
            if not ALERT_FLAG.exists():
                if alert.send_battery_alert(pct if pct is not None else "?", voltage):
                    ALERT_FLAG.write_text("sent")
        else:
            if ALERT_FLAG.exists():
                ALERT_FLAG.unlink()
                log.info("Batterie remontée, flag d'alerte réinitialisé")

    # --- Palier "critique" (répété, avec position GPS) ---
    if pct <= config.CRITICAL_BATTERY_PCT:
        now = datetime.now()
        last = None
        if CRITICAL_ALERT_STATE.exists():
            try:
                last = datetime.fromisoformat(CRITICAL_ALERT_STATE.read_text().strip())
            except ValueError:
                last = None
        elapsed_ok = last is None or (now - last).total_seconds() >= config.CRITICAL_ALERT_COOLDOWN_MINUTES * 60
        if elapsed_ok:
            log.warning("Batterie CRITIQUE : %s%% (répétera toutes les %d min)",
                       pct, config.CRITICAL_ALERT_COOLDOWN_MINUTES)
            # Lecture GPS forcée ici, indépendamment de config.ENABLE_GPS —
            # voir docstring ci-dessus. Retry si échec : c'est probablement
            # la dernière chance de localisation avant extinction.
            gps_critical = get_gps()
            if "latitude" not in gps_critical:
                log.warning("GPS critique indisponible, nouvelle tentative")
                time.sleep(3)
                gps_critical = get_gps()
            if alert.send_battery_alert(pct, voltage, gps=gps_critical):
                CRITICAL_ALERT_STATE.write_text(now.isoformat())
    elif CRITICAL_ALERT_STATE.exists():
        CRITICAL_ALERT_STATE.unlink()
        log.info("Batterie remontée au-dessus du seuil critique, alerte répétée arrêtée")


def write_status_file(summary: dict) -> None:
    """Écrit un statut d'autonomie lisible (profil TOUTES_OPTIONS / dashboard local).

    Fichier plein-texte léger (pas de matplotlib) rafraîchi à chaque cycle,
    consultable sur le téléphone sans interrompre l'enregistrement.
    """
    try:
        path = BASE_DIR / config.SITE / "deployment_status.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(autonomy.format_summary(summary) + "\n", encoding="utf-8")
    except OSError as e:
        log.debug("Écriture statut impossible : %s", e)


def main() -> None:
    log.info("Receiver — profil=%s, site=%s, rec=%ss, sleep=%ss, fs=%s Hz",
             config.PROFILE, config.SITE, config.RECORD_DURATION,
             config.SLEEP_DURATION, config.SAMPLE_RATE)
    log.info("Modèle  : %s", config.MODEL_WEIGHTS or "poids aléatoires (non entraîné)")
    log.info("Options : SMS détection=%s, SMS batterie=%s, Appel=%s, GPS=%s, statut local=%s",
             config.ENABLE_SMS_DETECTION, config.ENABLE_SMS_BATTERY,
             config.ENABLE_CALL_DETECTION, config.ENABLE_GPS, config.ENABLE_DASHBOARD)
    if config.ENABLE_SMS_DETECTION or config.ENABLE_SMS_BATTERY:
        log.info("Alerte  : %s", config.ALERT_PHONE)
    if config.ENABLE_CALL_DETECTION:
        log.info("Appel   : %s (seuil %.0f%%, cooldown %dmin)",
                 config.ALERT_PHONE, config.CALL_MIN_CONFIDENCE * 100,
                 config.CALL_COOLDOWN_MINUTES)

    if config.SITE == "inconnu":
        log.warning("Variable SITE non définie — lancer avec SITE=sete python -m android.receiver")

    # Autonomie au démarrage (point 3) : enregistre le début de mission (idempotent)
    # et journalise MEMORY_LIMIT / BATTERY_LIMIT.
    autonomy.start_mission()
    for line in autonomy.format_summary().splitlines():
        log.info("%s", line)

    cycle = 0
    while True:
        if STOP_FLAG.exists():
            log.info("Arret volontaire detecte (.pfe_stop_requested) - sortie propre.")
            break

        cycle += 1
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d_%H-%M-%S")
        d = day_dir()
        wav_path = d / f"log_{ts}.wav"
        txt_path = d / f"log_{ts}.txt"

        log.info("--- Cycle %d (%s) ---", cycle, ts)

        # Autonomie avant chaque enregistrement (MEMORY_LIMIT / BATTERY_LIMIT)
        # BATTERY_LIMIT = no si le téléphone est en charge / sur secteur.
        for line in autonomy.format_cycle_limits().splitlines():
            log.info("%s", line)

        # Batterie lue AVANT le cycle (en plus d'après) : permet de mesurer
        # la conso réelle par cycle et de ne pas perdre cette info si le
        # téléphone s'éteint pendant l'enregistrement.
        battery_before = get_battery()

        gps = get_gps() if config.ENABLE_GPS else {}
        wav_ok = record_audio(wav_path, config.RECORD_DURATION, config.SAMPLE_RATE)
        battery = get_battery()
        log.info("Batterie : %s%% / %s mV / %s°C",
                 battery.get("percentage"),
                 battery.get("voltage"),
                 battery.get("temperature"))

        try:
            drain = float(battery_before.get("percentage", 0)) - float(battery.get("percentage", 0))
            log.info("Conso cycle : %.1f%% (avant=%s%%, après=%s%%)",
                     drain, battery_before.get("percentage"), battery.get("percentage"))
        except (TypeError, ValueError):
            pass

        ia: dict = {}
        if wav_ok:
            ia = analyse(wav_path)    
        metadata.write(txt_path, {
            "site": config.SITE,
            "year": now.strftime("%Y"),
            "date": now.strftime("%Y-%m-%d"),
            "piezo_model": config.PIEZO_MODEL,
            "piezo_serial": config.PIEZO_SERIAL,
            "timestamp": ts,
            "wav_ok": wav_ok,
            "frequency_hz": config.SAMPLE_RATE,
            "detection_class": ia.get("class_name", "N/A"),
            "detection_conf": ia.get("confidence", "N/A"),
            "detection_ratio": ia.get("file_ratio", "N/A"),
            "alert_sent": "oui" if ia.get("sms_sent") else "non",
            "call_sent": "oui" if ia.get("call_made") else "non",
            "battery_pct": battery.get("percentage", "N/A"),
            "battery_voltage": battery.get("voltage", "N/A"),
            "battery_temp": battery.get("temperature", "N/A"),
            "battery_status": battery.get("status", "N/A"),
            "gps_lat": gps.get("latitude", "N/A"),
            "gps_lon": gps.get("longitude", "N/A"),
            "gps_accuracy": gps.get("accuracy", "N/A"),
        })
        append_cycle_log(ts, cycle, battery, wav_ok, ia)
        check_battery_alert(battery)

        if config.ENABLE_DASHBOARD:
            write_status_file(autonomy.summary())


        log.info("Pause %ss...", config.SLEEP_DURATION)
        time.sleep(config.SLEEP_DURATION)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Arrêt demandé (Ctrl+C)")