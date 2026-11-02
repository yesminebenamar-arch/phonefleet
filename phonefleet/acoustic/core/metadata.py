"""Lecture/écriture des fichiers .txt de métadonnées qui accompagnent chaque WAV."""

from pathlib import Path


def write(txt_path: Path, fields: dict) -> None:
    """Écrit un dict en format `clé = valeur` ligne par ligne."""
    txt_path = Path(txt_path)
    with txt_path.open("w", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k:<16} = {v}\n")


def read(txt_path: Path) -> dict:
    """Lit un fichier `clé = valeur` (tolérant aux erreurs)."""
    meta = {}
    try:
        for line in Path(txt_path).read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            meta[k.strip()] = v.strip()
    except OSError:
        pass
    return meta
