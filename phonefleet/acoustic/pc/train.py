"""Entraînement MLP sur données locales annotées.

Structure attendue :
    data_dir/
        small/      *.wav ou *.flac  — petits bateaux
        medium/
        large/
        background/
        bio/        (optionnel, nécessite core/model.py à jour — voir garde-fou plus bas)

Sortie : mlp_weights.npz

Usage :
    python -m pc.train --data ./training_data --epochs 150 --out mlp_weights.npz
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import audio
from core.model import MLP, CLASSES, train
from core.logging_utils import get_logger

log = get_logger("train")

CLASS_MAP = {"small": 0, "medium": 1, "large": 2, "background": 3, "bio": 4}
CLASS_NAMES = {v: k for k, v in CLASS_MAP.items()}


def _load_windows(files: list[Path], class_id: int) -> tuple[list, list]:
    """Chargement SÉQUENTIEL (un fichier à la fois) — volontaire : pas de
    ProcessPoolExecutor ici, pour éviter de saturer la RAM sur de gros
    fichiers (vécu : le parallélisme a fait perdre ~95% des fichiers
    large/medium par manque de mémoire sur ce dataset)."""
    X, y = [], []
    for f in files:
        try:
            rate, data = audio.load_wav(f)
            data = audio.resample(data, rate)
            mel = audio.mel_spectrogram(data)
            for col in range(mel.shape[1]):
                X.append(mel[:, col])
                y.append(class_id)
        except Exception as e:
            log.warning("Skip %s : %s", f.name, e)
    return X, y


def build_dataset(data_dir: Path, test_ratio: float = 0.2, seed: int = 42
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Pour chaque WAV, calcule le spectrogramme MEL et empile chaque fenêtre.

    Split TRAIN/TEST fait au niveau du FICHIER (pas de la fenêtre) : les
    fenêtres d'un même WAV se ressemblent fortement, donc les répartir au
    hasard entre train et test biaiserait l'évaluation (fuite d'information).
    """
    rng = np.random.default_rng(seed)
    X_train, y_train, X_test, y_test = [], [], [], []
    n_model_classes = len(CLASSES)

    for class_name, class_id in CLASS_MAP.items():
        class_dir = data_dir / class_name
        if not class_dir.is_dir():
            continue

        # Garde-fou : le modèle actuel (core/model.py CLASSES) ne connaît que
        # n_model_classes classes (0..n-1). Si un dossier existe pour une
        # classe hors de cette plage (ex: "bio" -> 4 alors que le modèle n'a
        # que 4 classes 0-3), on le SKIP explicitement avec un message clair
        # plutôt que de crasher plus tard (IndexError) pendant l'entraînement.
        if class_id >= n_model_classes:
            log.warning(
                "Dossier '%s' présent (classe id=%d) mais core/model.CLASSES "
                "n'a que %d classe(s) (0..%d). Dossier IGNORÉ — mets à jour "
                "core/model.py CLASSES/ALERT_CLASSES en même temps si tu veux "
                "réactiver cette classe.",
                class_name, class_id, n_model_classes, n_model_classes - 1,
            )
            continue

        files = sorted(list(class_dir.glob("*.wav")) + list(class_dir.glob("*.flac")))
        rng.shuffle(files)
        n_test = max(1, round(len(files) * test_ratio)) if len(files) > 1 else 0
        test_files, train_files = files[:n_test], files[n_test:]
        log.info("Classe %s : %d fichier(s) (%d train / %d test)",
                 class_name, len(files), len(train_files), len(test_files))

        Xtr, ytr = _load_windows(train_files, class_id)
        Xte, yte = _load_windows(test_files, class_id)
        X_train += Xtr; y_train += ytr
        X_test += Xte; y_test += yte

    def _arr(X, y):
        if not X:
            return (np.empty((0, audio.N_MEL), dtype=np.float32),
                    np.empty(0, dtype=np.int64))
        return np.asarray(X, dtype=np.float32), np.asarray(y, dtype=np.int64)

    Xtr, ytr = _arr(X_train, y_train)
    Xte, yte = _arr(X_test, y_test)
    return Xtr, ytr, Xte, yte


