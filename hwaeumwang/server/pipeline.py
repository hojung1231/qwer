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
VERSION = "5"                        # raise when results change, so the server's kept results are not reused


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


def pauses(ns, t, voiced):
    """Seconds of silence in the voice just before each note.  The written notes are joined up
    (a short breath is given to the note before it), so the pauses are read from the voice itself."""
    dt = float(t[1] - t[0]); out = np.zeros(len(ns))
    for i in range(1, len(ns)):
        a = ns[i - 1][0] + min(ns[i - 1][1], 0.15); b = ns[i][0] + 0.12
        seg = voiced[int(a / dt):max(int(a / dt) + 1, int(b / dt))]
        run = best = 0
        for x in seg:
            run = 0 if x else run + 1; best = max(best, run)
        out[i] = best * dt
    return out


def align(ns, syl, beat, pause=None, c_skip=0.7, w_cnt=1.0, w_gap=1.5, w_b=0.8, rate=None):
    """Lay lyric lines over the notes: each line takes a run of notes about as long as its
    syllable count, lines begin after pauses, notes with no words (ad libs) may be skipped."""
    N, M = len(ns), len(syl)
    st = np.array([n[0] for n in ns]); en = np.array([n[0] + n[1] for n in ns])
    gap = np.zeros(N + 1); gap[1:N] = np.maximum(0, st[1:] - en[:-1]) / beat
    if pause is not None:
        gap[1:N] = np.maximum(gap[1:N], np.asarray(pause)[1:N] / beat)
    gap[0] = 4; gap[N] = 4
    # A singer often spreads one syllable over several notes, so a line takes more notes than it
    # has syllables.  How many more is read off the whole song (all notes over all syllables);
    # matching one note to one syllable made the words run further and further ahead.
    r = min(2.2, max(1.0, N / max(1, sum(syl)))) if rate is None else rate
    INF = 1e9; dp = np.full((M + 1, N + 1), INF); bk = np.zeros((M + 1, N + 1, 2), int); dp[0, 0] = 0
    for j in range(M + 1):
        for i in range(N + 1):
            c = dp[j, i]
            if c >= INF:
                continue
            if i < N and c + c_skip < dp[j, i + 1]:
                dp[j, i + 1] = c + c_skip; bk[j, i + 1] = (j, i)
            if j < M:
                s = syl[j] * r; g = 0.0
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


