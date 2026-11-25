"""Extract audio from local video/audio; split by subtitles or silence."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .media import audio_stats, require_ffmpeg, transcode_to_wav16k
from .paths import AUDIO_SUFFIXES, VIDEO_SUFFIXES
from .subtitles import (
    SubtitleCue,
    load_cues_for_media,
    merge_cues,
    text_for_span,
)

SILENCE_RE = re.compile(
    r"silence_(?:start|end):\s*([0-9.]+)",
)


@dataclass
class MinedClip:
    path: Path
    start: float
    end: float
    text: str = ""
    text_source: str = ""  # sidecar_srt / embedded_0 / silence_overlap / none


def list_media_files(input_path: Path, *, recursive: bool = True) -> list[Path]:
    input_path = Path(input_path).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if input_path.is_file():
        files = [input_path]
    elif recursive:
        files = sorted(p for p in input_path.rglob("*") if p.is_file())
    else:
        files = sorted(p for p in input_path.iterdir() if p.is_file())
    media = [
        p
        for p in files
        if p.suffix.lower() in AUDIO_SUFFIXES or p.suffix.lower() in VIDEO_SUFFIXES
    ]
    # skip derived/cache
    media = [p for p in media if ".subs_cache" not in p.parts and "mine_work" not in p.parts]
    if not media:
        raise ValueError(f"未找到视频/音频: {input_path}")
    return media


def extract_full_wav16k(src: Path, dst: Path) -> dict:
    """Pull audio track (works for video too) into 16k mono wav."""
    return transcode_to_wav16k(src, dst)


def detect_silence_intervals(
    wav: Path,
    *,
    noise_db: float = -35.0,
    min_silence: float = 0.5,
) -> list[tuple[float, float]]:
    """Return list of (silence_start, silence_end) using ffmpeg silencedetect."""
    require_ffmpeg()
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(wav),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log = (proc.stderr or "") + (proc.stdout or "")
    starts: list[float] = []
    ends: list[float] = []
    for line in log.splitlines():
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([0-9.]+)", line)
            if m:
                starts.append(float(m.group(1)))
        if "silence_end:" in line:
            m = re.search(r"silence_end:\s*([0-9.]+)", line)
            if m:
                ends.append(float(m.group(1)))
    intervals: list[tuple[float, float]] = []
    i = j = 0
    while i < len(starts) and j < len(ends):
        if ends[j] >= starts[i]:
            intervals.append((starts[i], ends[j]))
            i += 1
            j += 1
        else:
            j += 1
    return intervals


def speech_segments_from_silence(
    duration: float,
    silences: list[tuple[float, float]],
    *,
    pad: float = 0.05,
) -> list[tuple[float, float]]:
    """Invert silence intervals into speech segments within [0, duration]."""
    if duration <= 0:
        return []
    silence_set = {(round(s, 3), round(e, 3)) for s, e in silences}
    segments: list[tuple[float, float]] = []
    t = 0.0
    for s, e in sorted(silences):
        if s - t > 0.05:
            segments.append((max(0.0, t - pad), min(duration, s + pad)))
        t = e
    if duration - t > 0.05:
        segments.append((max(0.0, t - pad), duration))
    if not segments and not silence_set:
        return [(0.0, duration)]
    return [(round(a, 3), round(b, 3)) for a, b in segments if b - a > 0.05]


def export_segment(src_wav: Path, dst: Path, start: float, end: float) -> dict:
    require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        str(src_wav),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    subprocess.check_call(cmd)
    return audio_stats(dst)


def _export_clips(
    full: Path,
    work_dir: Path,
    stem: str,
    spans: list[tuple[float, float, str, str]],
) -> list[MinedClip]:
    clips: list[MinedClip] = []
    for i, (start, end, text, text_source) in enumerate(spans):
        out = work_dir / f"{stem}__clip{i:04d}.wav"
        export_segment(full, out, start, end)
        clips.append(
            MinedClip(
                path=out,
                start=start,
                end=end,
                text=text,
                text_source=text_source,
            )
        )
    return clips


def mine_file_to_clips(
    src: Path,
    work_dir: Path,
    *,
    split_mode: str = "auto",
    use_subtitles: bool = True,
    prefer_lang: str = "zh",
    ocr_hardsubs: bool = False,
    ocr_interval: float = 0.35,
    ocr_band: tuple[float, float] = (0.68, 0.95),
    ocr_region: tuple[float, float, float, float] | None = None,
    ocr_min_score: float = 0.5,
    noise_db: float = -35.0,
    min_silence: float = 0.5,
    min_sec: float = 1.5,
    max_sec: float = 20.0,
    require_text: bool = False,
) -> tuple[list[MinedClip], dict]:
    """
    From one local media file, produce wav clips with optional paired text.

    split_mode:
      - auto: 有字幕则按字幕轴切；否则静音切
      - cues: 必须用字幕切
      - silence: 静音切；若有字幕则按时间重叠填文本
      - none: 整段一条
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    full = work_dir / f"{stem}__full.wav"
    extract_full_wav16k(src, full)
    stats = audio_stats(full)
    duration = float(stats["duration_sec"] or 0)

    cues: list[SubtitleCue] = []
    cue_source = ""
    if use_subtitles:
        cues, cue_source = load_cues_for_media(
            src,
            work_dir=work_dir / "subs",
            prefer_lang=prefer_lang,
            ocr_hardsubs=ocr_hardsubs,
            ocr_interval=ocr_interval,
            ocr_band=ocr_band,
            ocr_region=ocr_region,
            ocr_min_score=ocr_min_score,
        )

    meta = {
        "media": str(src),
        "duration_sec": duration,
        "cue_count": len(cues),
        "cue_source": cue_source,
        "split_mode": split_mode,
    }

    mode = split_mode
    if mode == "auto":
        mode = "cues" if cues else "silence"

    if mode == "cues":
        if not cues:
            raise ValueError(f"要求按字幕切句，但未找到字幕: {src}")
        merged = merge_cues(cues, min_sec=min_sec, max_sec=max_sec)
        spans: list[tuple[float, float, str, str]] = []
        for c in merged:
            if c.end <= c.start:
                continue
            if (c.end - c.start) < min_sec * 0.4 and not c.text:
                continue
            spans.append((c.start, min(c.end, duration), c.text, cue_source or "cues"))
        clips = _export_clips(full, work_dir, stem, spans)
    elif mode == "none":
        text = text_for_span(cues, 0.0, duration) if cues else ""
        src_tag = cue_source if text else "none"
        out = work_dir / f"{stem}__clip0000.wav"
        if out.exists():
            out.unlink()
        full.replace(out)
        clips = [
            MinedClip(
                path=out,
                start=0.0,
                end=duration,
                text=text,
                text_source=src_tag,
            )
        ]
        return clips, meta
    else:  # silence
        silences = detect_silence_intervals(full, noise_db=noise_db, min_silence=min_silence)
        segments = speech_segments_from_silence(duration, silences)
        spans = []
        for start, end in segments:
            length = end - start
            if length < min_sec:
                continue
            t0 = start
            while t0 < end - 0.05:
                t1 = min(end, t0 + max_sec)
                if t1 - t0 < min_sec:
                    break
                text = text_for_span(cues, t0, t1) if cues else ""
                tag = (cue_source + "+overlap") if text else "none"
                spans.append((t0, t1, text, tag))
                t0 = t1
        if not spans:
            text = text_for_span(cues, 0.0, duration) if cues else ""
            spans = [(0.0, duration, text, cue_source if text else "none")]
        clips = _export_clips(full, work_dir, stem, spans)

    if require_text:
        clips = [c for c in clips if c.text.strip()]
        if not clips:
            raise ValueError(f"有切段但无可用文本（字幕缺失或对不齐）: {src}")

    # drop intermediate full when we exported segments
    if full.exists() and mode != "none":
        try:
            full.unlink(missing_ok=True)
        except TypeError:
            if full.exists():
                full.unlink()

    meta["clip_count"] = len(clips)
    meta["with_text"] = sum(1 for c in clips if c.text.strip())
    return clips, meta
