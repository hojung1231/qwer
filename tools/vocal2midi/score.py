"""Reference-score parsing and evaluation of a quantised transcription against it."""
from __future__ import annotations
import re
import numpy as np

META_DEFAULT = {"div": 4, "bar": 16}
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def name_to_midi(s: str) -> int:
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", s)
    return _PC[m[1]] + {"#": 1, "b": -1, "": 0}[m[2]] + 12 * (int(m[3]) + 1)


def load_reference(path):
    """Returns (first_measure, slots, onsets): slots[i] = frozenset of accepted MIDI pitches
    for 16th-slot i (empty set = rest); onsets[i] = True where a new note is attacked."""
    slots, onsets, first, sure = [], [], None, []
    meta = dict(META_DEFAULT)
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
        if not line.strip():
            continue
        if line.startswith("@"):                      # "@div 3" = slots per beat, "@bar 12" = slots per bar
            k, v = line[1:].split(); meta[k] = int(v)
            continue
        meas, body = line.split(":", 1)
        unsure = meas.strip().startswith("?")
        meas = meas.strip().lstrip("?")
        first = int(meas) if first is None else first
        for tok in body.split():
            p, n = tok.rsplit(":", 1)
            tied = p.startswith("~"); p = p.lstrip("~")
            ps = frozenset() if p == "r" else frozenset(name_to_midi(x) for x in p.split("|"))
            for k in range(int(n)):
                slots.append(ps); onsets.append(bool(ps) and k == 0 and not tied); sure.append(not unsure)
    return first, slots, np.array(onsets), np.array(sure), meta


def evaluate(pred_slots, ref_slots, ref_onsets, pred_onsets=None, search=None, sure=None):
    """Slide the reference along the predicted slot sequence (the bar offset of the excerpt
    in the recording is unknown) and try octave shifts; report the best alignment."""
    n = len(ref_slots)
    ref_voiced = np.array([bool(s) for s in ref_slots])
    cands = []
    rng = search if search is not None else range(0, len(pred_slots) - n)
    for off in rng:
        seg = pred_slots[off: off + n]
        if len(seg) < n:
            break
        for octv in (-12, 0, 12):
            hit = sum(1 for i in range(n) if ref_voiced[i] and (seg[i] - octv) in ref_slots[i])
            cands.append((hit, off, octv))
    top = max(c[0] for c in cands)
    # a repeated section (2nd verse) matches about as well; the score's bar numbers refer
    # to the first time through, so take the earliest alignment that is nearly as good
    best = min((c for c in cands if c[0] >= 0.85 * top), key=lambda c: c[1])
    later = sorted({c[1] for c in cands if c[0] >= 0.85 * top and c[1] - best[1] >= n})
    hit, off, octv = best
    seg = np.asarray(pred_slots[off: off + n])
    pv = seg >= 0
    res = {
        "slot_offset": off, "octave_shift": octv, "repeat_offsets": later[:3],
        "pitch_acc": hit / ref_voiced.sum(),                       # correct pitch on sung slots
        "voicing_acc": float((pv == ref_voiced).mean()),           # note vs rest agreement
        "overall_acc": float(np.mean([(seg[i] - octv) in ref_slots[i] if ref_voiced[i] else seg[i] < 0
                                      for i in range(n)])),
        "chroma_acc": sum(1 for i in range(n) if ref_voiced[i] and pv[i] and
                          any((seg[i] - p) % 12 == 0 for p in ref_slots[i])) / ref_voiced.sum(),
    }
    if sure is not None and not sure.all():
        k = ref_voiced & sure
        res["pitch_acc_clear_bars"] = sum(1 for i in np.flatnonzero(k) if (seg[i] - octv) in ref_slots[i]) / k.sum()
        res["pitch_acc_tol1_clear_bars"] = sum(1 for i in np.flatnonzero(k) if any(
            0 <= i + d < n and (seg[i + d] - octv) in ref_slots[i] for d in (-1, 0, 1))) / k.sum()
    # same, but forgiving one 16th of early/late phrasing
    res["pitch_acc_tol1"] = sum(1 for i in range(n) if ref_voiced[i] and any(
        0 <= i + d < n and (seg[i + d] - octv) in ref_slots[i] for d in (-1, 0, 1))) / ref_voiced.sum()
    if pred_onsets is not None:
        po = np.asarray(pred_onsets[off: off + n])
        ro = ref_onsets
        tp = 0
        used = set()
        for i in np.flatnonzero(ro):
            for j in (i, i - 1, i + 1):
                if 0 <= j < n and po[j] and j not in used and (seg[j] - octv) in ref_slots[i]:
                    tp += 1; used.add(j); break
        prec = tp / max(1, po.sum()); rec = tp / max(1, ro.sum())
        res.update(note_precision=prec, note_recall=rec,
                   note_f1=2 * prec * rec / max(1e-9, prec + rec))
    return res


def midi_name(p):
    return ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][p % 12] + str(p // 12 - 1)


def side_by_side(pred_slots, ref_slots, off, octv, first_measure, bar=16):
    out = []
    for b in range(len(ref_slots) // bar):
        r = ref_slots[b * bar:(b + 1) * bar]
        p = pred_slots[off + b * bar: off + (b + 1) * bar]
        rs = " ".join((midi_name(min(s)) if s else "--").ljust(3) for s in r)
        ps = " ".join((midi_name(x - octv) if x >= 0 else "--").ljust(3) for x in p)
        mk = " ".join(("   " if ((x - octv) in s if s else x < 0) else "^^^") for s, x in zip(r, p))
        out.append(f"m{first_measure + b:<3} ref  {rs}\n     pred {ps}\n          {mk}")
    return "\n".join(out)
