"""ffmpeg / ffprobe helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("需要系统安装 ffmpeg 与 ffprobe")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def probe(path: Path) -> dict:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,sample_rate,channels,bits_per_sample",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def audio_stats(path: Path) -> dict:
    info = probe(path)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise ValueError(f"无音频流: {path}")
    stream = streams[0]
    duration = float(info.get("format", {}).get("duration") or 0.0)
    return {
        "duration_sec": round(duration, 3),
        "sample_rate": int(stream.get("sample_rate") or 0) or None,
        "channels": int(stream.get("channels") or 0) or None,
        "codec_name": stream.get("codec_name"),
    }


def transcode_to_wav16k(src: Path, dst: Path) -> dict:
    """Convert to mono 16 kHz PCM16 WAV."""
    require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    subprocess.check_call(cmd)
    stats = audio_stats(dst)
    stats["sha256"] = sha256_file(dst)
    return stats
