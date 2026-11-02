"""Lecture de la configuration depuis un fichier .env.
Ordre de priorité pour chaque clé :
    1. variable d'environnement du processus (os.environ) — permet aux scripts
       wrapper Termux de surcharger un profil sans toucher au .env
       (ex: PROFILE=SIMPLE python -m android.receiver)
    2. fichier .env
    3. valeur par défaut fournie à get()
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"


def _parse_env(path: Path) -> dict:
    if not path.exists():
        return {}
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


_ENV = _parse_env(ENV_PATH)


def get(key: str, default=None, *, cast=str):
    """Lit une clé depuis os.environ PUIS .env, avec valeur par défaut typée."""
    raw = os.environ.get(key, _ENV.get(key, default))
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


def require(key: str, *, cast=str):
    """Comme get() mais lève une erreur si la clé est absente."""
    raw = os.environ.get(key, _ENV.get(key))
    if raw is None or raw == "":
        raise SystemExit(f"Clé manquante dans {ENV_PATH.name} : {key}")
    return cast(raw)


_TRUTHY = {"1", "true", "yes", "oui", "on"}


def flag(key: str, default: bool) -> bool:
    """Lit un booléen depuis os.environ/.env ; sinon renvoie `default` (preset).

    Valeurs vraies : 1, true, yes, oui, on (insensible à la casse).
    """
    raw = os.environ.get(key, _ENV.get(key))
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _TRUTHY


# Connexion Fairphone
PHONE_IP = get("PHONE_IP", "")
PHONE_HOST = get("PHONE_HOST", "") or PHONE_IP
SSH_PORT = get("SSH_PORT", 8022, cast=int)
SSH_USER = get("SSH_USER", "")
SSH_PASSWORD = get("SSH_PASSWORD", "")

# Déploiement
SITE = get("SITE", "inconnu")
OUTPUT_FOLDER = get("OUTPUT_FOLDER", "recordings")

# Sites connus proposés lors de la configuration interactive.

KNOWN_SITES = ["sete", "banyuls", "marseille", "montpellier"]

# Capteur piézo / hydrophone (référence + numéro de série)
PIEZO_MODEL = get("PIEZO_MODEL", "inconnu")
PIEZO_SERIAL = get("PIEZO_SERIAL", "inconnu")

# Alertes
ALERT_PHONE = get("ALERT_PHONE", "+33XXXXXXXXX")
MIN_CONFIDENCE = get("MIN_CONFIDENCE", 0.65, cast=float)
COOLDOWN_MINUTES = get("COOLDOWN_MINUTES", 10, cast=int)


# Modèle
MODEL_WEIGHTS = get("MODEL_WEIGHTS", "")

# Enregistrement (44.1 kHz par défaut, conforme au piézo/hydrophone utilisé)
RECORD_DURATION = get("RECORD_DURATION", 60, cast=int)
SLEEP_DURATION = get("SLEEP_DURATION", 60, cast=int)
SAMPLE_RATE = get("SAMPLE_RATE", 44100, cast=int)
# Seuils
BATTERY_VOLTAGE_THRESHOLD_MV = get("BATTERY_VOLTAGE_THRESHOLD_MV", 3400, cast=int)

# Palier "batterie critique" (distinct de l'alerte "batterie faible" ci-dessus) :
# sous ce pourcentage, on accepte de RENVOYER le SMS à intervalle régulier
# (CRITICAL_ALERT_COOLDOWN_MINUTES) plutôt qu'une seule fois — l'appareil
# pouvant s'éteindre à tout moment, on préfère maximiser les chances qu'au
# moins un des SMS passe, quitte à en recevoir plusieurs.
CRITICAL_BATTERY_PCT = get("CRITICAL_BATTERY_PCT", 5.0, cast=float)
CRITICAL_ALERT_COOLDOWN_MINUTES = get("CRITICAL_ALERT_COOLDOWN_MINUTES", 15, cast=int)

# Autonomie batterie : consommation calibrée par défaut, en % par jour.
# Sert de point de départ ; l'estimation bascule ensuite sur le taux de décharge
# réellement observé pendant la mission (voir core/autonomy.py).
BATTERY_DRAIN_PCT_PER_DAY = get("BATTERY_DRAIN_PCT_PER_DAY", 25.0, cast=float)

# Profils de déploiement

PROFILES = {
    # SIMPLE       : enregistrement, AUCUN SMS, AUCUN appel.
    "SIMPLE":         dict(sms_detection=False, sms_battery=False,
                           gps=False, dashboard=True, call_detection=False),
    # ALERTE       : SMS sur toutes les classes d'alerte (bateaux) + SMS batterie faible.
    "ALERTE":         dict(sms_detection=True,  sms_battery=True,
                           gps=False, dashboard=True, call_detection=False),
    # ALLO_BRUIT   : ALERTE + appel téléphonique (en plus du SMS) sur détection
    # de forte confiance — cf. CALL_MIN_CONFIDENCE / CALL_COOLDOWN_MINUTES.
    "ALLO_BRUIT":     dict(sms_detection=True,  sms_battery=True,
                           gps=False, dashboard=True, call_detection=True),
    # TOUTES_OPTIONS : tout activé (alertes, batterie, GPS, statut local, appel).
    "TOUTES_OPTIONS": dict(sms_detection=True,  sms_battery=True,
                           gps=True,  dashboard=True, call_detection=True),
}

PROFILE = get("PROFILE", "TOUTES_OPTIONS").upper()
_preset = PROFILES.get(PROFILE, PROFILES["TOUTES_OPTIONS"])

# Flags effectifs = preset du profil, surchargeables clé par clé.
ENABLE_SMS_DETECTION = flag("ENABLE_SMS_DETECTION", _preset["sms_detection"])
ENABLE_SMS_BATTERY   = flag("ENABLE_SMS_BATTERY",   _preset["sms_battery"])
ENABLE_GPS           = flag("ENABLE_GPS",           _preset["gps"])
ENABLE_DASHBOARD     = flag("ENABLE_DASHBOARD",     _preset["dashboard"])
ENABLE_CALL_DETECTION = flag("ENABLE_CALL_DETECTION", _preset["call_detection"])

# Seuil et anti-spam dédiés à l'appel — volontairement plus stricts que le SMS
# (un appel est plus intrusif) : confiance minimale plus haute, cooldown plus long.
CALL_MIN_CONFIDENCE = get("CALL_MIN_CONFIDENCE", 0.80, cast=float)
CALL_COOLDOWN_MINUTES = get("CALL_COOLDOWN_MINUTES", 30, cast=int)


# Chemins Termux fixes (sur le Fairphone)
TERMUX_HOME = "/data/data/com.termux/files/home"
TERMUX_DATA = f"{TERMUX_HOME}/data"
# Dossier accessible depuis le téléphone (VLC, Gestionnaire de fichiers...)
AUDIO_FOLDER = f"{TERMUX_HOME}/storage/shared/Recordings"


# ─────────────────────────────────────────────────────────────────────────────
# Configuration interactive (côté PC uniquement — JAMAIS au chargement du module)
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Normalise un nom libre en identifiant de dossier sûr (minuscules, sans accents)."""
    import unicodedata
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.strip().lower()
    return "".join(c if c.isalnum() else "-" for c in name).strip("-") or "inconnu"


