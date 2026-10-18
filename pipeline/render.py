"""Motion-comic renderer: still image -> camera move + shake/flash + system panel, then concat, music, subtitles."""
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_encoder = None
# older ffmpeg builds (e.g. 4.4) cannot negotiate sidechaincompress formats on their own
AFMT = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")


def encoder_args():
    """h264_nvenc on GPU nodes, libx264 otherwise."""
    global _encoder
    if _encoder is None:
        test = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
             "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
        _encoder = (["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21"] if test.returncode == 0
                    else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
    return _encoder


def camera_filter(camera: str, frames: int) -> str:
    """zoompan expressions; image is pre-scaled to 2x output size to avoid zoompan jitter."""
    p = f"(on/{max(frames - 1, 1)})"           # progress 0..1
    ease = f"(0.5-0.5*cos(PI*{p}))"
    center_x, center_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    z, x, y = "1.12", center_x, center_y
    if camera == "zoom_in":
        z = f"1.0+0.22*{ease}"
    elif camera == "zoom_out":
        z = f"1.25-0.22*{ease}"
    elif camera == "pan_right":
        x = f"(iw-iw/zoom)*{ease}"
    elif camera == "pan_left":
        x = f"(iw-iw/zoom)*(1-{ease})"
    elif camera == "pan_up":
        y = f"(ih-ih/zoom)*(1-{ease})"
    elif camera == "shake":
        z = f"1.15+0.08*{ease}"
    return (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS}")


def system_panel(lines, out: Path):
    """Blue holographic 'System' window, transparent PNG."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pw, ph = 900, 120 + 70 * len(lines)
    x0, y0 = (W - pw) // 2, (H - ph) // 2 - 80
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([x0 - 10, y0 - 10, x0 + pw + 10, y0 + ph + 10], 24, fill=(40, 160, 255, 160))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], 18, fill=(6, 18, 40, 225), outline=(90, 200, 255, 255), width=4)
    d.line([x0 + 30, y0 + 105, x0 + pw - 30, y0 + 105], fill=(90, 200, 255, 200), width=2)
    for i, text in enumerate(lines):
        font = ImageFont.truetype(FONT_BOLD, 50 if i == 0 else 40)
        tw = d.textlength(text, font=font)
        color = (150, 225, 255, 255) if i == 0 else (235, 245, 255, 255)
        d.text(((W - tw) / 2, y0 + 30 + (0 if i == 0 else 40 + 70 * i)), text, font=font, fill=color)
    img.save(out)


def render_shot(shot: dict, image: Path, audio: Path, duration: float, out: Path, work: Path):
    frames = int(math.ceil(duration * FPS))
    vf = camera_filter(shot.get("camera", "static"), frames)
    if shot.get("camera") == "shake":
        amp = 22
        vf += (f",crop={W - 2 * amp}:{H - 2 * amp}:"
               f"'{amp}+{amp}*sin(n*2.7)*exp(-t*2.5)':'{amp}+{amp}*cos(n*3.3)*exp(-t*2.5)',scale={W}:{H}"
               f",fade=t=in:st=0:d=0.25:color=white")
    else:
        vf += ",fade=t=in:st=0:d=0.2"
    inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(image), "-i", str(audio)]
    graph = f"[0:v]{vf},setsar=1,format=yuv420p[v]"
    if shot.get("system"):
        panel = work / f"{shot['id']}_panel.png"
        system_panel(shot["system"], panel)
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(panel)]
        graph = (f"[0:v]{vf},setsar=1[bg];[2:v]format=rgba,fade=t=in:st=0.3:d=0.35:alpha=1[p];"
                 f"[bg][p]overlay=0:0:shortest=1,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "1:a",
         "-t", f"{duration:.3f}", *encoder_args(), "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)])


# ---------- audio helpers ----------

def _read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32767


def sfx(kind: str, sr: int) -> np.ndarray:
    t = np.arange(int(sr * (1.2 if kind == "impact" else 1.0))) / sr
    if kind == "impact":  # low boom + noise crack
        boom = np.sin(2 * np.pi * (55 + 40 * np.exp(-t * 8)) * t) * np.exp(-t * 4)
        crack = np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 25)
        return 0.9 * boom + 0.35 * crack
    # "chime": bright system ping
    return sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 3) for f in (880, 1320, 1760)) * 0.25


def shot_audio(line_wavs, gap: float, pad: float, kind: str | None, sr: int, out: Path) -> float:
    from tts import write_wav
    parts = [np.zeros(int(sr * 0.3), dtype=np.float32)]
    for wav in line_wavs:
        parts += [_read(wav), np.zeros(int(sr * gap), dtype=np.float32)]
    audio = np.concatenate(parts + [np.zeros(int(sr * pad), dtype=np.float32)])
    if kind:
        fx = sfx(kind, sr)[: len(audio)]
        audio[: len(fx)] += 0.6 * fx
    write_wav(out, audio / max(1.0, np.abs(audio).max()))
    return len(audio) / sr


def music_bed(duration: float, out: Path):
    """Dark cinematic drone, generated (no copyright). Replace with assets/music.mp3 for real tracks."""
    run(["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"sine=f=55:d={duration}", "-f", "lavfi", "-i", f"sine=f=82.4:d={duration}",
         "-f", "lavfi", "-i", f"sine=f=110:d={duration}", "-f", "lavfi", "-i", f"anoisesrc=d={duration}:c=pink:a=0.02",
         "-filter_complex", "[0][1][2][3]amix=4,lowpass=f=900,tremolo=f=0.15:d=0.5,volume=0.5,"
                            "afade=t=in:d=3,afade=t=out:st=" + f"{max(duration - 3, 0)}:d=3",
         "-ar", "48000", "-ac", "2", str(out)])


# ---------- subtitles ----------

def _ts(s: float) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"


def write_ass(cues, out: Path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,120,120,70,1
Style: System,DejaVu Sans,58,&H00FFE08C,&H00FFFFFF,&H00401000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,120,120,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    rows = []
    for start, end, speaker, text, is_system in cues:
        label = "" if speaker in ("Narrator", "System") else "{\\c&H66CCFF&}" + speaker + ": {\\c&HFFFFFF&}"
        rows.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},{'System' if is_system else 'Main'},,0,0,0,,{label}{text}")
    out.write_text(head + "\n".join(rows) + "\n")


def finalize(shot_videos, total: float, cues, work: Path, out: Path, music: Path | None = None):
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in shot_videos))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
    if music is None:
        music = work / "music.wav"
        music_bed(total, music)
    ass = work / "subs.ass"
    write_ass(cues, ass)
    # music ducks under the voices (sidechain), subtitles burned in
    run(["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-stream_loop", "-1", "-i", str(music),
         "-filter_complex",
         f"[0:a]{AFMT},asplit=2[voice][sc];[1:a]{AFMT},volume=0.35[m];"
         "[m][sc]sidechaincompress=threshold=0.03:ratio=6:release=400[duck];"
         f"[voice][duck]amix=2:duration=first:normalize=0,alimiter=limit=0.95[a];[0:v]ass={ass}[v]",
         "-map", "[v]", "-map", "[a]", *encoder_args(), "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)])
