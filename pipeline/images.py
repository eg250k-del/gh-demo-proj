"""Shot image generation with an anime SDXL model (diffusers).

QUALITY mode (default): Animagine XL, 28 steps, CFG 6  (~4 s/image on a 4090)
FAST mode (FAST_MODE=1): + SDXL-Lightning 8-step LoRA  (~1 s/image)
"""
import os
from pathlib import Path

BASE_MODEL = os.environ.get("BASE_MODEL", "cagliostrolab/animagine-xl-3.1")
LIGHTNING_REPO = "ByteDance/SDXL-Lightning"
LIGHTNING_FILE = "sdxl_lightning_8step_lora.safetensors"
WIDTH, HEIGHT = 1344, 768  # SDXL 16:9 bucket
QUALITY_TAGS = "masterpiece, best quality, very aesthetic, absurdres"

_pipe = None


def fast_mode() -> bool:
    return os.environ.get("FAST_MODE", "0") == "1"


def load():
    global _pipe
    if _pipe is not None:
        return _pipe
    import torch
    from diffusers import StableDiffusionXLPipeline, EulerDiscreteScheduler, EulerAncestralDiscreteScheduler

    pipe = StableDiffusionXLPipeline.from_pretrained(
        BASE_MODEL, torch_dtype=torch.float16, use_safetensors=True
    )
    if fast_mode():
        from huggingface_hub import hf_hub_download
        pipe.load_lora_weights(hf_hub_download(LIGHTNING_REPO, LIGHTNING_FILE))
        pipe.fuse_lora()
        pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
    else:
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
    pipe.to("cuda")
    _pipe = pipe
    return pipe


def build_prompt(episode: dict, shot: dict) -> str:
    looks = [episode["characters"][c]["look"] for c in shot.get("chars", []) if episode["characters"][c]["look"]]
    if not looks:
        looks = ["no humans"] if "student" not in shot["prompt"] and "crowd" not in shot["prompt"] else []
    parts = looks + [shot["prompt"], episode["style"], QUALITY_TAGS]
    return ", ".join(p for p in parts if p)


def generate(episode: dict, shot: dict, out: Path, seed: int) -> None:
    import torch
    pipe = load()
    kwargs = dict(
        prompt=build_prompt(episode, shot),
        width=WIDTH,
        height=HEIGHT,
        generator=torch.Generator("cuda").manual_seed(seed),
    )
    if fast_mode():
        kwargs.update(num_inference_steps=8, guidance_scale=0)
    else:
        kwargs.update(num_inference_steps=28, guidance_scale=6, negative_prompt=episode["negative"])
    pipe(**kwargs).images[0].save(out)


def placeholder(episode: dict, shot: dict, out: Path) -> None:
    """CPU fallback for testing the pipeline without a GPU."""
    from PIL import Image, ImageDraw, ImageFont
    import random
    rnd = random.Random(shot["id"])
    img = Image.new("RGB", (WIDTH, HEIGHT))
    d = ImageDraw.Draw(img)
    c1 = [rnd.randint(10, 90) for _ in range(3)]
    for y in range(HEIGHT):
        k = y / HEIGHT
        d.line([(0, y), (WIDTH, y)], fill=tuple(int(c * (1 - k) + 160 * k * (i == 2)) for i, c in enumerate(c1)))
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    d.multiline_text((60, 60), f"{shot['id']}\n" + "\n".join(_wrap(shot["prompt"], 60)), font=font, fill=(235, 235, 235))
    img.save(out)


def _wrap(text, n):
    words, line, lines = text.split(), "", []
    for w in words:
        if len(line) + len(w) > n:
            lines.append(line)
            line = ""
        line += w + " "
    return lines + [line]
