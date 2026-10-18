"""Control the Salad container group from your PC (standard library only).

    set SALAD_API_KEY=...      (Windows)   /  export SALAD_API_KEY=...  (Mac/Linux)
    python salad.py gpus                      list GPU classes and prices
    python salad.py create  ORG PROJECT DOCKERHUB_USER [comma-separated GPU class names]
    python salad.py create  ORG PROJECT --from-github  [GPU]   no Docker Hub: boots from this repo
    python salad.py start   ORG PROJECT
    python salad.py status  ORG PROJECT       shows the public URL when it's running
    python salad.py stop    ORG PROJECT       STOP when done, billing continues while running
"""
import json
import os
import sys
import urllib.request

API = "https://api.salad.com/api/public"
NAME = "manhwa-studio"
REPO = "eg250k-del/gh-demo-proj"
BRANCH = "ccr-8f933243-klm29q"
# 12 GB+ VRAM classes, cheapest first; Salad picks whichever is free
DEFAULT_GPUS = "RTX 3060 (12 GB),RTX 3080 Ti (12 GB),RTX 4070 (12 GB),RTX 3090 (24 GB),RTX 3090 Ti (24 GB),RTX A5000 (24 GB)"
BOOT_IMAGE = "docker.io/pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"


def call(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method, data=json.dumps(body).encode() if body else None,
        headers={"Salad-Api-Key": os.environ["SALAD_API_KEY"], "Content-Type": "application/json", "User-Agent": "manhwa-studio/1.0"})
    with urllib.request.urlopen(req) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def base(org, project):
    return f"/organizations/{org}/projects/{project}/containers/{NAME}"


def main(cmd, *a):
    if cmd == "gpus":
        org = a[0] if a else input("organization name: ")
        for g in call("GET", f"/organizations/{org}/gpu-classes")["items"]:
            print(g["id"], "|", g["name"], "|", g.get("prices", ""))
    elif cmd == "create":
        org, project, user = a[:3]
        wants = [w.strip().lower() for w in (a[3] if len(a) > 3 else DEFAULT_GPUS).split(",")]
        gpus = [g["id"] for g in call("GET", f"/organizations/{org}/gpu-classes")["items"] if g["name"].lower() in wants]
        if not gpus:
            sys.exit(f"no GPU class matching {wants}, run: python salad.py gpus {org}")
        container = {"image": f"docker.io/{user}/{NAME}:latest"}
        if user == "--from-github":
            # no registry needed: public pytorch image downloads this repo at boot and runs start.sh
            url = f"https://codeload.github.com/{REPO}/tar.gz/refs/heads/{BRANCH}"
            boot = (f"python -c \"import urllib.request,tarfile,io;"
                    f"tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen('{url}').read())).extractall('/src')\""
                    f" && cd /src/*/ && bash start.sh")
            container = {"image": BOOT_IMAGE, "command": ["bash", "-c", boot]}
        body = {
            "name": NAME,
            "container": {
                **container,
                "resources": {"cpu": 4, "memory": 16384, "gpu_classes": gpus, "storage_amount": 53687091200},
                "priority": os.environ.get("SALAD_PRIORITY", "high"),
                "environment_variables": {"APP_TOKEN": os.environ.get("APP_TOKEN", "")},
            },
            "networking": {"protocol": "http", "port": 8000, "auth": False},
            "replicas": 1,
            "restart_policy": "always",
            "autostart_policy": False,
        }
        print(json.dumps(call("POST", f"/organizations/{org}/projects/{project}/containers", body), indent=2))
    elif cmd in ("start", "stop"):
        call("POST", base(*a[:2]) + "/" + cmd)
        print(cmd, "requested")
    elif cmd == "status":
        g = call("GET", base(*a[:2]))
        print("status:", g["current_state"]["status"], "| instances:", g["current_state"].get("instance_status_counts"))
        dns = g.get("networking", {}).get("dns")
        if dns:
            print("URL: https://" + dns + (f"/?token={os.environ['APP_TOKEN']}" if os.environ.get("APP_TOKEN") else ""))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["help"]))