def update_env(updates: dict) -> None:
    """Écrit/met à jour des clés dans .env en conservant commentaires et ordre.

    Met aussi à jour les variables du module en mémoire (ex: config.SITE)
    pour que la suite du programme voie immédiatement les nouvelles valeurs.
    """
    updates = {k: str(v) for k, v in updates.items()}
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    # Clés nouvelles (absentes du fichier)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")

    # Rafraîchir le cache et les globals du module
    _ENV.update(updates)
    g = globals()
    for key, val in updates.items():
        if key in g:
            g[key] = val

def prompt_site() -> str:
    """Menu interactif de choix du site. Retourne un identifiant normalisé."""
    print("\nSite de déploiement :")
    for i, s in enumerate(KNOWN_SITES, 1):
        print(f"  {i}. {s}")
    print(f"  {len(KNOWN_SITES) + 1}. autre (saisir un nom)")
    while True:
        choix = input("Choix [1] : ").strip() or "1"
        if choix.isdigit():
            n = int(choix)
            if 1 <= n <= len(KNOWN_SITES):
                return KNOWN_SITES[n - 1]
            if n == len(KNOWN_SITES) + 1:
                libre = input("Nom du site : ").strip()
                if libre:
                    return _slugify(libre)
        # Tolérance : l'utilisateur a tapé directement un nom
        if choix and not choix.isdigit():
            return _slugify(choix)
        print("Choix invalide, réessayez.")


def prompt_piezo() -> tuple[str, str]:
    """Saisie de la référence et du numéro de série du capteur piézo."""
    print("\nCapteur piézo / hydrophone :")
    model = input(f"  Référence/modèle [{PIEZO_MODEL}] : ").strip() or PIEZO_MODEL
    serial = input(f"  Numéro de série  [{PIEZO_SERIAL}] : ").strip() or PIEZO_SERIAL
    return model, serial


def setup_interactive(force: bool = False) -> None:
    """Demande site + piézo s'ils sont absents (ou si force=True) et persiste dans .env.
    À appeler côté PC (humain présent), typiquement depuis launch.py, AVANT
    de déployer .env sur le Fairphone. Ne fait rien si tout est déjà renseigné.
    """
    updates = {}
    if force or SITE in ("", "inconnu"):
        updates["SITE"] = prompt_site()
    if force or PIEZO_MODEL in ("", "inconnu") or PIEZO_SERIAL in ("", "inconnu"):
        model, serial = prompt_piezo()
        updates["PIEZO_MODEL"] = model
        updates["PIEZO_SERIAL"] = serial
    if updates:
        update_env(updates)
        print(f"\n✓ Configuration enregistrée : site={SITE}, "
              f"piézo={PIEZO_MODEL} (SN {PIEZO_SERIAL})\n")