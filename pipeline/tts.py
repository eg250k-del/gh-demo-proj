"""Voice lines with Kokoro TTS (fast, free, Apache-2.0). Falls back to silence for CPU-less tests."""
import wave
from pathlib import Path

import numpy as np

SR = 24000
_pipes = {}


def _kokoro(lang: str):
    if lang not in _pipes:
        from kokoro import KPipeline
        _pipes[lang] = KPipeline(lang_code=lang)
    return _pipes[lang]


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def synth(text: str, voice: str, out: Path, use_kokoro: bool = True) -> float:
    """Writes a wav and returns its duration in seconds."""
    audio = None
    if use_kokoro:
        lang = "b" if voice.startswith("b") else "a"  # bm_/bf_ = British, am_/af_ = American
        chunks = [a for _, _, a in _kokoro(lang)(text, voice=voice, speed=1.0)]
        audio = np.concatenate([np.asarray(c, dtype=np.float32) for c in chunks])
    if audio is None:
        audio = np.zeros(int(SR * max(1.0, len(text.split()) * 0.36)), dtype=np.float32)
    write_wav(out, audio)
    return len(audio) / SR
