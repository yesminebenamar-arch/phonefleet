"""Trie les enregistrements IARA (tous datasets A-H) dans la structure
attendue par pc/train.py : training_data/small|medium|large|background/*.wav

Source des labels : la feuille "dataset_info" de iara.xlsx, colonnes
"IARA ID" (identifiant = nom de fichier attendu), "Dataset" (A-H) et
"Length" (longueur du navire en mètres).

Seuils de taille — IDENTIQUES à core/model.CLASSES, à ne pas modifier sans
mettre à jour les deux en même temps :
    Length < 50 m    -> small   (classe 0, "Petit bateau")
    50 <= L <= 100 m -> medium  (classe 1, "Bateau moyen")
    Length > 100 m   -> large   (classe 2, "Grand bateau")

Datasets E et H : bruit de fond, pas de navire associé (Length = "-")
    -> background (classe 3).
Tous les autres datasets (A, B, C, D, F, G) : navires, classés par longueur.


Usage :
    python -m pc.prepare_training_data --xlsx iara.xlsx \
        --source ./A ./B ./C ./D ./E \
        --out ./training_data

--source accepte un ou plusieurs dossiers (ceux où vous avez dézippé les
.zip des datasets voulus) ; le script cherche récursivement dedans
(*.wav, *.flac).
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

import openpyxl

AUDIO_EXTS = (".wav", ".flac", ".WAV", ".FLAC")

# Datasets sans navire associé (bruit de fond uniquement).
BACKGROUND_DATASETS = {"E", "H"}


def size_class(length) -> str | None:
    """Longueur (m) -> nom de classe, selon les seuils core/model.CLASSES."""
    try:
        length = float(length)
    except (TypeError, ValueError):
        return None
    if length < 50:
        return "small"
    if length <= 100:
        return "medium"
    return "large"


def load_labels(xlsx_path: Path) -> dict[int, str]:
    """Lit dataset_info et retourne {IARA ID: classe} pour TOUS les datasets
    présents dans le fichier (A-H), pas seulement B/E."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["dataset_info"]
    rows = ws.iter_rows(min_row=2, values_only=True)  # skip header

    labels: dict[int, str] = {}
    skipped_no_length = 0
    seen_datasets: dict[str, int] = {}

    for row in rows:
        iara_id, dataset = row[0], row[1]
        length = row[12]
        if iara_id is None or dataset is None:
            continue
        dataset = str(dataset).strip()
        seen_datasets[dataset] = seen_datasets.get(dataset, 0) + 1

        if dataset in BACKGROUND_DATASETS:
            labels[int(iara_id)] = "background"
        else:
            cls = size_class(length)
            if cls is None:
                skipped_no_length += 1
                continue
            labels[int(iara_id)] = cls

    if skipped_no_length:
        print(f"  (info) {skipped_no_length} enregistrement(s) sans longueur "
              f"renseignée, ignoré(s)")
    print(f"  Datasets rencontrés dans le xlsx : "
          f"{', '.join(f'{k}={v}' for k, v in sorted(seen_datasets.items()))}")
    return labels


_ID_RE = re.compile(r"(\d+)")


def index_audio_files(source_dirs: list[Path]) -> dict[int, Path]:
    """Indexe tous les fichiers audio trouvés, par IARA ID numérique extrait
    du nom de fichier (tolère un préfixe lettre/tiret et des zéros de tête,
    ex: 'B-0457.wav' -> 457, 'D-1203.wav' -> 1203)."""
    index: dict[int, Path] = {}
    for src in source_dirs:
        for ext in AUDIO_EXTS:
            for f in src.rglob(f"*{ext}"):
                digits = _ID_RE.findall(f.stem)
                if not digits:
                    continue
                # Le nom contient parfois d'autres nombres (rare) : on prend
                # le groupe de chiffres le plus long, le plus probable d'être l'ID.
                best = max(digits, key=len)
                index[int(best)] = f
    return index


def find_file(iara_id: int, index: dict[int, Path]) -> Path | None:
    return index.get(iara_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, help="Chemin vers iara.xlsx")
    parser.add_argument("--source", required=True, nargs="+",
                        help="Dossier(s) où les .zip des datasets ont été dézippés")
    parser.add_argument("--out", default="training_data",
                        help="Dossier de sortie (défaut: ./training_data)")
    parser.add_argument("--link", action="store_true",
                        help="Lien symbolique au lieu de copier (économise "
                             "l'espace disque ; Linux/Mac uniquement)")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    source_dirs = [Path(s) for s in args.source]
    out_dir = Path(args.out)

    for s in source_dirs:
        if not s.is_dir():
            raise SystemExit(f"Dossier source introuvable : {s}")

    print("Lecture des labels depuis", xlsx_path.name, "...")
    labels = load_labels(xlsx_path)
    print(f"  {len(labels)} enregistrement(s) labellisé(s) au total")

    print("Indexation des fichiers audio dans", [str(s) for s in source_dirs], "...")
    index = index_audio_files(source_dirs)
    print(f"  {len(index)} fichier(s) audio trouvé(s)")

    counts = {"small": 0, "medium": 0, "large": 0, "background": 0}
    missing = []

    for iara_id, cls in labels.items():
        f = find_file(iara_id, index)
        if f is None:
            missing.append(iara_id)
            continue
        dest_dir = out_dir / cls
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.name
        if args.link:
            if not dest.exists():
                dest.symlink_to(f.resolve())
        else:
            shutil.copy2(f, dest)
        counts[cls] += 1

    print("\n--- Résultat ---")
    for cls, n in counts.items():
        print(f"  {cls:12s} : {n} fichier(s) -> {out_dir / cls}")
    if missing:
        print(f"\n  {len(missing)} IARA ID non retrouvé(s) dans les fichiers "
              f"audio (premiers : {missing[:10]})")
        print("  -> vérifiez que tous les .zip voulus sont bien dézippés dans "
              "les dossiers passés à --source")
    print(f"\nPrêt pour l'entraînement :")
    print(f"  python -m pc.train --data {out_dir} --epochs 50 --out mlp_weights.npz")


if __name__ == "__main__":
    main()