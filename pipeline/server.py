"""HTTP server that runs on Salad. Open the container URL in a browser, paste an episode JSON, download the MP4.

Endpoints: GET / (web page) · GET /health · POST /jobs · GET /jobs/{id} · GET /jobs/{id}/video
Set APP_TOKEN to require ?token=... on every request.
"""
import json
import os
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

import images
import render
import run_episode
import tts

DATA = Path(os.environ.get("DATA_DIR", "/data"))
TOKEN = os.environ.get("APP_TOKEN", "")
app = FastAPI()
jobs: dict[str, dict] = {}
lock = threading.Lock()  # one GPU job at a time
state = {"models": "loading"}


def warmup():
    try:
        images.load()
        tts._kokoro("a")
        tts._kokoro("b")
        state["models"] = "ready"
    except Exception as e:  # noqa: BLE001
        state["models"] = f"error: {e}"


threading.Thread(target=warmup, daemon=True).start()


@app.middleware("http")
async def auth(request: Request, call_next):
    if TOKEN and request.url.path != "/health" and request.query_params.get("token") != TOKEN:
        return HTMLResponse("unauthorized", status_code=401)
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True, "models": state["models"]}


@app.post("/jobs")
async def create(request: Request):
    episode = await request.json()
    job_id = uuid.uuid4().hex[:8]
    (DATA / job_id).mkdir(parents=True, exist_ok=True)
    (DATA / job_id / "episode.json").write_text(json.dumps(episode))
    jobs[job_id] = {"status": "queued", "log": []}
    threading.Thread(target=_work, args=(job_id, episode), daemon=True).start()
    return {"id": job_id}


def _work(job_id: str, episode: dict):
    job = jobs[job_id]
    with lock:
        job["status"] = "running"
        try:
            run_episode.produce(episode, DATA / job_id, log=job["log"].append)
            job["status"] = "done"
        except Exception:  # noqa: BLE001
            job["status"] = "error"
            job["log"].append(traceback.format_exc())


@app.get("/jobs/{job_id}")
def status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404)
    return jobs[job_id]


@app.post("/jobs/{job_id}/retry")
def retry(job_id: str):
    """Re-run a job in place; finished images/audio/shots on disk are reused."""
    if job_id not in jobs:
        raise HTTPException(404)
    episode = json.loads((DATA / job_id / "episode.json").read_text())
    jobs[job_id] = {"status": "queued", "log": []}
    threading.Thread(target=_work, args=(job_id, episode), daemon=True).start()
    return {"id": job_id}


@app.get("/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    """Download intermediate results (shot images, shot videos) so nothing is lost if the node goes away."""
    path = DATA / job_id / "work" / Path(name).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/jobs/{job_id}/files")
def job_files(job_id: str):
    work = DATA / job_id / "work"
    return sorted(p.name for p in work.glob("*") if p.suffix in (".png", ".mp4", ".wav")) if work.exists() else []


@app.post("/admin/update")
def update_code():
    """Pull the latest code from GitHub and hot-reload it, no restart, models stay in memory."""
    import importlib, io, shutil, tarfile, tempfile, urllib.request
    repo, branch = os.environ.get("CODE_REPO"), os.environ.get("CODE_BRANCH")
    if not repo or not branch:
        raise HTTPException(400, "CODE_REPO / CODE_BRANCH not set")
    if lock.locked():
        raise HTTPException(409, "a job is running")
    data = urllib.request.urlopen(f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{branch}").read()
    with tempfile.TemporaryDirectory() as tmp:
        tarfile.open(fileobj=io.BytesIO(data)).extractall(tmp)
        src = next(Path(tmp).iterdir())
        here = Path(__file__).parent
        for f in (src / "pipeline").glob("*.py"):
            shutil.copy(f, here / f.name)
        for d in ("episodes", "assets"):
            if (src / d).exists():
                shutil.copytree(src / d, here.parent / d, dirs_exist_ok=True)
    for mod in (render, tts, run_episode):  # images is not reloaded: keeps the loaded GPU pipeline
        importlib.reload(mod)
    return {"updated": True}


@app.get("/jobs/{job_id}/video")
def video(job_id: str):
    path = DATA / job_id / "final.mp4"
    if not path.exists():
        raise HTTPException(404, "not ready")
    return FileResponse(path, media_type="video/mp4", filename=f"episode_{job_id}.mp4")


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Manhwa Studio</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui;background:#0b1020;color:#e8ecff;max-width:900px;margin:auto;padding:16px}
textarea{width:100%;height:320px;background:#111833;color:#e8ecff;border:1px solid #2a3a70;border-radius:8px;padding:8px;font-family:monospace}
button{background:#3b82f6;color:#fff;border:0;padding:12px 20px;border-radius:8px;font-size:16px;cursor:pointer}
pre{background:#111833;padding:8px;border-radius:8px;white-space:pre-wrap;max-height:300px;overflow:auto}a{color:#7cc4ff}</style></head>
<body><h1>Manhwa Studio</h1><p>Models: <b id="m">…</b></p>
<p>Paste an episode JSON:</p><textarea id="ep">__EPISODE__</textarea><p><button onclick="go()">Render episode</button></p>
<p id="st"></p><pre id="log"></pre>
<script>
const q = location.search;
fetch('/health').then(r=>r.json()).then(j=>m.textContent=j.models);
async function go(){
  const r = await fetch('/jobs'+q,{method:'POST',headers:{'Content-Type':'application/json'},body:ep.value});
  const {id} = await r.json(); poll(id);
}
async function poll(id){
  const j = await (await fetch('/jobs/'+id+q)).json();
  st.innerHTML = 'Job '+id+': <b>'+j.status+'</b>' + (j.status=='done' ? ' — <a href="/jobs/'+id+'/video'+q+'">Download MP4</a>' : '');
  log.textContent = j.log.join('\\n');
  if (j.status=='queued' || j.status=='running') setTimeout(()=>poll(id), 3000);
}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def page():
    sample = Path(__file__).parent.parent / "episodes" / "ep01_pilot.json"
    return PAGE.replace("__EPISODE__", sample.read_text().replace("<", "&lt;") if sample.exists() else "")
