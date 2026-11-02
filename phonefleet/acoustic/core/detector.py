"""Pipeline de détection : WAV → MEL → MLP → vote temporel → décision."""

import os
from pathlib import Path

import numpy as np

from core import audio
from core.model import MLP, CLASSES, ALERT_CLASSES


def temporal_vote(probs: np.ndarray, conf_threshold: float = 0.65) -> dict:
    """Vote majoritaire sur toutes les fenêtres + seuil de cohérence.

    `probs` est de forme (n_frames, n_classes).
    """
    preds = np.argmax(probs, axis=1)
    counts = np.bincount(preds, minlength=len(CLASSES))
    majority = int(np.argmax(counts))
    file_ratio = float(counts[majority] / max(len(preds), 1))
    mean_prob = float(probs[:, majority].mean())
    probs_mean = probs.mean(axis=0)

    if file_ratio < conf_threshold:
        decision = "inconnu"
        alert = False
    else:
        decision = CLASSES[majority]
        alert = (majority in ALERT_CLASSES) and (mean_prob >= conf_threshold)

    return {
        "class_id": majority,
        "class_name": decision,
        "confidence": round(mean_prob, 3),
        "file_ratio": round(file_ratio, 3),
        "alert": alert,
        "probs_mean": {CLASSES[i]: round(float(p), 3)
                       for i, p in enumerate(probs_mean)},
    }


def detect(wav_path: str | Path,
           weights_path: str | None = None,
           conf_threshold: float = 0.65) -> dict:
    """Pipeline complète sur un fichier WAV."""
    wav_path = Path(wav_path)
    rate, data = audio.load_wav(wav_path)
    data = audio.resample(data, rate, audio.TARGET_SR)
    mel = audio.mel_spectrogram(data)

    if mel.shape[1] < 2:
        return {"error": "Fichier trop court", "wav_file": wav_path.name}

    model = MLP(input_dim=audio.N_MEL, n_classes=len(CLASSES))
    if weights_path and os.path.exists(weights_path):
        model.load(weights_path)

    probs = model.predict_proba(mel)
    result = temporal_vote(probs, conf_threshold=conf_threshold)
    result["wav_file"] = wav_path.name
    result["n_frames"] = int(mel.shape[1])
    return result
