"""화음왕 extraction server on Modal: same web API as server.py, but nothing runs (and nothing
is billed) until a song arrives.

    modal deploy hwaeumwang/server/modal_app.py        # needs MODAL_TOKEN_ID / MODAL_TOKEN_SECRET
                                                       # HWAEUM_KEY in the environment sets the access word

Two parts:
  web      a small CPU container that answers the app (upload, progress, result)
  extract  a T4 GPU container that works one song out; it starts when a song comes in and
           is released about a minute and a half after the last one
Results are kept on a volume by the file's content, so the same song is never computed twice.
The uploaded mp3 is deleted as soon as its result is written.
"""
import os
import modal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
app = modal.App("hwaeumwang")
vol = modal.Volume.from_name("hwaeumwang-data", create_if_missing=True)
jobs = modal.Dict.from_name("hwaeumwang-jobs", create_if_missing=True)
# one entry per installed app, under a random number the app made up for itself (no name, no device
# details): first and last time it was opened, how often, its version, the songs it sent
users = modal.Dict.from_name("hwaeumwang-users", create_if_missing=True)
key = modal.Secret.from_dict({"HWAEUM_KEY": os.environ.get("HWAEUM_KEY", "")})
SRC = dict(ignore=["data", "__pycache__", "*.ipynb", "*.pyc", "scores", "tuning"])


def _weights():
    """Run once while the image is built, so a cold start does not download models."""
    from demucs.pretrained import get_model
    get_model("htdemucs")
    from faster_whisper import WhisperModel
    WhisperModel("small", device="cpu", compute_type="int8")


NV = "/usr/local/lib/python3.11/site-packages/nvidia"
gpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "build-essential")
    .pip_install("torch", "torchaudio")
    .pip_install("demucs", "torchcrepe", "librosa", "soundfile", "mido", "pyworld", "faster-whisper")
    .pip_install("nvidia-cublas-cu12", "nvidia-cudnn-cu12")            # what the recogniser's GPU build is linked against
    .env({"LD_LIBRARY_PATH": f"{NV}/cublas/lib:{NV}/cudnn/lib"})          # the recogniser's GPU libraries come with torch
    .run_function(_weights)
    .add_local_dir(os.path.join(ROOT, "tools", "vocal2midi"), "/app/tools/vocal2midi", **SRC)
    .add_local_dir(HERE, "/app/hwaeumwang/server", **SRC)
)
web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "numpy")
    .add_local_dir(HERE, "/app/hwaeumwang/server", **SRC)
)
STALE_S = 20 * 60                    # a job silent for this long is taken for dead and may be sent again


