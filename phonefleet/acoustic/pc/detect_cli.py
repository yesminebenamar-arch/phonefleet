"""CLI pour tester l'IA sur un WAV unique.

Usage : python -m pc.detect_cli --wav file.wav [--weights mlp_weights.npz]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.detector import detect
from core import alert


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", required=True)
    parser.add_argument("--weights", default=config.MODEL_WEIGHTS or None)
    parser.add_argument("--threshold", type=float, default=config.MIN_CONFIDENCE)
    parser.add_argument("--sms", action="store_true",
                        help="Envoie un SMS si alerte (simulation hors Termux)")
    args = parser.parse_args()

    wav = Path(args.wav)
    if not wav.exists():
        raise SystemExit(f"Fichier introuvable : {wav}")

    result = detect(wav, weights_path=args.weights, conf_threshold=args.threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.sms:
        sent = alert.maybe_send_detection_alert(result)
        print(f"\nSMS : {'envoyé' if sent else 'non envoyé'}")


if __name__ == "__main__":
    main()
