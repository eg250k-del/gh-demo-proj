FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    DATA_DIR=/data \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && python -m spacy download en_core_web_sm

COPY pipeline /app/pipeline
COPY episodes /app/episodes
COPY assets /app/assets
WORKDIR /app/pipeline

EXPOSE 8000
# "::" so Salad's Container Gateway (IPv6) can reach it
CMD ["uvicorn", "server:app", "--host", "::", "--port", "8000"]
