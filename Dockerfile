# Everything baked in (tools + models) so a Salad node starts working right after the image pull.
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models \
    DATA_DIR=/data \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    CODE_REPO=eg250k-del/gh-demo-proj \
    CODE_BRANCH=ccr-8f933243-klm29q

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg espeak-ng fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && python -m spacy download en_core_web_sm

# models: Animagine XL (fp16 weights only), SDXL-Lightning LoRA, Kokoro voices
RUN python -c "from huggingface_hub import snapshot_download, hf_hub_download; \
snapshot_download('cagliostrolab/animagine-xl-3.1', allow_patterns=['*.json', '*.txt', '**/*.json', '**/*.txt', '*.safetensors', '**/*.safetensors'], ignore_patterns=['animagine-xl-3.1.safetensors']); \
hf_hub_download('ByteDance/SDXL-Lightning', 'sdxl_lightning_8step_lora.safetensors'); \
snapshot_download('hexgrad/Kokoro-82M')"

COPY pipeline /app/pipeline
COPY episodes /app/episodes
COPY assets /app/assets
WORKDIR /app/pipeline

EXPOSE 8000
# "::" so Salad's Container Gateway (IPv6) can reach it
CMD ["uvicorn", "server:app", "--host", "::", "--port", "8000"]
