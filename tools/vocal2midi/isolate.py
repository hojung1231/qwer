"""Stage 1 — vocal isolation.

Two back-ends:
  * demucs  : neural source separation (best; needs the pretrained weights).
  * center  : model-free fallback. Lead vocals are mixed dead-centre, so we keep
              the time-frequency bins where L and R agree in phase and level,
              then drop percussive energy (HPSS) and band-limit to the voice.
"""
from __future__ import annotations
import subprocess, tempfile, os
import numpy as np
import librosa, soundfile as sf


def decode(path: str, sr: int = 44100) -> np.ndarray:
    """Decode any ffmpeg-readable file to float32 stereo, shape (2, n)."""
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vn",
                        "-ac", "2", "-ar", str(sr), wav], check=True)
        y, _ = sf.read(wav, dtype="float32", always_2d=True)
    return y.T


def center_extract(stereo: np.ndarray, sr: int, power: float = 4.0) -> np.ndarray:
    n_fft, hop = 4096, 1024
    L = librosa.stft(stereo[0], n_fft=n_fft, hop_length=hop)
    R = librosa.stft(stereo[1], n_fft=n_fft, hop_length=hop)
    # 1.0 where L == R (same magnitude and phase), -> 0 for side / decorrelated content
    sim = 2.0 * np.real(L * np.conj(R)) / (np.abs(L) ** 2 + np.abs(R) ** 2 + 1e-12)
    mask = np.clip(sim, 0.0, 1.0) ** power
    C = mask * 0.5 * (L + R)
    # remove drums: keep the harmonic part only
    H, _ = librosa.decompose.hpss(np.abs(C), kernel_size=(17, 31), margin=(1.0, 2.0))
    C = C * (H / (np.abs(C) + 1e-12)).clip(0, 1)
    # voice band: fundamentals of a tenor/pop vocal start around 100 Hz
    f = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = 1.0 / (1.0 + (140.0 / np.maximum(f, 1.0)) ** 8)
    C = C * band[:, None]
    return librosa.istft(C, hop_length=hop, length=stereo.shape[1])


def demucs_extract(stereo: np.ndarray, sr: int, stereo_out: bool = False) -> np.ndarray:
    import torch
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    model = get_model("htdemucs")
    model.eval()
    x = torch.from_numpy(stereo)[None]
    if sr != model.samplerate:
        import torchaudio
        x = torchaudio.functional.resample(x, sr, model.samplerate)
    ref = x.mean(1, keepdim=True)
    mu, sd = ref.mean(), ref.std() + 1e-8
    x = (x - mu) / sd
    with torch.no_grad():
        out = apply_model(model, x, shifts=1, overlap=0.25, progress=False)[0]
    out = out * sd + mu                      # back to the level of the original recording
    v = out[model.sources.index("vocals")].numpy()            # (2, n): keep the stereo image
    if sr != model.samplerate:
        v = librosa.resample(v, orig_sr=model.samplerate, target_sr=sr)
    return v if stereo_out else v.mean(0)


def lead_from_stereo(vocals: np.ndarray, power: float = 3.0) -> np.ndarray:
    """Lead vocal out of a stereo vocal stem.  The lead is mixed dead-centre; harmony and
    doubled backing vocals are spread left/right.  Keep the time-frequency bins where the
    two channels agree in level and phase (same idea as center_extract, but on a stem that
    no longer contains instruments, so nothing else needs filtering)."""
    n_fft, hop = 4096, 1024
    L = librosa.stft(vocals[0], n_fft=n_fft, hop_length=hop)
    R = librosa.stft(vocals[1], n_fft=n_fft, hop_length=hop)
    sim = 2.0 * np.real(L * np.conj(R)) / (np.abs(L) ** 2 + np.abs(R) ** 2 + 1e-12)
    C = np.clip(sim, 0.0, 1.0) ** power * 0.5 * (L + R)
    return librosa.istft(C, hop_length=hop, length=vocals.shape[1])


def isolate(stereo: np.ndarray, sr: int, method: str = "auto", lead_only: bool = False) -> tuple[np.ndarray, str]:
    if method in ("auto", "demucs"):
        try:
            if lead_only:
                return lead_from_stereo(demucs_extract(stereo, sr, stereo_out=True)), "demucs"
            return demucs_extract(stereo, sr), "demucs"
        except Exception as e:  # weights unavailable / offline
            if method == "demucs":
                raise
            print(f"[isolate] demucs unavailable ({type(e).__name__}); using centre extraction")
    return center_extract(stereo, sr), "center"
