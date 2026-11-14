#!/usr/bin/env python3
"""Backing-vocal harmony for an extracted melody.

    python3 harmony.py <vocal2midi out_dir> <original audio> [--only A|B|C]

How pop/ballad harmony lines are usually written (the rules implemented here):
  * A harmony voice moves in the lead's rhythm and sings the same words, a 3rd away:
    a diatonic 3rd above (bright) or a 3rd below / 6th below (warm, sits under the lead).
  * "3rd" is counted in scale steps, so it is sometimes major and sometimes minor.
  * On notes that are held or land on a beat, the harmony must agree with the chord
    underneath: if the scale 3rd is not a chord tone it is moved to the nearest chord tone
    (which turns some 3rds into 4ths).  Short passing notes just keep the parallel 3rd.
  * A good single harmony voice is not a shadow of the lead.  It picks the side that keeps it
    in a singable register (below a high hook, above a low line), prefers 3rds and 6ths but
    takes a 4th or 5th when that is the chord tone, moves by step, holds a note while the lead
    moves through passing notes (oblique motion), answers a rising lead by falling (contrary
    motion), and avoids running in parallel 4ths/5ths.
  * Arrangers do not harmonise everything: verses stay solo, the voice joins for the end of
    each phrase as the song builds, and sings whole phrases only on the hook.

Versions:  A = 3rd above throughout,  B = 3rd below throughout,
           C = one arranged voice: `smart_line` chooses every note by the rules above.

The harmony is rendered with the singer's own isolated voice: WORLD re-synthesises it with the
F0 moved by the harmony interval of the note being sung, so words, timing, vibrato and timbre
stay and only the pitch changes.
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
import librosa, mido, soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate, notes as N

MAJOR = [0, 2, 4, 5, 7, 9, 11]
NAMES = N.NAMES


# ------------------------------------------------------------------ inputs
def load_melody(out_dir):
    rep = json.load(open(os.path.join(out_dir, "report.json")))
    org = rep["midi_origin_s"]
    t, on, ns = 0.0, {}, []
    for msg in mido.MidiFile(os.path.join(out_dir, "melody_quantised.mid")):
        t += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            on[msg.note] = t
        elif msg.type in ("note_off", "note_on") and msg.note in on:
            a = on.pop(msg.note); ns.append((a + org, t - a, msg.note))
    return rep, np.array(sorted(ns))                       # rows: start (audio s), duration, MIDI pitch


# ------------------------------------------------------------------ chords from the accompaniment
def estimate_chords(mix_mono, vocal_mono, sr, t_bar1, beat, tonic, beats_per_chord=2):
    """One major/minor triad per half bar, from the chroma of (mix - vocal)."""
    n = min(len(mix_mono), len(vocal_mono))
    acc = mix_mono[:n] - vocal_mono[:n]
    acc = librosa.effects.harmonic(acc, margin=3.0)
    hop = 2048
    chroma = librosa.feature.chroma_cqt(y=acc, sr=sr, hop_length=hop, bins_per_octave=36)
    # bass chroma (below ~260 Hz) tells the root apart from its relatives
    bass = librosa.feature.chroma_cqt(y=acc, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=3, bins_per_octave=36)
    seg = beat * beats_per_chord
    first = t_bar1 - np.ceil(t_bar1 / seg) * seg
    nseg = int((n / sr - first) / seg)
    ft = np.arange(chroma.shape[1]) * hop / sr
    C = np.zeros((nseg, 12)); B = np.zeros((nseg, 12))
    for s in range(nseg):
        k = (ft >= first + s * seg) & (ft < first + (s + 1) * seg)
        if k.any():
            C[s] = chroma[:, k].mean(1); B[s] = bass[:, k].mean(1)
    # 24 triad templates, scored by treble fit + bass on the root
    T = []; lab = []
    for r in range(12):
        for q, iv in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            v = np.zeros(12); v[[(r + i) % 12 for i in iv]] = 1
            T.append(v / np.linalg.norm(v)); lab.append((r, q))
    T = np.array(T)
    Cn = C / (np.linalg.norm(C, axis=1, keepdims=True) + 1e-9); Bn = B / (B.sum(1, keepdims=True) + 1e-9)
    score = Cn @ T.T + 0.6 * Bn[:, [r for r, _ in lab]]
    # vocabulary of a major-key pop song: the six diatonic triads, plus (at a price) the usual
    # borrowed ones - secondary dominants II, III, VI, the flat VII and the minor iv
    diatonic = {((tonic + d) % 12, q) for d, q in ((0, ""), (2, "m"), (4, "m"), (5, ""), (7, ""), (9, "m"))}
    borrowed = {((tonic + d) % 12, q) for d, q in ((2, ""), (4, ""), (9, ""), (10, ""), (5, "m"))}
    score += np.array([0.15 if c in diatonic else (0.0 if c in borrowed else -1.0) for c in lab])[None, :]
    # Viterbi: chords tend to last
    K = len(lab); cost = -score; stay = 0.12
    dp = cost[0].copy(); bk = np.zeros((nseg, K), int)
    for s in range(1, nseg):
        tr = dp[:, None] + stay * (1 - np.eye(K)); bk[s] = tr.argmin(0); dp = tr.min(0) + cost[s]
    path = [int(dp.argmin())]
    for s in range(nseg - 1, 0, -1):
        path.append(bk[s, path[-1]])
    path = path[::-1]
    return [(first + s * seg, seg, lab[p][0], lab[p][1]) for s, p in enumerate(path)]


def chord_at(chords, t):
    t0, seg = chords[0][0], chords[0][1]
    i = int(np.clip((t - t0) // seg, 0, len(chords) - 1))
    return chords[i]


def chord_tones(ch):
    _, _, r, q = ch
    return {(r) % 12, (r + (3 if q == "m" else 4)) % 12, (r + 7) % 12}


# ------------------------------------------------------------------ writing the harmony line
def scale_step(p, tonic, steps):
    """Move pitch p by `steps` scale degrees of the major key (chromatic notes use the degree below)."""
    pc = (p - tonic) % 12
    deg = max(i for i, s in enumerate(MAJOR) if s <= pc)
    extra = pc - MAJOR[deg]
    d2 = deg + steps
    return p - pc + 12 * (d2 // 7) + MAJOR[d2 % 7] + extra


def harmony_line(mel, chords, tonic, beat, direction=+1, strict_s=None):
    """direction +1: voice above the lead, -1: below.  Returns one harmony pitch per melody note."""
    strict_s = strict_s or 0.9 * beat          # notes at least this long must be chord tones
    out, prev = [], None
    for (t, d, p) in mel:
        p = int(p)
        h = scale_step(p, tonic, 2 * direction)
        tones = chord_tones(chord_at(chords, t + min(d, beat) * 0.5))
        if d >= strict_s and (h % 12) not in tones:
            # nearest chord tone on the same side, a 3rd..5th from the lead (not a 2nd, not a unison)
            # (if there is none - the lead is on a 7th or 9th of the chord - the scale 3rd stays)
            cand = [p + direction * k for k in (3, 4, 5) if ((p + direction * k) % 12) in tones]
            if cand:
                ref = prev if prev is not None else h
                h = min(cand, key=lambda c: (abs(c - h) > 2, abs(c - ref)))
        out.append(h); prev = h
    return np.array(out)


def sections(mel, beat):
    """Phrase-level register tells verse from hook without a score: the hook is where the melody
    sits highest.  Returns per-note labels 0 = solo, 1 = one harmony voice, 2 = full stack."""
    t, p = mel[:, 0], mel[:, 2]
    gaps = np.flatnonzero(np.diff(t) - mel[:-1, 1] > 1.0 * beat) + 1          # a rest of a beat ends a phrase
    lab = np.zeros(len(mel), int)
    lo, hi = np.percentile(p, 30), np.percentile(p, 75)
    for idx in np.split(np.arange(len(mel)), gaps):
        w = mel[idx, 1]; reg = np.average(p[idx], weights=w)
        lab[idx] = 2 if reg >= hi - 1 else (1 if reg >= lo + 2 else 0)
    return lab


def phrases(mel, beat):
    """Index arrays of the notes of each phrase (a rest of a beat or more ends a phrase)."""
    gaps = np.flatnonzero(mel[1:, 0] - (mel[:-1, 0] + mel[:-1, 1]) > 1.0 * beat) + 1
    return np.split(np.arange(len(mel)), gaps)


def smart_line(mel, chords, tonic, beat):
    """One harmony voice chosen note by note with dynamic programming.

    Every scale (or chord) tone a 3rd to a 6th away from the lead, above or below, is a
    candidate.  A path through the candidates is scored on how each note sounds against the
    lead and the chord, and on how the voice moves from note to note; Viterbi finds the best.
    Returns the harmony pitch per melody note, 0 where the voice rests."""
    p = mel[:, 2].astype(int); t = mel[:, 0]; d = mel[:, 1]
    scale = {(tonic + x) % 12 for x in MAJOR}
    # comfortable register for the same singer: roughly the lead's own range
    lo_r, hi_r = np.percentile(p, 5) - 3, np.percentile(p, 92) + 1
    IV = {3: 0.0, 4: 0.0, 8: 0.25, 9: 0.25, 5: 0.7, 7: 1.1}        # 3rds, 6ths, 4th, 5th
    sec = sections(mel, beat)
    out = np.zeros(len(mel), int)
    prev_side = 0
    for idx in phrases(mel, beat):
        if sec[idx[0]] == 0:
            prev_side = 0
            continue                                                 # verse: lead alone
        cands, costs = [], []
        for n, i in enumerate(idx):
            ch = chord_at(chords, t[i] + min(d[i], beat) * 0.5); tones = chord_tones(ch)
            seventh = (ch[2] + (10 if ch[3] == "m" or (ch[2] - tonic) % 12 == 7 else 11)) % 12
            structural = d[i] >= 0.9 * beat or n == len(idx) - 1     # held notes and phrase endings
            w = float(np.clip(d[i] / beat, 0.3, 2.0))
            cs, cc = [], []
            for side in (+1, -1):
                for k, base in IV.items():
                    h = p[i] + side * k; pc = h % 12
                    if pc not in scale:
                        continue                                     # stay in the key: a wrongly guessed
                                                                     # borrowed chord must not pull the voice out
                    c = base
                    if pc not in tones:
                        c += (0.5 if pc == seventh else 1.6) if structural else 0.3
                    elif k in (5, 7):
                        c -= 0.3                                     # a 4th/5th is fine when it is the chord tone
                    if n == len(idx) - 1 and k not in (3, 4, 8, 9):
                        c += 0.6                                     # end a phrase on a sweet interval
                    c += 0.12 * max(0.0, h - hi_r) + 0.10 * max(0.0, lo_r - h)
                    cs.append((h, side, k)); cc.append(c * w)
            cands.append(cs); costs.append(np.array(cc))
        # Viterbi over the phrase
        dp = costs[0] + np.array([0.3 if (prev_side and sd != prev_side) else 0.0 for _, sd, _ in cands[0]])
        back = []
        for n in range(1, len(idx)):
            lead_move = p[idx[n]] - p[idx[n - 1]]
            tr = np.zeros((len(cands[n - 1]), len(cands[n])))
            for a_, (h0, s0, k0) in enumerate(cands[n - 1]):
                for b_, (h1, s1, k1) in enumerate(cands[n]):
                    m = h1 - h0; am = abs(m)
                    c = 0.0 if am <= 2 else (0.35 if am <= 4 else (0.9 if am <= 7 else 2.2))
                    if s0 != s1:
                        c += 2.5                                     # do not hop over the lead mid-phrase
                    if lead_move != 0 and m == 0:
                        c -= 0.30                                    # oblique: hold while the lead moves
                    elif lead_move * m < 0:
                        c -= 0.20                                    # contrary motion
                    if lead_move == 0 and m != 0:
                        c += 0.4                                     # lead repeats a note: stay with it
                    if k0 in (5, 7) and k1 == k0 and lead_move != 0:
                        c += 1.5                                     # parallel 4ths / 5ths
                    tr[a_, b_] = c
            tot = dp[:, None] + tr
            back.append(tot.argmin(0)); dp = tot.min(0) + costs[n]
        j = int(dp.argmin()); path = [j]
        for bk in reversed(back):
            j = int(bk[j]); path.append(j)
        path = path[::-1]
        line = np.array([cands[n][j][0] for n, j in enumerate(path)])
        prev_side = cands[-1][path[-1]][1]
        if sec[idx[0]] == 1:
            # building sections: the voice only joins for the back half of the phrase
            mid = 0.5 * (t[idx[0]] + t[idx[-1]] + d[idx[-1]])
            line = np.where(t[idx] >= mid - 1e-6, line, 0)
            if not line.any():
                line[-1] = cands[-1][path[-1]][0]
        out[idx] = line
    return out


# ------------------------------------------------------------------ rendering with the singer's voice
class Voice:
    """WORLD analysis of the vocal, done once; `shifted` re-synthesises it with F0 moved per note."""
    def __init__(self, vocal, sr):
        import pyworld as pw
        self.pw, self.sr, self.x = pw, sr, vocal.astype(np.float64)
        f0, self.tt = pw.dio(self.x, sr, f0_floor=70.0, f0_ceil=1000.0, frame_period=5.0)
        self.f0 = pw.stonemask(self.x, f0, self.tt, sr)
        self.sp = pw.cheaptrick(self.x, self.f0, self.tt, sr); self.ap = pw.d4c(self.x, self.f0, self.tt, sr)

    def shifted(self, mel, interval_semitones):
        tt = self.tt
        shift = np.zeros(len(tt)); gain = np.zeros(len(tt))
        for (t, d, _), iv in zip(mel, interval_semitones):
            if iv == 0:
                continue
            k = (tt >= t - 0.03) & (tt < t + d + 0.03)
            shift[k] = iv; gain[k] = 1.0
        ker = np.hanning(13); ker /= ker.sum()                  # short ramps: no clicks at entries
        gain = np.convolve(gain, ker, mode="same")
        for i in range(1, len(shift)):                          # carry the last interval through gaps
            if shift[i] == 0:
                shift[i] = shift[i - 1]
        y = self.pw.synthesize(self.f0 * 2.0 ** (shift / 12.0), self.sp, self.ap, self.sr, 5.0)[:len(self.x)]
        return (y * np.interp(np.arange(len(y)) / self.sr, tt, gain)).astype(np.float32)

    def from_score(self, mel, pitches, tuning_cents=0.0, glide_s=0.06, vib_cents=18.0, vib_hz=5.5):
        """Sing the written harmony notes with the singer's timbre and words.

        Only the spectral envelope (timbre, vowels, consonants) and the voiced/unvoiced
        pattern are taken from the recording; the pitch comes from the score: each note is
        held at its exact pitch, joined to the next by a short glide, with a light vibrato
        that fades in on held notes so it does not sound like a machine."""
        tt = self.tt; dt = tt[1] - tt[0]
        target = np.zeros(len(tt)); gain = np.zeros(len(tt)); vib = np.zeros(len(tt))
        for (t, d, _), h in zip(mel, pitches):
            if h <= 0:
                continue
            k = (tt >= t - 0.03) & (tt < t + d + 0.03)
            target[k] = h + tuning_cents / 100.0; gain[k] = 1.0
            age = tt[k] - t                                         # vibrato grows in after 0.3 s
            vib[k] = np.clip((age - 0.3) / 0.4, 0.0, 1.0) * np.sin(2 * np.pi * vib_hz * age) * vib_cents / 100.0
        for i in range(1, len(target)):                             # fill gaps so glides have two ends
            if target[i] == 0:
                target[i] = target[i - 1]
        first = np.flatnonzero(target)
        if len(first):
            target[:first[0]] = target[first[0]]
        w = max(3, int(glide_s / dt) | 1); ker = np.hanning(w + 2)[1:-1]; ker /= ker.sum()
        target = np.convolve(np.pad(target, w // 2, mode="edge"), ker, mode="valid") + vib
        ker = np.hanning(13); ker /= ker.sum(); gain = np.convolve(gain, ker, mode="same")
        f0 = np.where(self.f0 > 0, 440.0 * 2.0 ** ((target - 69.0) / 12.0), 0.0)
        y = self.pw.synthesize(f0, self.sp, self.ap, self.sr, 5.0)[:len(self.x)]
        return (y * np.interp(np.arange(len(y)) / self.sr, tt, gain)).astype(np.float32)


def write_midi(path, mel, lines, bpm, origin, div):
    tpb = 480; q_bpm = bpm * (1.5 if div % 3 == 0 else 1.0)
    mid = mido.MidiFile(ticks_per_beat=tpb)
    for ti, (name, pitches) in enumerate([("Lead", mel[:, 2])] + lines):
        tr = mido.MidiTrack(); mid.tracks.append(tr)
        tr.append(mido.MetaMessage("track_name", name=name, time=0))
        if ti == 0:
            tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(q_bpm), time=0))
        tr.append(mido.Message("program_change", program=52 if ti else 54, channel=ti, time=0))
        ev = []
        for (t, d, _), p in zip(mel, pitches):
            if p <= 0:
                continue
            a = int(round((t - origin) * q_bpm / 60 * tpb)); b = int(round((t + d - origin) * q_bpm / 60 * tpb))
            if a >= 0 and b > a:
                ev += [(a, 1, int(p)), (b, 0, int(p))]
        ev.sort(); now = 0
        for tick, on, p in ev:
            tr.append(mido.Message("note_on" if on else "note_off", note=p, velocity=80 if on else 0, channel=ti, time=tick - now)); now = tick
    mid.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir"); ap.add_argument("audio")
    ap.add_argument("--only", default="ABC"); ap.add_argument("--name", default="harmony")
    ap.add_argument("--pitch-source", choices=["voice", "score"], default="voice",
                    help="voice: move the singer's own pitch curve by the interval; "
                         "score: sing the written harmony notes at exact pitch (singer's timbre and words kept)")
    ap.add_argument("--harmony-db", type=float, default=-5.0, help="level of each harmony voice relative to the lead")
    a = ap.parse_args()
    sr = 44100
    rep, mel = load_melody(a.out_dir)
    beat = 60.0 / rep["bpm"]; div = rep.get("slots_per_beat", 4); tonic = NAMES.index(rep["key"].split()[0])
    stereo = isolate.decode(a.audio, sr); mix = stereo.mean(0)
    vocal, _ = librosa.load(os.path.join(a.out_dir, "vocal.wav"), sr=sr)
    chords = estimate_chords(mix, vocal, sr, rep["midi_origin_s"], beat, tonic)
    json.dump([[round(t, 3), NAMES[r] + q] for t, _, r, q in chords], open(os.path.join(a.out_dir, a.name + "_chords.json"), "w"))
    up = harmony_line(mel, chords, tonic, beat, +1); dn = harmony_line(mel, chords, tonic, beat, -1)
    sec = sections(mel, beat)
    versions = {
        "A": [("3rd above", up)],
        "B": [("3rd below", dn)],
        "C": [("arranged single voice", smart_line(mel, chords, tonic, beat))],
    }
    g = 10 ** (a.harmony_db / 20)
    voice = Voice(vocal, sr)
    for v in a.only:
        lines = versions[v]
        if a.pitch_source == "score":
            parts = [voice.from_score(mel, p, rep.get("tuning_cents", 0.0)) for _, p in lines]
        else:
            parts = [voice.shifted(mel, np.where(p > 0, p - mel[:, 2], 0)) for _, p in lines]
        n = min(stereo.shape[1], len(parts[0])); voices = sum(parts)
        # harmony voices sit a little to the sides, as backing vocals are usually mixed
        outp = stereo[:, :n].copy()
        pans = [(0.8, 1.0)] if len(parts) == 1 else [(1.0, 0.5), (0.5, 1.0)]
        for part, (gl, gr) in zip(parts, pans):
            outp[0] += g * gl * part[:n]; outp[1] += g * gr * part[:n]
        outp *= min(1.0, 0.98 / np.abs(outp).max())
        base = os.path.join(a.out_dir, f"{a.name}_{v}")
        sf.write(base + ".wav", outp.T, sr)
        sf.write(base + "_voices_only.wav", (g * voices[:n]), sr)
        write_midi(base + ".mid", mel, lines, rep["bpm"], rep["midi_origin_s"], div)
        print(v, [(nm, int((p > 0).sum())) for nm, p in lines])
    print("chords:", " ".join(NAMES[r] + q for _, _, r, q in chords[:48]))
    print("sections (0 solo / 1 one voice / 2 stack):", np.bincount(sec, minlength=3))


if __name__ == "__main__":
    main()
