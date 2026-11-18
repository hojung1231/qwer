"""mp3 -> the data the 화음왕 app needs for one song (a "pack").

    python pipeline.py song.mp3 out.json

Steps: bar/tempo detection -> vocal separation, pitch tracking and note decoding
(tools/vocal2midi) -> harmony lines (3rd above, 3rd below, arranged) -> the harmony sung
with the singer's own voice -> where each lyric line of the file's own lyrics is sung.
"""
from __future__ import annotations
import base64, json, math, os, re, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
V2M = os.path.normpath(os.path.join(HERE, "..", "..", "tools", "vocal2midi"))
sys.path.insert(0, V2M)
PER_BUNDLE = 4                       # lyric lines per bundle: must match the app


# ------------------------------------------------------------------ lyrics kept in the file
def tags(mp3):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", mp3],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        t = json.loads(out).get("format", {}).get("tags", {})
    except Exception:
        t = {}
    low = {k.lower(): v for k, v in t.items()}
    lyr = next((v for k, v in low.items() if "lyric" in k), "")
    return low.get("title", ""), low.get("artist", ""), [l.strip() for l in lyr.replace("\r", "").split("\n") if l.strip()]


def syllables(line):
    n = 0
    for m in re.finditer(r"[가-힣]|[A-Za-z’']+|\d+", line):
        w = m.group(0)
        if "가" <= w[0] <= "힣" or w[0].isdigit():
            n += 1
        else:
            v = len(re.findall(r"[aeiouy]+", w.lower()))
            if w.lower().endswith("e") and v > 1 and not w.lower().endswith(("le", "ee")):
                v -= 1
            n += max(1, v)
    return max(1, n)


def align(ns, syl, beat, c_skip=0.7, w_cnt=1.0, w_gap=1.5, w_b=0.8):
    """Lay lyric lines over the notes: each line takes a run of notes about as long as its
    syllable count, lines begin after pauses, notes with no words (ad libs) may be skipped."""
    N, M = len(ns), len(syl)
    st = np.array([n[0] for n in ns]); en = np.array([n[0] + n[1] for n in ns])
    gap = np.zeros(N + 1); gap[1:N] = np.maximum(0, st[1:] - en[:-1]) / beat; gap[0] = 4; gap[N] = 4
    INF = 1e9; dp = np.full((M + 1, N + 1), INF); bk = np.zeros((M + 1, N + 1, 2), int); dp[0, 0] = 0
    for j in range(M + 1):
        for i in range(N + 1):
            c = dp[j, i]
            if c >= INF:
                continue
            if i < N and c + c_skip < dp[j, i + 1]:
                dp[j, i + 1] = c + c_skip; bk[j, i + 1] = (j, i)
            if j < M:
                s = syl[j]; g = 0.0
                for k in range(1, min(N - i, int(2.5 * s) + 3) + 1):
                    if k > 1:
                        g += max(0.0, gap[i + k - 1] - 0.5)
                    if k < max(1, int(s / 2.5)):
                        continue
                    cost = w_cnt * abs(k - s) / math.sqrt(s) + w_gap * g - w_b * min(gap[i], 2.0) - 0.3 * w_b * min(gap[i + k], 2.0)
                    if c + cost < dp[j + 1, i + k]:
                        dp[j + 1, i + k] = c + cost; bk[j + 1, i + k] = (j, i)
    if dp[M].min() >= INF:
        return None                                  # more words than the notes can carry
    j, i = M, int(np.argmin(dp[M])); segs = []
    while (j, i) != (0, 0):
        pj, pi = bk[j, i]
        if pj == j - 1:
            segs.append((pj, pi, i))
        j, i = pj, pi
    return segs[::-1]