# ------------------------------------------------------------------ where the words are, by listening
def sung_chunks(t, voiced, join=0.35, max_len=20.0, max_pause=1.5):
    """Stretches of singing to hand to the recogniser one at a time.  Given the whole song it
    skips long passages; given one stretch at a time it writes down nearly every word."""
    runs, a = [], None
    for k, x in enumerate(voiced):
        if x and a is None:
            a = k
        if not x and a is not None:
            runs.append([float(t[a]), float(t[k])]); a = None
    ph = []
    for r in runs:
        if r[1] - r[0] < 0.08:
            continue
        if ph and r[0] - ph[-1][1] < join:
            ph[-1][1] = r[1]
        else:
            ph.append(r)
    out = []
    for a, b in (x for x in ph if x[1] - x[0] > 0.3):
        if out and a - out[-1][1] < max_pause and b - out[-1][0] < max_len:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def transcribe(vocal, sr, chunks, lang="ko", progress=lambda f: None):
    """[(start s, end s, word)] of what is sung, or None when no recogniser is installed."""
    try:
        from faster_whisper import WhisperModel
        import librosa
    except Exception:
        return None
    name = os.environ.get("HWAEUM_ASR", "small")
    y = librosa.resample(vocal, orig_sr=sr, target_sr=16000) if sr != 16000 else vocal
    # The GPU is tried first.  Its libraries can be missing or mismatched, and that only shows
    # when the first stretch is actually recognised, so the whole pass is retried on the CPU.
    for dev, ct in (("cuda", "float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(name, device=dev, compute_type=ct)
            words = []
            for k, (a, b) in enumerate(chunks):
                a0 = max(0.0, a - 0.3)
                segs, _ = model.transcribe(y[int(a0 * 16000):int((b + 0.3) * 16000)], language=lang, word_timestamps=True, vad_filter=False,
                                           condition_on_previous_text=False, temperature=0.0, beam_size=5,
                                           no_speech_threshold=None, log_prob_threshold=None, compression_ratio_threshold=None)
                for sg in segs:
                    words += [(a0 + w.start, a0 + w.end, w.word) for w in (sg.words or [])]
                progress((k + 1) / len(chunks))
            return words
        except Exception as e:
            print(f"[lyrics] recogniser failed on {dev}: {type(e).__name__}: {str(e)[:200]}", flush=True)
    return None


def _units(text):
    """A word as comparable sound units: Hangul syllables split into their letters (so 바램 and
    바람 still mostly agree), other letters and digits as they are."""
    out = []
    for ch in text.lower():
        if "가" <= ch <= "힣":
            c = ord(ch) - 0xAC00
            out += [("i", c // 588), ("v", (c % 588) // 28)] + ([("f", c % 28)] if c % 28 else [])
        elif ch.isalnum():
            out.append(("c", ch))
    return out


def heard_lines(lyr, words, min_match=0.5):
    """Start and end of each lyric line from the recognised words: the lyrics and the recognised
    text are matched letter by letter (the recogniser mishears words, but mostly keeps their
    sounds and their order).  Lines it could not place come back as None."""
    L = [(u, j) for j, l in enumerate(lyr) for u in _units(l)]
    R = []
    for a, b, w in words:
        us = _units(w)
        R += [(u, a + (b - a) * k / len(us), a + (b - a) * (k + 1) / len(us)) for k, u in enumerate(us)]
    n, m = len(L), len(R)
    if not n or not m:
        return [None] * len(lyr)
    D = np.zeros((n + 1, m + 1), np.float32); D[:, 0] = np.arange(n + 1); D[0, :] = np.arange(m + 1)
    lu = [x[0] for x in L]; ru = [x[0] for x in R]
    for i in range(1, n + 1):
        prev = D[i - 1]; cur = D[i]; u = lu[i - 1]; left = float(cur[0])
        for k in range(1, m + 1):
            v = prev[k - 1] + (0.0 if u == ru[k - 1] else 1.0)
            if prev[k] + 1.0 < v:
                v = prev[k] + 1.0
            if left + 1.0 < v:
                v = left + 1.0
            cur[k] = v; left = v
    i, k = n, m; hits = [[] for _ in lyr]; pos = {}; count = [0] * len(lyr)
    for u, j in L:
        count[j] += 1
    first = {}
    for idx, (u, j) in enumerate(L):
        first.setdefault(j, idx)
    while i > 0 and k > 0:
        if D[i, k] == D[i - 1, k - 1] + (0.0 if lu[i - 1] == ru[k - 1] else 1.0):
            if lu[i - 1] == ru[k - 1]:
                hits[L[i - 1][1]].append((i - 1 - first[L[i - 1][1]], R[k - 1][1], R[k - 1][2]))
            i -= 1; k -= 1
        elif D[i, k] == D[i - 1, k] + 1.0:
            i -= 1
        else:
            k -= 1
    out = []
    for j, h in enumerate(hits):
        h.sort()
        if not h or len(h) < min_match * count[j] or h[0][0] > 0.34 * count[j]:
            out.append(None); continue                   # too little heard, or its beginning was not heard
        out.append((h[0][1], h[-1][2]))
    return out


def place_lines(lyr, notes, heard):
    """A start and an end for every line: heard lines sit where they were heard (moved onto the
    nearest note), the others are spread between their neighbours by their length."""
    M = len(lyr); syl = [syllables(l) for l in lyr]; st = np.array([n[0] for n in notes])
    start = [None] * M; end = [None] * M
    for j, h in enumerate(heard):
        if h:
            k = int(np.argmin(np.abs(st - h[0])))
            start[j] = float(st[k]) if abs(st[k] - h[0]) <= 0.5 else h[0]; end[j] = max(h[1], start[j] + 0.3)
    for j in range(1, M):                                # the recogniser's order is kept; a line cannot begin before the one above it
        if start[j] is not None:
            prev = next((start[q] for q in range(j - 1, -1, -1) if start[q] is not None), None)
            if prev is not None and start[j] <= prev:
                start[j] = end[j] = None
    j = 0
    while j < M:
        if start[j] is not None:
            j += 1; continue
        a = j
        while j < M and start[j] is None:
            j += 1
        lo = end[a - 1] if a else float(st[0]); hi = start[j] if j < M else float(notes[-1][0] + notes[-1][1])
        tot = sum(syl[a:j]) or 1; acc = 0
        for q in range(a, j):
            start[q] = lo + (hi - lo) * acc / tot; acc += syl[q]; end[q] = lo + (hi - lo) * acc / tot
            k = int(np.argmin(np.abs(st - start[q])))
            if abs(st[k] - start[q]) <= 0.6 and (q == 0 or st[k] > start[q - 1]):
                start[q] = float(st[k])
    en = np.array([n[0] + n[1] for n in notes])
    for j in range(M):                                   # a line ends with its last note, not at the next line after an interlude
        nxt = start[j + 1] if j + 1 < M else 1e9
        inside = en[(st >= start[j] - 0.05) & (st < nxt - 0.05)]
        if len(inside):
            end[j] = min(end[j], float(inside[-1])) if heard[j] is None else min(max(end[j], start[j] + 0.2), nxt)
        end[j] = max(start[j] + 0.2, min(end[j], nxt))
    return [(float(a), float(b)) for a, b in zip(start, end)]


# ------------------------------------------------------------------ the whole job
def build(mp3, work, progress=lambda p, msg="": None, name=None):
    import soundfile as sf
    os.makedirs(work, exist_ok=True)
    clock, t_all = {}, time.time()
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

    clock["melody"] = round(time.time() - t_all, 1)
    progress(77, "화음 만드는 중")
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import librosa, harmony as H, isolate, notes as N
    sr = 44100
    rep, mel = H.load_melody(work)
    if len(mel) < 8:
        raise RuntimeError("노래하는 목소리를 찾지 못했습니다")
    beat = 60.0 / rep["bpm"]; tonic = H.NAMES.index(rep["key"].split()[0])
    vocal, _ = librosa.load(os.path.join(work, "vocal.wav"), sr=sr)
    z = np.load(os.path.join(work, "f0.npz"))
    voiced = N.voicing(z["per"], z["rms"], rel_db=-18.0)
    title, artist, lyr = tags(mp3)
    notes = [(float(t), float(d), int(m)) for t, d, m in mel]

    # The words are listened for on the side (that is GPU work) while the harmony voices are made
    # (CPU work): neither waits for the other.
    found = {"span": None, "how": "none"}

    def lyrics():
        t0 = time.time()
        try:
            if not lyr:
                return
            words = transcribe(vocal, sr, sung_chunks(z["t"], voiced))
            heard = heard_lines(lyr, words) if words else None
            if heard and sum(h is not None for h in heard) >= 0.4 * len(lyr):
                found["span"] = place_lines(lyr, notes, heard); found["how"] = f"heard {sum(h is not None for h in heard)}/{len(lyr)}"
            else:                                        # no recogniser, or a language it could not follow: count notes instead
                segs = align(notes, [syllables(l) for l in lyr], beat, pauses(notes, z["t"], voiced))
                if segs and len(segs) == len(lyr):
                    found["span"] = [(notes[a][0], notes[e - 1][0] + notes[e - 1][1]) for _, a, e in segs]; found["how"] = "counted"
        except Exception as e:
            print(f"[lyrics] {type(e).__name__}: {str(e)[:200]}", flush=True)
        finally:
            clock["lyrics"] = round(time.time() - t0, 1)

    side = threading.Thread(target=lyrics, daemon=True); side.start()

    t0 = time.time()
    stereo = isolate.decode(mp3, sr); mix = stereo.mean(0)
    chords = H.estimate_chords(mix, vocal, sr, rep["midi_origin_s"], beat, tonic)
    lines = {"up": H.harmony_line(mel, chords, tonic, beat, +1), "down": H.harmony_line(mel, chords, tonic, beat, -1),
             "arranged": H.smart_line(mel, chords, tonic, beat, everywhere=True)}
    # where an arranger would actually bring the voice in: used only to recommend bundles
    arranged_rec = H.smart_line(mel, chords, tonic, beat)
    clock["harmony_lines"] = round(time.time() - t0, 1)

    progress(82, "화음 목소리 만드는 중")
    # The voice is re-sung at 24 kHz: the result is a backing voice kept as a small mp3, which holds
    # nothing above that anyway, and the analysis and the singing take well under half the time.
    t0 = time.time(); VSR = 24000
    voice = H.Voice(librosa.resample(vocal, orig_sr=sr, target_sr=VSR), VSR, (z["t"], z["f0"], voiced), mel, rep.get("tuning_cents", 0.0))
    progress(88, "화음 목소리 만드는 중")

    def sing(item):
        key, pitches = item
        y = voice.from_score(mel, pitches, rep.get("tuning_cents", 0.0)) * 10 ** (-5.0 / 20)
        wav = os.path.join(work, f"harm_{key}.wav"); out = os.path.join(work, f"harm_{key}.mp3")
        sf.write(wav, y, VSR)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-b:a", "48k", out], check=True)
        os.remove(wav)
        return key, "data:audio/mpeg;base64," + base64.b64encode(open(out, "rb").read()).decode()

    with ThreadPoolExecutor(3) as pool:                  # the three voices at once
        harm = dict(pool.map(sing, lines.items()))
    clock["voices"] = round(time.time() - t0, 1)

    progress(96, "가사 맞추는 중")
    side.join()
    span, how = found["span"], found["how"]
    bundle_times, line_times, cover = [], [], []
    if span:
        line_times = [round(s, 2) for s, _ in span]
        for i in range(0, len(lyr), PER_BUNDLE):
            part = span[i:i + PER_BUNDLE]
            bundle_times.append([round(max(0.0, part[0][0] - 0.4), 1), round(part[-1][1] + 0.4, 1)])
        arr = arranged_rec
        for a, e in bundle_times:
            inside = [arr[k] > 0 for k, n in enumerate(notes) if a <= n[0] < e]
            cover.append(1 if inside and sum(inside) >= 0.3 * len(inside) else 0)
    pack = {"hwaeum": 1, "title": (name or title or os.path.splitext(os.path.basename(mp3))[0]).strip(), "artist": artist,
            "info": {"notes": len(notes), "key": rep["key"].split()[0] + "장조", "bpm": int(round(rep["bpm"])),
                     "sig": "12/8" if div == 3 else "4/4"},
            "mel": [[round(t, 3), round(d, 3), m] for t, d, m in notes],
            "up": [int(x) for x in lines["up"]], "down": [int(x) for x in lines["down"]], "arranged": [int(x) for x in lines["arranged"]],
            "bundleTimes": bundle_times, "lineTimes": line_times, "arrangedCover": cover, "arrangedFull": True, "harm": harm,
            "made": {"device": rep.get("timings", {}).get("device", "?"), "separator": rep.get("separator", "?"), "lyrics": len(lyr), "lines": how,
                     "seconds": dict(clock, total=round(time.time() - t_all, 1), **{k: v for k, v in rep.get("timings", {}).items() if k.endswith("_s")})}}
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
