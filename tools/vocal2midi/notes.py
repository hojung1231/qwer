"""Stage 3 — turn a wobbly sung F0 curve into discrete notes on a metrical grid.

Why not just round F0 to the nearest semitone?  A singer's pitch is not a staircase:
vibrato swings +-50..100 cents at 5-7 Hz, notes are approached by scoops and left by
falls, and consonants break voicing.  Rounding frame by frame turns each of those
into spurious notes.  We therefore:

  1. estimate the recording's tuning offset and fold the octave to cents-from-A440;
  2. decide voicing from CREPE periodicity + loudness (with hysteresis);
  3. decode the most likely *note sequence* with an HMM (Viterbi): one state per
     semitone + silence, a wide emission tolerance so vibrato stays inside one state,
     a heavy switching penalty so only sustained deviations create a new note, and a
     mild key prior so chromatic notes need real evidence;
  4. vote the frame labels onto the 16th-note grid derived from beat tracking and
     split equal-pitch runs at vocal onsets (re-articulated syllables).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import librosa
from scipy.ndimage import median_filter

MAJOR = np.array([0, 2, 4, 5, 7, 9, 11])
KRUMHANSL = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class Note:
    start: float      # seconds
    end: float
    pitch: int        # MIDI number
    slot: int = -1    # first 16th-slot index on the grid (quantised notes only)
    nslots: int = 0


def hz_to_midi_f(f0):
    return 69.0 + 12.0 * np.log2(np.maximum(f0, 1e-6) / 440.0)


def voicing(per, rms, per_on=0.5, per_off=0.3, rel_db=-14.0, win_s=8.0, hop_s=0.01):
    """Voiced = periodic (hysteresis) AND loud relative to the vocal's own recent level.

    The loudness reference is a rolling 90th percentile, so quiet verses and loud
    choruses are each judged on their own scale.  This is what rejects accompaniment
    that leaks through the separation: it is pitched (periodic) but ~10 dB quieter."""
    from scipy.ndimage import percentile_filter
    db = 20 * np.log10(rms + 1e-9)
    step = 10                                           # evaluate the slow envelope every 100 ms
    ref = percentile_filter(db[::step], 90, size=max(3, int(win_s / (hop_s * step))), mode="nearest")
    ref = np.maximum(np.repeat(ref, step)[:len(db)], np.percentile(db, 60))
    loud = db > ref + rel_db
    v = np.zeros(len(per), bool)
    on = False
    for i in range(len(per)):
        on = (per[i] > per_off) if on else (per[i] > per_on)
        v[i] = on and loud[i]
    return v


def tuning_offset(m, voiced):
    """Global deviation from A440 in semitones (-0.5..0.5): circular mean of the fractional part."""
    # only frames where the pitch is momentarily flat (note centres, not glides)
    slope = np.abs(np.gradient(m))
    ok = voiced & (slope < 0.03)
    if ok.sum() < 50:
        ok = voiced
    frac = m[ok] - np.round(m[ok])
    ang = np.exp(2j * np.pi * frac)
    return float(np.angle(ang.mean()) / (2 * np.pi))


def estimate_key(m, voiced):
    """Major key (tonic pitch class) by Krumhansl profile correlation on the pitch-class histogram."""
    pcs = np.round(m[voiced]).astype(int) % 12
    h = np.bincount(pcs, minlength=12).astype(float)
    scores = [np.corrcoef(np.roll(KRUMHANSL, k), h)[0, 1] for k in range(12)]
    return int(np.argmax(scores))


def smooth_vibrato(m, voiced, win_s=0.17, hop_s=0.01):
    """Median over ~1 vibrato cycle pulls the curve to the note centre, keeps step edges."""
    out = m.copy()
    w = max(3, int(round(win_s / hop_s)) | 1)
    idx = np.flatnonzero(voiced)
    if len(idx) == 0:
        return out
    # filter each voiced run separately so silence does not leak in
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    for r in runs:
        if len(r) >= 3:
            out[r] = median_filter(m[r], size=min(w, len(r) | 1), mode="nearest")
    return out


def viterbi_notes(m, voiced, per, tonic=None, lo=36, hi=88, sigma=0.55,
                  switch_cost=9.0, voice_cost=3.0, offkey_cost=1.0, hop_s=0.01):
    """Frame-wise note labels (MIDI number, or -1 for silence)."""
    pitches = np.arange(lo, hi + 1)
    K, T = len(pitches) + 1, len(m)          # last state = silence
    # emission costs (negative log-likelihood up to constants)
    d = (m[:, None] - pitches[None, :]) / sigma
    em = np.empty((T, K))
    conf = np.clip(per, 0.05, 1.0)[:, None]
    em[:, :-1] = 0.5 * d * d * conf           # unreliable frames pull less
    if tonic is not None:
        inkey = np.isin((pitches - tonic) % 12, MAJOR)
        em[:, :-1] += np.where(inkey, 0.0, offkey_cost)[None, :]
    big = 1e6
    em[:, -1] = np.where(voiced, big, 0.0)
    em[~voiced, :-1] += 2.0                   # a note may bridge short unvoiced gaps, at a price
    # transitions
    step = np.abs(pitches[:, None] - pitches[None, :])
    trans = np.zeros((K, K))
    trans[:-1, :-1] = np.where(step == 0, 0.0, switch_cost + 0.25 * step)
    trans[-1, :-1] = voice_cost
    trans[:-1, -1] = voice_cost
    cost = em[0].copy()
    back = np.zeros((T, K), np.int32)
    for t in range(1, T):
        tot = cost[:, None] + trans
        back[t] = np.argmin(tot, axis=0)
        cost = tot[back[t], np.arange(K)] + em[t]
    path = np.empty(T, np.int32)
    path[-1] = int(np.argmin(cost))
    for t in range(T - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    lab = np.where(path == K - 1, -1, pitches[np.minimum(path, K - 2)])
    return lab


def labels_to_notes(lab, hop_s=0.01, min_dur=0.06):
    notes, i, T = [], 0, len(lab)
    while i < T:
        j = i
        while j < T and lab[j] == lab[i]:
            j += 1
        if lab[i] >= 0 and (j - i) * hop_s >= min_dur:
            notes.append(Note(i * hop_s, j * hop_s, int(lab[i])))
        i = j
    return notes


def absorb_ornaments(lab, hop_s=0.01, max_dur=0.11, max_step=2):
    """Scoops, falls and turn-like blips are not notes on a lead sheet: a very short
    segment touching a longer neighbour within a whole tone is absorbed into it
    (into the following note for scoops, else the preceding one)."""
    lab = lab.copy()
    changed = True
    while changed:
        changed = False
        b = np.flatnonzero(np.diff(lab) != 0) + 1
        starts = np.concatenate([[0], b]); ends = np.concatenate([b, [len(lab)]])
        for k in range(len(starts)):
            p = lab[starts[k]]
            dur = (ends[k] - starts[k]) * hop_s
            if p < 0 or dur > max_dur:
                continue
            nxt = lab[ends[k]] if k + 1 < len(starts) else -1
            prv = lab[starts[k] - 1] if k > 0 else -1
            nd = (ends[k + 1] - starts[k + 1]) * hop_s if k + 1 < len(starts) else 0
            pd = (ends[k - 1] - starts[k - 1]) * hop_s if k > 0 else 0
            if nxt >= 0 and abs(nxt - p) <= max_step and nd > dur:
                lab[starts[k]:ends[k]] = nxt; changed = True; break
            if prv >= 0 and abs(prv - p) <= max_step and pd > dur:
                lab[starts[k]:ends[k]] = prv; changed = True; break
    return lab


# ---------------------------------------------------------------- rhythm grid

def beat_grid(mix_mono, sr, bpm_hint=None):
    """Constant-tempo grid fitted to tracked beats: returns (t_first_beat, beat_period).
    Studio pop is recorded to a click, so a straight line through the beat times is far
    more stable than the raw per-beat estimates."""
    kw = {"start_bpm": bpm_hint} if bpm_hint else {}
    _, beats = librosa.beat.beat_track(y=mix_mono, sr=sr, units="time", tightness=200, **kw)
    k = np.arange(len(beats), dtype=float)
    # robust line fit (iteratively drop outliers)
    keep = np.ones(len(beats), bool)
    for _ in range(5):
        p, t0 = np.polyfit(k[keep], beats[keep], 1)
        res = beats - (t0 + p * k)
        # beats may be skipped/doubled: re-index to nearest integer multiple
        k = np.round((beats - t0) / p)
        keep = np.abs(beats - (t0 + p * k)) < 0.06
    p, t0 = np.polyfit(k[keep], beats[keep], 1)
    t0 = t0 - np.floor(t0 / p) * p            # phase within one beat
    return float(t0), float(p)


def grid_lag(lab, t0, period, div=4, hop_s=0.01):
    """Singers sit behind (or ahead of) the beat.  Find the constant shift of the 16th grid,
    within +-half a slot, for which note changes fall on slot boundaries, i.e. for which
    frames agree best with the majority label of their slot."""
    slot = period / div
    best = (-1.0, 0.0)
    for lag in np.arange(-0.5, 0.5, 0.05) * slot:
        idx = np.floor((np.arange(len(lab)) * hop_s - t0 - lag) / slot).astype(int)
        ok = (idx >= 0) & (lab >= 0)
        key = idx[ok] * 128 + lab[ok]
        _, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
        slots, sinv = np.unique(idx[ok], return_inverse=True)
        maj = np.zeros(len(slots)); np.maximum.at(maj, sinv, cnt[inv])
        score = maj.sum() / ok.sum()
        if score > best[0]:
            best = (score, float(lag))
    return best[1]


def quantise(lab, t0, period, onset_env=None, div=4, hop_s=0.01, min_fill=0.45,
             onset_thresh=None, legato_slots=2):
    """Vote frame labels into 1/div-beat slots; merge runs; split at onsets.
    legato_slots: a singer clips note ends for breath/consonants where the score keeps the
    note sounding, so a silence of up to this many slots *inside a phrase* is given back to
    the preceding note."""
    slot = period / div
    nslots = int((len(lab) * hop_s - t0) / slot)
    sl = np.full(nslots, -1, int)
    for s in range(nslots):
        a = int(round((t0 + s * slot) / hop_s)); b = int(round((t0 + (s + 1) * slot) / hop_s))
        seg = lab[a:b]
        if len(seg) == 0:
            continue
        v = seg[seg >= 0]
        if len(v) >= min_fill * len(seg):
            vals, cnt = np.unique(v, return_counts=True)
            sl[s] = vals[np.argmax(cnt)]
    filled = np.zeros(nslots, bool)
    s = 0
    while s < nslots and legato_slots:
        if sl[s] < 0:
            s += 1; continue
        e = s
        while e < nslots and sl[e] == sl[s]:
            e += 1
        g = e
        while g < nslots and sl[g] < 0:
            g += 1
        if g < nslots and 0 < g - e <= legato_slots:
            sl[e:g] = sl[s]; filled[e:g] = True
        s = g if g > e else e
    notes, s = [], 0
    while s < nslots:
        if sl[s] < 0:
            s += 1; continue
        e = s + 1
        while e < nslots and sl[e] == sl[s]:
            if onset_env is not None and onset_thresh is not None and not filled[e]:
                a = int(round((t0 + e * slot) / hop_s))
                w = onset_env[max(0, a - 4): a + 5]
                if len(w) and w.max() > onset_thresh:
                    break
            e += 1
        notes.append(Note(t0 + s * slot, t0 + e * slot, int(sl[s]), s, e - s))
        s = e
    return notes, sl