def _counts_str(y: np.ndarray) -> str:
    classes, counts = np.unique(y, return_counts=True)
    return ", ".join(f"{CLASS_NAMES.get(int(c), c)}={n}" for c, n in zip(classes, counts))


def rebalance(X: np.ndarray, y: np.ndarray, cap_factor: float, seed: int = 42
             ) -> tuple[np.ndarray, np.ndarray]:
    """Sous-échantillonne les classes majoritaires côté TRAIN uniquement.

    Chaque classe est plafonnée à `cap_factor` fois la taille de la classe
    minoritaire. Le TEST n'est jamais rééquilibré (doit rester représentatif
    de la réalité du terrain)."""
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y, return_counts=True)
    min_count = int(counts.min())
    target = int(min_count * cap_factor)

    idx_keep = []
    for c in classes:
        idx_c = np.where(y == c)[0]
        if len(idx_c) > target:
            idx_c = rng.choice(idx_c, size=target, replace=False)
        idx_keep.append(idx_c)
    idx_keep = np.concatenate(idx_keep)
    rng.shuffle(idx_keep)
    return X[idx_keep], y[idx_keep]


def evaluate(model: MLP, X: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Retourne (accuracy globale, balanced accuracy = moyenne des rappels
    par classe — plus honnête vu le déséquilibre des classes)."""
    if len(X) == 0:
        return float("nan"), float("nan")
    preds = np.argmax(model.forward(X), axis=1)
    acc = float((preds == y).mean())
    recalls = []
    for c in np.unique(y):
        mask = y == c
        recalls.append(float((preds[mask] == c).mean()))
    return acc, float(np.mean(recalls))


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> np.ndarray:
    """cm[i, j] = nombre d'exemples de vraie classe i prédits comme classe j."""
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    return cm


def classification_report(y_true: np.ndarray, y_pred: np.ndarray) -> str:
    """Precision / Recall / F1 / support par classe, à partir de la matrice
    de confusion — plus parlant qu'un seul score global pour identifier
    QUELLES classes le modèle confond entre elles."""
    present = sorted(set(np.unique(y_true).tolist()) | set(np.unique(y_pred).tolist()))
    n = max(present) + 1
    cm = confusion_matrix(y_true, y_pred, n)

    lines = []
    lines.append(f"{'Classe':22s} {'Précision':>10s} {'Rappel':>10s} {'F1':>8s} {'Support':>8s}")
    lines.append("-" * 62)

    f1s = []
    for c in present:
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        support = cm[c, :].sum()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        f1s.append(f1)
        name = CLASS_NAMES.get(c, str(c))
        lines.append(f"{name:22s} {precision*100:9.1f}% {recall*100:9.1f}% "
                     f"{f1*100:7.1f}% {support:8d}")

    lines.append("-" * 62)
    lines.append(f"{'Moyenne macro (F1)':22s} {'':>10s} {'':>10s} "
                 f"{np.mean(f1s)*100:7.1f}%")
    lines.append("")
    lines.append("Matrice de confusion (lignes = vraie classe, colonnes = prédiction) :")
    header = "        " + " ".join(f"{CLASS_NAMES.get(c, c)[:8]:>8s}" for c in present)
    lines.append(header)
    for c in present:
        row = " ".join(f"{cm[c, cc]:8d}" for cc in present)
        lines.append(f"{CLASS_NAMES.get(c, c)[:8]:8s}{row}")

    return "\n".join(lines)


def _snapshot(model: MLP) -> dict:
    return {k: getattr(model, k).copy() for k in ("W1", "b1", "W2", "b2", "W3", "b3")}


def _restore(model: MLP, snap: dict) -> None:
    for k, v in snap.items():
        setattr(model, k, v.copy())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Dossier d'entraînement")
    parser.add_argument("--out", default="mlp_weights.npz")
    parser.add_argument("--epochs", type=int, default=150,
                        help="Nombre MAX d'epochs (l'early stopping peut arrêter avant)")
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--test_ratio", type=float, default=0.2,
                        help="Fraction des FICHIERS (par classe) réservée au test")
    parser.add_argument("--balance_cap", type=float, default=3.0,
                        help="Plafonne chaque classe (train) à cap*taille_classe_min. "
                             "0 ou négatif = désactive le rééquilibrage.")
    parser.add_argument("--eval_every", type=int, default=5,
                        help="Évalue sur le test tous les N epochs")
    parser.add_argument("--patience", type=int, default=4,
                        help="Arrête si pas d'amélioration après N évaluations "
                             "consécutives (= N*eval_every epochs). 0 = désactive.")
    args = parser.parse_args()

    data_dir = Path(args.data)
    if not data_dir.is_dir():
        raise SystemExit(f"Dossier introuvable : {data_dir}")

    log.info("Construction du dataset depuis %s (split %.0f/%.0f par fichier, "
             "chargement séquentiel) ...",
             data_dir, (1 - args.test_ratio) * 100, args.test_ratio * 100)
    X_train, y_train, X_test, y_test = build_dataset(data_dir, test_ratio=args.test_ratio)
    if len(X_train) == 0:
        raise SystemExit("Aucune donnée d'entraînement trouvée")

    log.info("Train (avant rééquilibrage) : %s", _counts_str(y_train))
    if args.balance_cap > 0:
        X_train, y_train = rebalance(X_train, y_train, cap_factor=args.balance_cap)
        log.info("Train (après rééquilibrage, cap=%.1fx) : %s",
                 args.balance_cap, _counts_str(y_train))
    else:
        log.info("Rééquilibrage désactivé (--balance_cap <= 0)")

    log.info("Train : %d fenêtres — Test : %d fenêtres — %d classes",
             len(X_train), len(X_test), len(CLASSES))
    model = MLP(input_dim=audio.N_MEL, n_classes=len(CLASSES))

    best_balanced_acc = -1.0
    best_epoch = 0
    best_snapshot = None
    no_improve_checks = 0
    stop_flag = {"stop": False}

    def on_epoch(epoch, loss, acc):
        nonlocal best_balanced_acc, best_epoch, best_snapshot, no_improve_checks
        if epoch % 5 == 0 or epoch == args.epochs:
            log.info("Epoch %d/%d — loss=%.4f — train_acc=%.1f%%",
                     epoch, args.epochs, loss, acc * 100)

        if epoch % args.eval_every == 0:
            test_acc, test_bal_acc = evaluate(model, X_test, y_test)
            log.info("  -> eval test @ epoch %d : acc=%.1f%% balanced_acc=%.1f%%",
                     epoch, test_acc * 100, test_bal_acc * 100)
            if test_bal_acc > best_balanced_acc:
                best_balanced_acc = test_bal_acc
                best_epoch = epoch
                best_snapshot = _snapshot(model)
                no_improve_checks = 0
                log.info("  -> nouveau meilleur modèle (balanced_acc=%.1f%%)",
                         test_bal_acc * 100)
            else:
                no_improve_checks += 1
                if args.patience > 0 and no_improve_checks >= args.patience:
                    log.info("Early stopping : pas d'amélioration depuis %d "
                             "évaluation(s) (%d epochs)",
                             no_improve_checks, no_improve_checks * args.eval_every)
                    stop_flag["stop"] = True

    train(model, X_train, y_train, epochs=args.epochs, lr=args.lr,
          batch_size=args.batch_size, on_epoch=on_epoch,
          should_stop=lambda: stop_flag["stop"])

    if best_snapshot is not None:
        log.info("Restauration du meilleur modèle (epoch %d, balanced_acc=%.1f%%) "
                 "avant sauvegarde", best_epoch, best_balanced_acc * 100)
        _restore(model, best_snapshot)

    test_acc, test_balanced_acc = evaluate(model, X_test, y_test)
    log.info("=== Évaluation finale sur TEST (fichiers jamais vus à l'entraînement) ===")
    log.info("Test accuracy         : %.1f%%", test_acc * 100)
    log.info("Test balanced accuracy: %.1f%% (moyenne des rappels par classe)",
             test_balanced_acc * 100)
    if best_snapshot is not None and best_epoch != args.epochs:
        log.info("(meilleur modèle obtenu à l'epoch %d, pas au dernier epoch — "
                 "signe d'overfitting après ce point)", best_epoch)

    if len(X_test) > 0:
        y_pred_test = np.argmax(model.forward(X_test), axis=1)
        log.info("\n" + classification_report(y_test, y_pred_test))

    model.save(args.out)
    log.info("Poids sauvegardés → %s", args.out)


if __name__ == "__main__":
    main()