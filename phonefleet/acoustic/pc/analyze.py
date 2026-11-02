"""Analyse spectrale d'un WAV : spectrogramme, PSD, événements.

Usage : python -m pc.analyze --wav <file.wav> --out <dossier>
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import spectral
from core.logging_utils import get_logger

log = get_logger("analyze")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse spectrale d'un WAV")
    parser.add_argument("--wav", required=True, help="Chemin vers le fichier WAV")
    parser.add_argument("--out", required=True, help="Dossier de sortie")
    args = parser.parse_args()

    wav = Path(args.wav)
    if not wav.exists():
        raise SystemExit(f"Fichier introuvable : {wav}")

    log.info("Analyse de %s", wav.name)
    summary = spectral.analyze_wav(wav, Path(args.out))
    log.info("→ %d événement(s) | bruit=%.1f dB | sortie=%s/",
             summary["nb_evenements"], summary["bruit_fond_db"], args.out)


if __name__ == "__main__":
    main()