# 4 CPU cores: half of the work (decoding, tempo, the harmony voices) is CPU work, and on the default
# fraction of a core it took longer than the GPU part.
@app.function(image=gpu_image, gpu="T4", cpu=4.0, memory=8192, timeout=15 * 60, scaledown_window=90, max_containers=2, volumes={"/data": vol})
def extract(body: bytes, name: str, jid: str):
    import json, sys, time, tempfile, shutil
    sys.path.insert(0, "/app/hwaeumwang/server")
    import pipeline
    last = {"p": -1}

    def progress(p, msg=""):
        if int(p) != last["p"]:
            last["p"] = int(p); jobs[jid] = {"state": "running", "progress": int(p), "message": msg, "ts": time.time()}

    work = tempfile.mkdtemp()
    try:
        mp3 = os.path.join(work, "song.mp3")
        with open(mp3, "wb") as f:
            f.write(body)
        progress(0, "준비 중")
        pack = pipeline.build(mp3, os.path.join(work, "w"), progress, name)
        with open(f"/data/{jid}.json", "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False)
        vol.commit()
        jobs[jid] = {"state": "done", "progress": 100, "message": "", "ts": time.time()}
    except Exception as e:
        jobs[jid] = {"state": "error", "progress": 0, "message": str(e)[:400], "ts": time.time()}
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


@app.function(image=web_image, cpu=0.25, memory=512, scaledown_window=120, max_containers=1, volumes={"/data": vol}, secrets=[key])
@modal.concurrent(max_inputs=40)
@modal.asgi_app()
def web():
    import hashlib, sys, time
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    sys.path.insert(0, "/app/hwaeumwang/server")
    import pipeline
    KEY = os.environ.get("HWAEUM_KEY", ""); MAX_BYTES = 60 * 1024 * 1024
    api = FastAPI()
    api.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def denied(req):
        return bool(KEY) and req.headers.get("x-hwaeum-key", "") != KEY

    def have(jid):
        if os.path.exists(f"/data/{jid}.json"):
            return True
        with lock:                                      # not in the middle of a write of the records
            vol.reload()
        return os.path.exists(f"/data/{jid}.json")

    # ---- beta records.  Kept on the volume (they must outlive the week), in two places:
    #   /data/users.json            one entry per install: name given, phone, version, first/last seen, songs sent
    #   /data/events/<install>.jsonl  what was done, one line per event, as the app reported it
    # This is the only container that writes them (max_containers=1), so appending is safe.
    import json, threading
    lock = threading.Lock(); mem = {"users": None}

    def people():
        if mem["users"] is None:
            try:
                vol.reload()
            except Exception:
                pass
            try:
                mem["users"] = json.load(open("/data/users.json", encoding="utf-8"))
            except Exception:
                mem["users"] = {}
                try:                                    # counts gathered before the records moved to the volume
                    for k, u in users.items():
                        u["songs"] = {h: "" for h in u.get("songs", [])} if isinstance(u.get("songs"), list) else u.get("songs", {})
                        mem["users"][k] = u
                except Exception:
                    pass
        return mem["users"]

    def keep():
        tmp = "/data/users.json.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mem["users"], f, ensure_ascii=False)
        os.replace(tmp, "/data/users.json"); vol.commit()

    def clean(uid):
        uid = "".join(c for c in uid if c.isalnum())[:32]
        return uid if len(uid) >= 8 else ""

    def seen(uid, version="", song=None, title="", nick=None, device=None):
        uid = clean(uid)
        if not uid:
            return
        with lock:
            now = time.time(); u = people().setdefault(uid, {"first": now, "opens": 0, "songs": {}})
            u["last"] = now
            if version:
                u["v"] = version[:20]
            if nick:
                u["nick"] = str(nick)[:20]
            if device:
                u["device"] = str(device)[:80]
            if song is None:
                u["opens"] = u.get("opens", 0) + 1
            else:
                u.setdefault("songs", {})[song] = title[:80]
            keep()

    DAILY = int(os.environ.get("HWAEUM_DAILY", "3"))    # songs one install may send in a day (Korean time)

    def allow(uid, song, admin):
        """Whether this install may send this song today; the song is noted if so.  A song already
        sent today does not count twice."""
        with lock:
            now = time.time(); u = people().setdefault(uid, {"first": now, "opens": 0, "songs": {}}); u["last"] = now
            day = time.strftime("%Y-%m-%d", time.gmtime(now + 9 * 3600)); days = u.setdefault("days", {})
            today = days.setdefault(day, [])
            if song not in today:
                if len(today) >= DAILY and not admin:
                    return False
                today.append(song)
            for d in sorted(days)[:-30]:
                del days[d]
            keep()
            return True

    @api.post("/hello")
    async def hello(req: Request, id: str = "", v: str = ""):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        try:
            body = await req.json()
        except Exception:
            body = {}
        seen(id, v, nick=body.get("nick"), device=body.get("device"))
        return {"ok": True}

    @api.delete("/hello")
    def forget(req: Request, id: str = ""):            # take an install out of the records (a test device)
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        with lock:
            gone = people().pop(id, None) is not None
            if os.path.exists(f"/data/events/{clean(id)}.jsonl"):
                os.remove(f"/data/events/{clean(id)}.jsonl")
            keep()
        return {"removed": gone}

    @api.post("/events")
    async def events(req: Request, id: str = ""):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        uid = clean(id)
        try:
            rows = await req.json()
        except Exception:
            rows = None
        if not uid or not isinstance(rows, list) or len(rows) > 1000:
            return JSONResponse({"error": "bad"}, 400)
        with lock:
            os.makedirs("/data/events", exist_ok=True)
            with open(f"/data/events/{uid}.jsonl", "a", encoding="utf-8") as f:
                for r in rows:
                    if isinstance(r, dict):
                        f.write(json.dumps(r, ensure_ascii=False)[:2000] + "\n")
            vol.commit()
        return {"ok": True, "n": len(rows)}

    def history(uid):
        try:
            with open(f"/data/events/{uid}.jsonl", encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        except Exception:
            return []

    @api.get("/report")
    def report(req: Request, raw: int = 0):
        """Everything known per tester, summed up; raw=1 adds every event."""
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        out = []
        with lock:
            for uid, u in people().items():
                ev = history(uid); pr = [e for e in ev if e.get("e") == "practice"]
                scores = [b["score"] for e in pr for b in e.get("bundles", []) if "score" in b]
                modes = {}
                for e in pr:
                    for b in e.get("bundles", []):
                        modes[b.get("mode", "?")] = modes.get(b.get("mode", "?"), 0) + 1
                by_song = {}
                for e in pr:
                    by_song[e.get("song", "?")] = by_song.get(e.get("song", "?"), 0) + e.get("sec", 0)
                screens = {}
                for e in ev:
                    if e.get("e") == "session":
                        for k, v in (e.get("screens") or {}).items():
                            screens[k] = screens.get(k, 0) + v
                row = {"id": uid, "nick": u.get("nick", ""), "device": u.get("device", ""), "v": u.get("v", ""),
                       "first": u.get("first", 0), "last": u.get("last", 0), "opens": u.get("opens", 0),
                       "songs": sorted({t for t in (u.get("songs") or {}).values() if t} | {e.get("song", "") for e in ev if e.get("e") == "extract_done"} - {""}),
                       "app_sec": sum(e.get("sec", 0) for e in ev if e.get("e") == "session"), "screen_sec": screens,
                       "practice_sec": sum(e.get("sec", 0) for e in pr), "practice_runs": len(pr), "practice_by_song": by_song,
                       "avg_score": round(sum(scores) / len(scores)) if scores else None, "harmony_kinds": modes,
                       "melody_guide_runs": sum(1 for e in pr if e.get("melody")), "voice_guide_runs": sum(1 for e in pr if e.get("voice")),
                       "routes": sorted({e.get("route", "") for e in pr} - {""}),
                       "extract_fail": [e.get("msg", "") for e in ev if e.get("e") == "extract_fail"],
                       "errors": [e.get("msg", "") for e in ev if e.get("e") == "error"][-20:],
                       "events": len(ev)}
                if raw:
                    row["raw"] = ev
                out.append(row)
        out.sort(key=lambda r: -r["last"])
        return {"users": out}

    @api.get("/stats")
    def stats(req: Request):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        now = time.time()
        with lock:
            all_users = list(people().values())
        versions = {}
        for u in all_users:
            versions[u.get("v", "?")] = versions.get(u.get("v", "?"), 0) + 1
        return {"users": len(all_users),
                "week": sum(now - u.get("last", 0) < 7 * 86400 for u in all_users),
                "today": sum(now - u.get("last", 0) < 86400 for u in all_users),
                "songs": sum(len(u.get("songs") or {}) for u in all_users),
                "with_songs": sum(1 for u in all_users if u.get("songs")),
                "versions": versions}

    @api.get("/health")
    def health():
        return {"ok": True, "device": "Modal T4", "key": bool(KEY)}

    @api.post("/extract")
    async def start(req: Request, name: str = "", force: int = 0, uid: str = "", admin: str = ""):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        body = await req.body()
        if not 0 < len(body) <= MAX_BYTES:
            return JSONResponse({"error": "size"}, 413)
        jid = hashlib.sha1(body + pipeline.VERSION.encode()).hexdigest()[:16]
        uid = clean(uid)
        if not uid:                                     # an app from before installs were told apart
            return JSONResponse({"error": "update"}, 426)
        song = hashlib.sha1(body).hexdigest()[:12]
        if not allow(uid, song, admin == "8516"):
            return JSONResponse({"error": "limit", "limit": DAILY}, 429)
        seen(uid, song=song, title=name.strip())
        if have(jid) and not force:                     # force: work it out again even though a result is kept
            return {"id": jid, "state": "done"}
        j = jobs.get(jid)
        if j and j["state"] in ("queued", "running") and time.time() - j.get("ts", 0) < STALE_S:
            return {"id": jid, "state": j["state"]}
        jobs[jid] = {"state": "queued", "progress": 0, "message": "서버 깨우는 중", "ts": time.time()}
        extract.spawn(body, name.strip(), jid)
        return {"id": jid, "state": "queued"}

    @api.get("/job/{jid}")
    def status(jid: str, req: Request):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        j = jobs.get(jid)
        if j is None:
            return {"state": "done", "progress": 100, "message": ""} if have(jid) else JSONResponse({"error": "not found"}, 404)
        if j["state"] in ("queued", "running") and time.time() - j.get("ts", 0) > STALE_S:
            return {"state": "error", "progress": 0, "message": "서버가 응답하지 않습니다. 다시 시도해 주세요"}
        return {k: j[k] for k in ("state", "progress", "message")}

    @api.get("/job/{jid}/pack")
    def pack(jid: str, req: Request):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        if not jid.isalnum() or not have(jid):
            return JSONResponse({"error": "not found"}, 404)
        with lock:
            vol.reload()                                # a result worked out again replaces the file this container has seen
        return FileResponse(f"/data/{jid}.json", media_type="application/json; charset=utf-8")

    return api
