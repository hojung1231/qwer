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


@app.function(image=web_image, cpu=0.25, memory=512, scaledown_window=120, max_containers=2, volumes={"/data": vol}, secrets=[key])
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
        vol.reload()
        return os.path.exists(f"/data/{jid}.json")

    @api.get("/health")
    def health():
        return {"ok": True, "device": "Modal T4", "key": bool(KEY)}

    @api.post("/extract")
    async def start(req: Request, name: str = ""):
        if denied(req):
            return JSONResponse({"error": "key"}, 401)
        body = await req.body()
        if not 0 < len(body) <= MAX_BYTES:
            return JSONResponse({"error": "size"}, 413)
        jid = hashlib.sha1(body + pipeline.VERSION.encode()).hexdigest()[:16]
        if have(jid):
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
        return FileResponse(f"/data/{jid}.json", media_type="application/json; charset=utf-8")

    return api
