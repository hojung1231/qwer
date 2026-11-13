"""Stage 2 — frame-level F0 of the isolated vocal (CREPE, 10 ms hop)."""
from __future__ import annotations
import numpy as np
import librosa

HOP_S = 0.01


def track(vocal: np.ndarray, sr: int, fmin: float = 82.0, fmax: float = 1050.0,
          model: str = "full"):
    """Returns (times, f0_hz, periodicity, rms). f0 is defined on every frame;
    voicing is decided later from periodicity + loudness."""
    import torch, torchcrepe
    device = "cuda" if torch.cuda.is_available() else "cpu"
    y = librosa.resample(vocal, orig_sr=sr, target_sr=16000)
    hop = int(16000 * HOP_S)
    x = torch.from_numpy(y.astype(np.float32))[None]
    f0, per = torchcrepe.predict(x, 16000, hop, fmin, fmax, model,
                                 decoder=torchcrepe.decode.viterbi,
                                 return_periodicity=True, batch_size=1024, device=device)
    f0, per = f0[0].cpu().numpy(), per[0].cpu().numpy()
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop, center=True)[0]
    n = min(len(f0), len(rms))
    t = np.arange(n) * HOP_S
    return t, f0[:n], per[:n], rms[:n]
