"""화음왕 extraction server: the app sends an mp3, this computer does the heavy work.

    python server.py                 # listens on every network interface, port 8787
    python server.py --key 비밀단어    # only requests carrying this word are served
    python server.py --tunnel        # also open an internet address (needs cloudflared), for a
                                     # phone that is not on this computer's network

    POST /extract?name=<song title>   body: the mp3 file      -> {"id": ...}
    GET  /job/<id>                                            -> {"state","progress","message"}
    GET  /job/<id>/pack                                       -> the song's data (JSON)
    GET  /health                                              -> {"ok": true, "device": ...}

One song is worked on at a time; others wait their turn.  Finished results are kept on disk
by the file's content, so sending the same song again answers at once.
"""
from __future__ import annotations
import argparse, hashlib, json, os, queue, re, shutil, socket, subprocess, threading, traceback, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
JOBS, QUEUE, LOCK = {}, queue.Queue(), threading.Lock()
KEY = ""
MAX_BYTES = 60 * 1024 * 1024


def device():
    try:
        import torch
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def worker():
    while True:
        jid = QUEUE.get(); job = JOBS[jid]
        def progress(p, msg=""):
            job["progress"] = round(float(p), 1); job["message"] = msg
        try:
            job["state"] = "running"
            pack = pipeline.build(job["mp3"], os.path.join(DATA, jid + "_work"), progress, job["name"])
            with open(job["pack"], "w", encoding="utf-8") as f:
                json.dump(pack, f, ensure_ascii=False)
            job["state"] = "done"; job["progress"] = 100
        except Exception as e:
            traceback.print_exc()
            job["state"] = "error"; job["message"] = str(e)[:400]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _head(self, code, ctype="application/json", length=0):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type, x-hwaeum-key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(length))
        self.end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._head(code, "application/json; charset=utf-8", len(body)); self.wfile.write(body)

    def _allowed(self):
        if not KEY or self.headers.get("x-hwaeum-key", "") == KEY:
            return True
        self._json(401, {"error": "key"}); return False

    def do_OPTIONS(self):
        self._head(204)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        if path == "/health":
            return self._json(200, {"ok": True, "device": device(), "waiting": QUEUE.qsize(), "key": bool(KEY)})
        if not self._allowed():
            return
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] == "job" and parts[2] in JOBS:
            job = JOBS[parts[2]]
            if len(parts) == 3:
                return self._json(200, {k: job[k] for k in ("state", "progress", "message")})
            if parts[3] == "pack" and job["state"] == "done":
                size = os.path.getsize(job["pack"])
                self._head(200, "application/json; charset=utf-8", size)
                with open(job["pack"], "rb") as f:
                    while chunk := f.read(1 << 16):
                        self.wfile.write(chunk)
                return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.rstrip("/") != "/extract":
            return self._json(404, {"error": "not found"})
        if not self._allowed():
            return
        n = int(self.headers.get("content-length", 0))
        if not 0 < n <= MAX_BYTES:
            return self._json(413, {"error": "size"})
        body = self.rfile.read(n)
        jid = hashlib.sha1(body).hexdigest()[:16]
        name = urllib.parse.parse_qs(u.query).get("name", [""])[0].strip()
        with LOCK:
            job = JOBS.get(jid)
            if job is None or job["state"] == "error":
                mp3 = os.path.join(DATA, jid + ".mp3"); pack = os.path.join(DATA, jid + ".json")
                with open(mp3, "wb") as f:
                    f.write(body)
                done = os.path.exists(pack)
                job = JOBS[jid] = {"state": "done" if done else "queued", "progress": 100 if done else 0, "message": "",
                                   "mp3": mp3, "pack": pack, "name": name}
                if not done:
                    QUEUE.put(jid)
        self._json(200, {"id": jid, "state": job["state"]})

    def log_message(self, fmt, *args):
        if "/job/" not in (args[0] if args else ""):          # progress polling would flood the window
            super().log_message(fmt, *args)


def addresses():
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); out.append(s.getsockname()[0]); s.close()
    except Exception:
        pass
    return out or ["127.0.0.1"]


def tunnel(port):
    """A temporary public https address for this server (Cloudflare quick tunnel, no account)."""
    exe = shutil.which("cloudflared")
    if not exe:
        print("cloudflared 가 없습니다.  Windows: winget install Cloudflare.cloudflared  설치 뒤 창을 새로 열어 주세요."); return
    p = subprocess.Popen([exe, "tunnel", "--url", f"http://localhost:{port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    def watch():
        for line in p.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m:
                print(f"\n어디서나 되는 주소 (앱의 서버 주소 칸에 넣기):  {m.group(0)}\n(서버를 다시 켜면 주소가 바뀝니다)\n", flush=True)
    threading.Thread(target=watch, daemon=True).start()


def main():
    global KEY
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8787); ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--key", default=os.environ.get("HWAEUM_KEY", ""))
    ap.add_argument("--tunnel", action="store_true", help="open a public https address with cloudflared")
    a = ap.parse_args(); KEY = a.key
    os.makedirs(DATA, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    print("화음왕 추출 서버  ·  계산 장치:", device())
    for ip in addresses():
        print(f"앱의 서버 주소 칸에 넣을 주소:  http://{ip}:{a.port}")
    if a.tunnel:
        tunnel(a.port)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