# ------------------------------------------------------------------ the whole job
def build(mp3, work, progress=lambda p, msg="": None, name=None):
    import soundfile as sf
    os.makedirs(work, exist_ok=True)
    progress(1, "박자 찾는 중")
    import bars
    b = bars.find_bars(mp3)
    div = 3 if b["beat_subdivision"] == 3 else 4
    length = sf.info(_wav(mp3, work)).duration

    # separation + pitch + notes run as the existing tool, in its own process
    for f in ("report.json", "f0.npz", "vocal.wav"):
        if os.path.exists(os.path.join(work, f)):
            os.remove(os.path.join(work, f))
    log = open(os.path.join(work, "vocal2midi.log"), "w", encoding="utf-8")
    p = subprocess.Popen([sys.executable, os.path.join(V2M, "vocal2midi.py"), mp3, "-o", work, "--div", str(div),
                          "--bpm-hint", str(b["bpm"])], stdout=log, stderr=subprocess.STDOUT)
    stages = [("vocal.wav", 3, 50, "목소리 분리 중"), ("f0.npz", 50, 70, "음정 읽는 중"), ("report.json", 70, 76, "음표로 옮기는 중")]
    t0 = time.time(); si = 0
    while p.poll() is None:
        while si < len(stages) - 1 and os.path.exists(os.path.join(work, stages[si][0])):
            si += 1; t0 = time.time()
        _, lo, hi, msg = stages[si]
        progress(lo + (hi - lo) * (1 - math.exp(-(time.time() - t0) / max(20.0, 0.35 * length))), msg)
        time.sleep(1.0)
    log.close()
    if p.returncode != 0 or not os.path.exists(os.path.join(work, "report.json")):
        tail = open(os.path.join(work, "vocal2midi.log"), encoding="utf-8", errors="replace").read()[-600:]
        raise RuntimeError("멜로디 추출 실패: " + tail)

    progress(77, "화음 만드는 중")
    import librosa, harmony as H, isolate, notes as N
    sr = 44100
    rep, mel = H.load_melody(work)
    if len(mel) < 8:
        raise RuntimeError("노래하는 목소리를 찾지 못했습니다")
    beat = 60.0 / rep["bpm"]; tonic = H.NAMES.index(rep["key"].split()[0])
    stereo = isolate.decode(mp3, sr); mix = stereo.mean(0)
    vocal, _ = librosa.load(os.path.join(work, "vocal.wav"), sr=sr)
    chords = H.estimate_chords(mix, vocal, sr, rep["midi_origin_s"], beat, tonic)
    lines = {"up": H.harmony_line(mel, chords, tonic, beat, +1), "down": H.harmony_line(mel, chords, tonic, beat, -1),
             "arranged": H.smart_line(mel, chords, tonic, beat)}

    progress(80, "화음 목소리 만드는 중")
    z = np.load(os.path.join(work, "f0.npz"))
    voice = H.Voice(vocal, sr, (z["t"], z["f0"], N.voicing(z["per"], z["rms"], rel_db=-18.0)))
    harm = {}
    for k, (key, pitches) in enumerate(lines.items()):
        y = voice.from_score(mel, pitches, rep.get("tuning_cents", 0.0)) * 10 ** (-5.0 / 20)
        wav = os.path.join(work, f"harm_{key}.wav"); out = os.path.join(work, f"harm_{key}.mp3")
        sf.write(wav, y, sr)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-b:a", "48k", out], check=True)
        harm[key] = "data:audio/mpeg;base64," + base64.b64encode(open(out, "rb").read()).decode()
        os.remove(wav)
        progress(80 + 5 * (k + 1), "화음 목소리 만드는 중")

    progress(96, "가사 맞추는 중")
    title, artist, lyr = tags(mp3)
    notes = [(float(t), float(d), int(m)) for t, d, m in mel]
    bundle_times, line_times, cover = [], [], []
    segs = align(notes, [syllables(l) for l in lyr], beat) if lyr else None
    if segs and len(segs) == len(lyr):
        span = [(notes[a][0], notes[e - 1][0] + notes[e - 1][1]) for _, a, e in segs]
        line_times = [round(s, 2) for s, _ in span]
        for i in range(0, len(lyr), PER_BUNDLE):
            part = span[i:i + PER_BUNDLE]
            bundle_times.append([round(max(0.0, part[0][0] - 0.4), 1), round(part[-1][1] + 0.4, 1)])
        arr = lines["arranged"]
        for a, e in bundle_times:
            inside = [arr[k] > 0 for k, n in enumerate(notes) if a <= n[0] < e]
            cover.append(1 if inside and sum(inside) >= 0.3 * len(inside) else 0)
    pack = {"hwaeum": 1, "title": (name or title or os.path.splitext(os.path.basename(mp3))[0]).strip(), "artist": artist,
            "info": {"notes": len(notes), "key": rep["key"].split()[0] + "장조", "bpm": int(round(rep["bpm"])),
                     "sig": "12/8" if div == 3 else "4/4"},
            "mel": [[round(t, 3), round(d, 3), m] for t, d, m in notes],
            "up": [int(x) for x in lines["up"]], "down": [int(x) for x in lines["down"]], "arranged": [int(x) for x in lines["arranged"]],
            "bundleTimes": bundle_times, "lineTimes": line_times, "arrangedCover": cover, "harm": harm,
            "made": {"device": rep.get("timings", {}).get("device", "?"), "separator": rep.get("separator", "?"), "lyrics": len(lyr)}}
    progress(100, "완료")
    return pack


def _wav(mp3, work):
    out = os.path.join(work, "probe.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-vn", "-ac", "1", "-ar", "8000", out], check=True)
    return out


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    pk = build(src, os.path.splitext(dst)[0] + "_work", lambda p, m="": print(f"{p:5.1f}%  {m}", flush=True))
    json.dump(pk, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print({k: (len(v) if isinstance(v, list) else v) for k, v in pk.items() if k != "harm"})
