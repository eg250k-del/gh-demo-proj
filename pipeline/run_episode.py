"""Episode JSON -> finished MP4. Resumable: finished images/audio/shots are reused on re-run.

    python pipeline/run_episode.py episodes/ep01_pilot.json out/ep01
    python pipeline/run_episode.py episodes/ep01_pilot.json out/ep01 --cpu-test   # no GPU: placeholders + silent audio
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import images  # noqa: E402
import render  # noqa: E402
import tts  # noqa: E402

LINE_GAP, SHOT_PAD = 0.35, 0.6


def produce(episode: dict, out_dir: Path, cpu_test: bool = False, log=print) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    chars = episode["characters"]
    shots = episode["shots"]
    t0 = time.time()

    # 1) images
    for i, shot in enumerate(shots):
        img = work / f"{shot['id']}.png"
        if img.exists():
            continue
        log(f"[image {i + 1}/{len(shots)}] {shot['id']}")
        if cpu_test:
            images.placeholder(episode, shot, img)
        else:
            images.generate(episode, shot, img, seed=shot.get("seed", 1000 + i))
    log(f"images done in {time.time() - t0:.0f}s")

    # 2) voices + per-shot render, collecting subtitle cues on the global timeline
    shot_videos, cues, clock = [], [], 0.0
    for i, shot in enumerate(shots):
        line_wavs, line_lens = [], []
        for j, line in enumerate(shot["lines"]):
            wav = work / f"{shot['id']}_l{j}.wav"
            if not wav.exists():
                tts.synth(line["text"], chars[line["speaker"]]["voice"], wav, use_kokoro=not cpu_test)
            line_wavs.append(wav)
            line_lens.append(render._read(wav).size / tts.SR)
        audio = work / f"{shot['id']}_audio.wav"
        dur = render.shot_audio(line_wavs, LINE_GAP, SHOT_PAD, shot.get("sfx"), tts.SR, audio)
        dur = max(dur, shot.get("min_duration", 2.5))

        t = clock + 0.3
        for line, ln in zip(shot["lines"], line_lens):
            spk = chars[line["speaker"]]["name"]
            cues.append((t, t + ln, spk, line["text"], line["speaker"] == "system"))
            t += ln + LINE_GAP

        video = work / f"{shot['id']}.mp4"
        if not video.exists():
            log(f"[render {i + 1}/{len(shots)}] {shot['id']} ({dur:.1f}s, {shot.get('camera', 'static')})")
            tmp = work / f"{shot['id']}.tmp.mp4"
            render.render_shot(shot, work / f"{shot['id']}.png", audio, dur, tmp, work)
            tmp.rename(video)
        shot_videos.append(video)
        clock += dur

    # 3) final mix
    final = out_dir / "final.mp4"
    music = Path(__file__).parent.parent / "assets" / "music.mp3"
    log("[final] concat + music + subtitles")
    render.finalize(shot_videos, clock, cues, work, final, music if music.exists() else None)
    log(f"DONE: {final} — {clock:.0f}s of video in {time.time() - t0:.0f}s")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("out")
    ap.add_argument("--cpu-test", action="store_true")
    a = ap.parse_args()
    produce(json.loads(Path(a.episode).read_text()), Path(a.out), cpu_test=a.cpu_test)
