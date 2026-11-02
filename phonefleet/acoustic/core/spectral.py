"""Analyse spectrale : STFT, détection d'événements, spectrogramme PNG.
Module appelé côté PC après réception d'un WAV. Distinct de core.detector
qui fait la classification IA — ici on cherche juste des pics d'énergie
dans la bande utile pour produire un spectrogramme et compter les événements.
"""

import json
from pathlib import Path

import numpy as np
import scipy.signal as sig

from core import audio


F_LOW = 100
F_HIGH = 3000
NPERSEG = 1024
NOVERLAP = 768
EVENT_THRESH_DB = 6.0
MIN_EVENT_GAP_S = 0.3


def stft_band(data: np.ndarray, rate: int,
              f_low: float = F_LOW, f_high: float = F_HIGH):
    """STFT restreinte à la bande utile, en dB."""
    freqs, times, sxx = sig.spectrogram(
        data, fs=rate, nperseg=NPERSEG, noverlap=NOVERLAP, window="hann"
    )
    sxx_db = 10 * np.log10(sxx + 1e-12)
    mask = (freqs >= f_low) & (freqs <= f_high)
    return freqs[mask], times, sxx_db[mask]


def detect_events(freqs: np.ndarray, times: np.ndarray, sxx_db: np.ndarray,
                  thresh_db: float = EVENT_THRESH_DB,
                  min_gap_s: float = MIN_EVENT_GAP_S):
    """Pics d'énergie au-dessus du bruit de fond (20e percentile)."""
    energy = sxx_db.mean(axis=0)
    noise_floor = float(np.percentile(energy, 20))
    threshold = noise_floor + thresh_db
    above = energy > threshold

    events = []
    in_event = False
    t_start = 0.0

    for i, t in enumerate(times):
        if above[i] and not in_event:
            in_event = True
            t_start = float(t)
        elif not above[i] and in_event:
            in_event = False
            duration = float(t) - t_start
            if duration < min_gap_s:
                continue
            mask_t = (times >= t_start) & (times < t)
            peak_idx = int(sxx_db[:, mask_t].mean(axis=1).argmax())
            snr = float(energy[mask_t].mean() - noise_floor)
            events.append({
                "time_s": round(t_start, 3),
                "duration_s": round(duration, 3),
                "peak_freq_hz": round(float(freqs[peak_idx]), 1),
                "snr_db": round(snr, 2),
            })

    if in_event:
        duration = float(times[-1]) - t_start
        if duration >= min_gap_s:
            mask_t = times >= t_start
            peak_idx = int(sxx_db[:, mask_t].mean(axis=1).argmax())
            snr = float(energy[mask_t].mean() - noise_floor)
            events.append({
                "time_s": round(t_start, 3),
                "duration_s": round(duration, 3),
                "peak_freq_hz": round(float(freqs[peak_idx]), 1),
                "snr_db": round(snr, 2),
            })

    return events, noise_floor


def analyze_wav(wav_path: Path, out_dir: Path, make_plots: bool = True) -> dict:
    """Analyse complète : charge le WAV, calcule STFT, détecte événements,
    génère spectrogramme et PSD. Retourne le résumé.

    `make_plots` : si False, saute complètement l'étape matplotlib (PNG
    spectrogramme + PSD) — utile pour tourner sur Termux/Fairphone où
    matplotlib est lourd/pas forcément installé. La détection d'événements
    et le résumé JSON/CSV, eux, ne dépendent que de scipy/numpy et
    fonctionnent dans tous les cas.
    """
    wav_path = Path(wav_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rate, data = audio.load_wav(wav_path)
    filtered = audio.bandpass(data, rate, F_LOW, F_HIGH)
    freqs, times, sxx_db = stft_band(filtered, rate)
    events, noise_floor = detect_events(freqs, times, sxx_db)

    if make_plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        # Spectrogramme
        fig, ax = plt.subplots(figsize=(14, 5))
        vmin = float(np.percentile(sxx_db, 5))
        vmax = float(np.percentile(sxx_db, 99))
        im = ax.pcolormesh(times, freqs / 1000, sxx_db, shading="gouraud",
                           cmap="inferno",
                           norm=mcolors.Normalize(vmin=vmin, vmax=vmax))
        plt.colorbar(im, ax=ax, label="Puissance (dB)")
        for ev in events:
            ax.axvline(ev["time_s"], color="cyan", lw=0.8, alpha=0.7)
        ax.set_xlabel("Temps (s)")
        ax.set_ylabel("Fréquence (kHz)")
        ax.set_title(f"Spectrogramme — {wav_path.stem}")
        ax.set_ylim(F_LOW / 1000, F_HIGH / 1000)
        fig.tight_layout()
        fig.savefig(out_dir / "spectrogram.png", dpi=150)
        plt.close(fig)

        # PSD (Welch)
        freqs_w, psd = sig.welch(filtered, fs=rate, nperseg=NPERSEG)
        mask = (freqs_w >= F_LOW) & (freqs_w <= F_HIGH)
        psd_db = 10 * np.log10(psd[mask] + 1e-12)
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(freqs_w[mask], psd_db, color="#00c8ff", lw=1.2)
        ax.fill_between(freqs_w[mask], psd_db.min(), psd_db, alpha=0.15, color="#00c8ff")
        ax.set_xlabel("Fréquence (Hz)")
        ax.set_ylabel("PSD (dB/Hz)")
        ax.set_title(f"PSD — {wav_path.stem}")
        ax.set_xlim(F_LOW, F_HIGH)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "psd.png", dpi=150)
        plt.close(fig)

    # CSV événements
    with (out_dir / "events.csv").open("w", encoding="utf-8") as f:
        f.write("time_s,duration_s,peak_freq_hz,snr_db\n")
        for ev in events:
            f.write(f"{ev['time_s']},{ev['duration_s']},"
                    f"{ev['peak_freq_hz']},{ev['snr_db']}\n")

    summary = {
        "fichier": wav_path.name,
        "duree_s": round(len(data) / rate, 2),
        "taux_echantillon": int(rate),
        "bande_utile_hz": [F_LOW, F_HIGH],
        "bruit_fond_db": round(noise_floor, 2),
        "nb_evenements": len(events),
        "snr_moyen_db": (round(float(np.mean([e["snr_db"] for e in events])), 2)
                          if events else None),
        "freq_dominante_hz": (round(float(np.median([e["peak_freq_hz"] for e in events])), 1)
                               if events else None),
        "evenements": events,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary