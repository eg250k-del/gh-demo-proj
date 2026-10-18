#!/bin/bash
# Salad boot script: runs inside the public pytorch image, installs everything, starts the web server.
set -e
apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core >/dev/null
pip install -q --no-cache-dir -r requirements.txt
python -m spacy download en_core_web_sm -q || true
export HF_HOME=/models DATA_DIR=/data PYTHONUNBUFFERED=1
mkdir -p /models /data
cd pipeline
exec uvicorn server:app --host :: --port 8000
