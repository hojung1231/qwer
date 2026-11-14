#!/usr/bin/env python3
"""Split a song into bars without a score.

    python3 bars.py song.mp3 [-o out_dir] [--bpm-hint 70]

Three questions are answered in turn:
  1. Where are the beats?            constant-tempo grid fitted to tracked beats (notes.beat_grid)
  2. How is a beat subdivided?       in 2 (4/4, 2/4 ...) or in 3 (6/8, 12/8): which grid of
                                     sub-beats collects more of the note onsets
  3. Which beat starts the bar?      the phase (0..3) at which harmony changes and bass
                                     accents pile up - chords change on the downbeat far more
                                     often than anywhere else

Bars are assumed to hold four beats (4/4 or 12/8), which covers nearly all pop ballads; triple
metre (3/4, 6/8 felt in two) is not detected.

Writes bars.json (bar number -> start time) and bars_click.mp3 (the song with a high click on
every downbeat and a low click on the other beats) so the result can be checked by ear.
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
import librosa, soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate, notes as N


def subdivision(onset_env, hop_s, t0, period):
    """2 or 3: fold the onset envelope onto one beat and see which sub-beat grid it prefers."""
    t = np.arange(len(onset_env)) * hop_s
    ph = ((t - t0) / period) % 1.0
    def strength(div):
        # onset energy near k/div (k = 1..div-1), relative to the average level
        d = np.abs(((ph * div + 0.5) % 1.0) - 0.5) / div          # distance to nearest sub-beat, in beats
        near = (d < 0.04) & (np.abs(ph - np.round(ph)) > 0.08)    # exclude the beat itself
        return onset_env[near].mean() / (onset_env.mean() + 1e-9)
    s2, s3 = strength(2), strength(3)
    return (3 if s3 > s2 * 1.1 else 2), float(s2), float(s3)


def downbeat_phase(y, sr, t0, period, beats_per_bar=4):
    """Index (0..beats_per_bar-1) of the beat, counted from t0, on which bars start."""
    hop = 1024
    yh = librosa.effects.harmonic(y, margin=3.0)
    chroma = librosa.feature.chroma_cqt(y=yh, sr=sr, hop_length=hop, bins_per_octave=36)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop)); f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = S[(f >= 30) & (f < 150)].sum(0)
    ft = np.arange(chroma.shape[1]) * hop / sr
    nb = int((len(y) / sr - t0) / period)
    C = np.zeros((nb, 12)); L = np.zeros(nb)
    for b in range(nb):
        k = (ft >= t0 + b * period) & (ft < t0 + (b + 1) * period)
        if k.any():
            C[b] = chroma[:, k].mean(1)
        k2 = (ft >= t0 + b * period - 0.05) & (ft < t0 + b * period + 0.12)
        if k2.any():
            L[b] = low[k2].max()
    Cn = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9)
    # harmonic change at beat b: the two beats after it against the two beats before it
    def novelty(w):
        out = np.zeros(nb)
        for b in range(w, nb - w):
            a = Cn[b - w:b].mean(0); c = Cn[b:b + w].mean(0)
            out[b] = 1.0 - float(a @ c) / (np.linalg.norm(a) * np.linalg.norm(c) + 1e-9)
        return out
    nov = novelty(2)
    nov_bar = novelty(beats_per_bar)        # a whole bar against the bar before: tells beat 1 from beat 3
    Ln = L / (np.median(L[L > 0]) + 1e-9)
    idx = np.arange(nb)
    harm = np.array([nov[idx % beats_per_bar == p].mean() for p in range(beats_per_bar)])
    bass = np.array([Ln[idx % beats_per_bar == p].mean() for p in range(beats_per_bar)])
    harm_bar = np.array([nov_bar[idx % beats_per_bar == p].mean() for p in range(beats_per_bar)])
    score = harm / (harm.mean() + 1e-9) + harm_bar / (harm_bar.mean() + 1e-9) + 0.5 * bass / (bass.mean() + 1e-9)
    order = np.argsort(score)[::-1]
    margin = float((score[order[0]] - score[order[1]]) / (score[order[0]] + 1e-9))
    return int(order[0]), margin, score.round(3).tolist()


def find_bars(path, bpm_hint=None, sr=22050):
    y = isolate.decode(path, sr).mean(0)
    t0, period = N.beat_grid(y, sr, bpm_hint)
    # beat trackers often lock onto twice the felt tempo of a slow song; a counted beat faster
    # than ~115 per minute is taken to be the half-beat
    while 60.0 / period > 115.0:
        period *= 2.0
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
    div, s2, s3 = subdivision(oenv, 256 / sr, t0, period)
    phase, margin, scores = downbeat_phase(y, sr, t0, period)
    first = t0 + phase * period
    first -= np.floor(first / (4 * period)) * 4 * period           # earliest bar line in the file
    n = int((len(y) / sr - first) / (4 * period))
    return {"bpm": round(60 / period, 3), "beat_s": round(period, 5), "beats_per_bar": 4,
            "beat_subdivision": div, "time_signature": "12/8" if div == 3 else "4/4",
            "first_bar_s": round(float(first), 3), "bar_s": round(4 * period, 5), "bars": n,
            "downbeat_confidence": round(margin, 3), "phase_scores": scores,
            "subdivision_strength": {"in_2": round(s2, 3), "in_3": round(s3, 3)}}


def click_track(path, info, out_path, sr=44100):
    st = isolate.decode(path, sr); n = st.shape[1]; clk = np.zeros(n, np.float32)
    t = info["first_bar_s"]; k = 0
    while t < n / sr:
        i = int(t * sr); L = int(0.04 * sr); tt = np.arange(L) / sr
        hi = k % 4 == 0
        if i + L < n and i >= 0:
            clk[i:i + L] += (0.9 if hi else 0.45) * np.sin(2 * np.pi * (1760 if hi else 880) * tt) * np.exp(-tt * 70)
        t += info["beat_s"]; k += 1
    out = st * 0.7 + clk[None, :] * 0.6
    out *= min(1.0, 0.98 / np.abs(out).max())
    wav = out_path[:-4] + ".wav"; sf.write(wav, out.T, sr)
    import subprocess
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-b:a", "192k", out_path], check=True); os.remove(wav)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio"); ap.add_argument("-o", "--out", default="out"); ap.add_argument("--bpm-hint", type=float, default=None)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    info = find_bars(a.audio, a.bpm_hint)
    info["bar_starts_s"] = [round(info["first_bar_s"] + i * info["bar_s"], 3) for i in range(info["bars"])]
    json.dump(info, open(os.path.join(a.out, "bars.json"), "w"), indent=1)
    click_track(a.audio, info, os.path.join(a.out, "bars_click.mp3"))
    print(json.dumps({k: v for k, v in info.items() if k != "bar_starts_s"}, indent=1))


if __name__ == "__main__":
    main()
