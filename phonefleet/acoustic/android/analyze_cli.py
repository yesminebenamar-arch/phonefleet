"""Analyse spectrale d'un WAV, embarquée sur le Fairphone (Termux) — SANS
matplotlib (pas de PNG). Produit summary.json + events.csv, exactement
comme pc/analyze.py, mais uniquement la partie numérique (scipy/numpy),
utilisable directement sur le téléphone sans installer matplotlib.

Usage (sur le Fairphone, dans Termux) :
    cd ~/pfe
    python -m android.analyze_cli --wav ~/data/banyuls/2026/07/10/log_2026-07-10_10-00-00.wav \
        --out ~/analyse_locale

Si tu veux les PNG (spectrogramme/PSD), utilise plutôt pc/analyze.py côté
PC après collecte (matplotlib est plus fiable/rapide sur PC) : ce script
donne les mêmes chiffres (événements, bruit de fond, SNR) mais pas les
images.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import spectral
from core.logging_utils import get_logger

log = get_logger("analyze_cli")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse spectrale d'un WAV (embarqué, sans PNG)")
    parser.add_argument("--wav", required=True, help="Chemin vers le fichier WAV")
    parser.add_argument("--out", required=True, help="Dossier de sortie (summary.json, events.csv)")
    args = parser.parse_args()

    wav = Path(args.wav)
    if not wav.exists():
        raise SystemExit(f"Fichier introuvable : {wav}")

    log.info("Analyse de %s (sans graphiques — make_plots=False)", wav.name)
    summary = spectral.analyze_wav(wav, Path(args.out), make_plots=False)
    log.info("→ %d événement(s) | bruit=%.1f dB | résumé=%s/summary.json",
             summary["nb_evenements"], summary["bruit_fond_db"], args.out)
    if summary["evenements"]:
        log.info("Premier événement : %.1fs, %.0f Hz, SNR %.1f dB",
                 summary["evenements"][0]["time_s"],
                 summary["evenements"][0]["peak_freq_hz"],
                 summary["evenements"][0]["snr_db"])


if __name__ == "__main__":
    main()