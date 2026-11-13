#!/usr/bin/env python3
"""Sung melody (mp3/wav) -> MIDI.

    python3 vocal2midi.py song.mp3 -o out_dir [--reference reference_score.txt]

Pipeline:  decode -> isolate vocal -> F0 (CREPE) -> tuning/key -> vibrato-robust
HMM note decoding -> beat grid -> 16th quantisation -> MIDI (+ evaluation report).
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
import librosa, mido

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate, pitch, notes as N, score as S


def write_midi(path, notes, bpm, t_origin=0.0, transpose=0, program=52):
    """Tempo-mapped single-track MIDI; time 0 of the file = t_origin seconds of the audio."""
    tpb = 480
    mid = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    tr.append(mido.Message("program_change", program=program, time=0))
    ev = []
    for n in notes:
        a = int(round((n.start - t_origin) * bpm / 60 * tpb)); b = int(round((n.end - t_origin) * bpm / 60 * tpb))
        if a < 0 or b <= a:
            continue
        ev.append((a, 1, n.pitch + transpose)); ev.append((b, 0, n.pitch + transpose))
    ev.sort()
    now = 0
    for tick, on, p in ev:
        tr.append(mido.Message("note_on" if on else "note_off", note=int(p), velocity=90 if on else 0,
                               time=tick - now))
        now = tick
    mid.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--separator", choices=["auto", "demucs", "center"], default="auto")
    ap.add_argument("--bpm-hint", type=float, default=None, help="tempo printed on the score, if known")
    ap.add_argument("--key", default=None, help="tonic of the major key, e.g. E (default: estimated)")
    ap.add_argument("--transpose", type=int, default=0,
                    help="semitones added on output (12 = write a male voice at lead-sheet octave)")
    ap.add_argument("--reference", default=None, help="reference score file to evaluate against")
    ap.add_argument("--cache", action="store_true", help="reuse vocal/F0 from a previous run in --out")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sr = 44100
    f0_path = os.path.join(a.out, "f0.npz")

    stereo = isolate.decode(a.audio, sr)
    mono = stereo.mean(0)
    if a.cache and os.path.exists(f0_path):
        z = np.load(f0_path); t, f0, per, rms = z["t"], z["f0"], z["per"], z["rms"]; sep = str(z["sep"])
        vocal, _ = librosa.load(os.path.join(a.out, "vocal.wav"), sr=sr)
    else:
        vocal, sep = isolate.isolate(stereo, sr, a.separator)
        import soundfile as sf
        sf.write(os.path.join(a.out, "vocal.wav"), vocal, sr)
        t, f0, per, rms = pitch.track(vocal, sr)
        np.savez(f0_path, t=t, f0=f0, per=per, rms=rms, sep=sep)

    voiced = N.voicing(per, rms)
    m = N.hz_to_midi_f(f0)
    ms = N.smooth_vibrato(m, voiced)          # vibrato flattened first, so tuning sees note centres
    tune = N.tuning_offset(ms, voiced)
    ms = ms - tune
    tonic = N.NAMES.index(a.key) if a.key else N.estimate_key(ms, voiced)
    lab = N.viterbi_notes(ms, voiced, per, tonic=tonic)
    lab = N.absorb_ornaments(lab)
    raw_notes = N.labels_to_notes(lab)

    t0, period = N.beat_grid(mono, sr, a.bpm_hint)
    bpm = 60.0 / period
    v16 = librosa.resample(vocal, orig_sr=sr, target_sr=16000)
    oenv = librosa.onset.onset_strength(y=v16, sr=16000, hop_length=160)
    oth = float(np.percentile(oenv, 90))
    lag = N.grid_lag(lab, t0, period)
    qnotes, slots = N.quantise(lab, t0 + lag, period, oenv, onset_thresh=oth)

    info = {"separator": sep, "tuning_cents": round(100 * tune, 1), "key": N.NAMES[tonic] + " major",
            "bpm": round(bpm, 3), "first_beat_s": round(t0, 4), "vocal_lag_ms": round(1000 * lag),
            "raw_notes": len(raw_notes), "quantised_notes": len(qnotes)}

    origin = t0 + lag                      # MIDI time 0; a beat, but the bar phase is unknown...
    octv = 0
    if a.reference:
        first, ref_slots, ref_on, sure = S.load_reference(a.reference)
        pred_on = np.zeros(len(slots), bool)
        for n in qnotes:
            pred_on[n.slot] = True
        ev = S.evaluate(slots, ref_slots, ref_on, pred_on, sure=sure)
        info["evaluation"] = {k: (round(float(v), 4) if not isinstance(v, int) else v) for k, v in ev.items()}
        off, octv = ev["slot_offset"], ev["octave_shift"]
        info["evaluation"]["excerpt_starts_s"] = round(t0 + lag + off * period / 4, 3)
        # ...unless the score tells us where its first bar sits: put bar 1 of the score on bar 1 of the MIDI
        bar1 = off - (first - 1) * 16
        origin = t0 + lag + (bar1 % 16 - (16 if bar1 % 16 else 0) if bar1 < 0 else bar1) * period / 4
        with open(os.path.join(a.out, "comparison.txt"), "w", encoding="utf-8") as f:
            f.write(S.side_by_side(slots, ref_slots, off, octv, first) + "\n")
    info["midi_origin_s"] = round(origin, 3)
    write_midi(os.path.join(a.out, "melody_raw.mid"), raw_notes, bpm, origin, a.transpose)
    write_midi(os.path.join(a.out, "melody_quantised.mid"), qnotes, bpm, origin, a.transpose)
    if octv:
        write_midi(os.path.join(a.out, "melody_quantised_score_octave.mid"), qnotes, bpm, origin, -octv)
    with open(os.path.join(a.out, "report.json"), "w") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
