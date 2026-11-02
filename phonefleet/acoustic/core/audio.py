"""Chargement et prétraitement audio (chargement WAV, rééchantillonnage, MEL)."""

from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal as sig


TARGET_SR = 16000
N_FFT = 1024
N_MEL = 128
BLOCK_SIZE = 8


def load_wav(wav_path: Path) -> tuple[int, np.ndarray]:
    """Lit un WAV, le convertit en mono float32 normalisé dans [-1, 1]."""
    rate, data = wavfile.read(str(wav_path))
    if data.ndim == 2:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    peak = float(np.abs(data).max())
    if peak > 0:
        data /= max(peak, np.iinfo(np.int16).max)
    return rate, data


def resample(data: np.ndarray, src_rate: int, dst_rate: int = TARGET_SR) -> np.ndarray:
    if src_rate == dst_rate:
        return data
    n = int(len(data) * dst_rate / src_rate)
    return sig.resample(data, n).astype(np.float32)


def bandpass(data: np.ndarray, rate: int, f_low: float, f_high: float,
             order: int = 4) -> np.ndarray:
    nyq = rate / 2.0
    sos = sig.butter(order, [f_low / nyq, f_high / nyq],
                     btype="band", output="sos")
    return sig.sosfiltfilt(sos, data).astype(np.float32)


def _mel_filterbank(n_mels: int, n_bins: int, sr: int) -> np.ndarray:
    """Banc de filtres Mel triangulaires en numpy pur (compatible Termux)."""
    high_mel = 2595 * np.log10(1 + (sr / 2) / 700)
    mel_pts = np.linspace(0, high_mel, n_mels + 2)
    hz_pts = 700 * (10 ** (mel_pts / 2595) - 1)
    bin_pts = np.clip(
        np.floor((n_bins * 2) * hz_pts / sr).astype(int), 0, n_bins - 1
    )
    filters = np.zeros((n_mels, n_bins), dtype=np.float32)
    for m in range(1, n_mels + 1):
        a, b, c = bin_pts[m - 1], bin_pts[m], bin_pts[m + 1]
        if b > a:
            filters[m - 1, a:b] = np.linspace(0, 1, b - a, endpoint=False)
        if c > b:
            filters[m - 1, b:c] = np.linspace(1, 0, c - b, endpoint=False)
    return filters


def mel_spectrogram(data: np.ndarray, sr: int = TARGET_SR,
                    n_mels: int = N_MEL, n_fft: int = N_FFT,
                    block_size: int = BLOCK_SIZE) -> np.ndarray:
    """Spectrogramme MEL normalisé L2, moyenné par blocs (pipeline IARA).

    Retourne un array (n_mels, n_blocks).
    """
    _, _, spec = sig.spectrogram(
        data, fs=sr, nperseg=n_fft, noverlap=n_fft // 2, window="hann"
    )
    mel_filt = _mel_filterbank(n_mels, n_fft // 2 + 1, sr)
    mel = np.log1p(mel_filt @ spec * 1e6)

    n_blocks = mel.shape[1] // block_size
    if n_blocks == 0:
        return mel
    mel = mel[:, : n_blocks * block_size]
    mel = mel.reshape(n_mels, n_blocks, block_size).mean(axis=2)

    norms = np.linalg.norm(mel, axis=0, keepdims=True) + 1e-8
    return (mel / norms).astype(np.float32)
