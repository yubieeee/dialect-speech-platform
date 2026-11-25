"""Burned-in (hard) subtitle OCR → timed cues / SRT."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .media import require_ffmpeg
from .subtitles import SubtitleCue, clean_subtitle_text

# UI chrome often OCR'd from WeChat / player overlays
_UI_NOISE = re.compile(
    r"^(?:"
    r"[\d.:]+x?"  # 1.0 / 01:23
    r"|播放|暂停|倍速|全屏|静音"
    r"|点赞|转发|分享|收藏|评论|关注"
    r"|微信|视频号"
    r")$",
    re.I,
)
_UI_CONTAINS = re.compile(
    r"(给阿嬷的情书|给阿嬤的情书|海南话表达|文昌市融媒体|文昌市广播|看网友|发表作品|"
    r"完成\d|5月\d+日|点赞|转发|收藏|评论)"
)
_CJK = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class OcrFrame:
    t: float
    text: str
    score: float


_ENGINE = None


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            from rapidocr import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "硬字幕 OCR 需要 rapidocr + onnxruntime。"
                "请执行: pip install -U rapidocr onnxruntime"
            ) from exc
        _ENGINE = RapidOCR()
    return _ENGINE


def _probe_duration(video: Path) -> float:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return float(out or 0)


def _extract_frame_png(video: Path, t: float, out_png: Path) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        str(out_png),
    ]
    subprocess.check_call(cmd)
    return out_png


def _crop_band(img: Image.Image, y0_ratio: float, y1_ratio: float) -> Image.Image:
    w, h = img.size
    y0 = max(0, min(h - 1, int(h * y0_ratio)))
    y1 = max(y0 + 1, min(h, int(h * y1_ratio)))
    return img.crop((0, y0, w, y1))


def _crop_region(
    img: Image.Image,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> Image.Image:
    """Crop by relative box [x0,y0,x1,y1] in 0..1."""
    w, h = img.size
    xa = max(0, min(w - 1, int(w * x0)))
    xb = max(xa + 1, min(w, int(w * x1)))
    ya = max(0, min(h - 1, int(h * y0)))
    yb = max(ya + 1, min(h, int(h * y1)))
    return img.crop((xa, ya, xb, yb))


def _normalize_ocr_text(text: str) -> str:
    t = clean_subtitle_text(text)
    t = re.sub(r"\s+", "", t)
    return t


def _is_noise(text: str) -> bool:
    if not text or len(text) < 2:
        return True
    if _UI_NOISE.match(text):
        return True
    if _UI_CONTAINS.search(text):
        # strip UI phrase; if almost nothing left, noise
        cleaned = _UI_CONTAINS.sub("", text)
        cleaned = re.sub(r"[！!。.\d:：/\s]+", "", cleaned)
        if len(_CJK.findall(cleaned)) < 2:
            return True
        # keep residual poetic text if substantial
    # prefer lines with some CJK for dialect news
    if not _CJK.search(text) and len(text) < 6:
        return True
    return False


def _strip_ui(text: str) -> str:
    t = _UI_CONTAINS.sub("", text)
    t = re.sub(r"(5月\d+日|00:\d{2}/\d{2}:\d{2})", "", t)
    return _normalize_ocr_text(t)


def ocr_image(img: Image.Image, *, min_score: float = 0.5) -> tuple[str, float]:
    engine = _get_engine()
    arr = np.asarray(img.convert("RGB"))
    out = engine(arr)
    txts = list(getattr(out, "txts", None) or ())
    scores = list(getattr(out, "scores", None) or ())
    if not txts:
        return "", 0.0
    kept: list[tuple[str, float]] = []
    for i, raw in enumerate(txts):
        sc = float(scores[i]) if i < len(scores) else 0.0
        if sc < min_score:
            continue
        t = _strip_ui(_normalize_ocr_text(str(raw)))
        if _is_noise(t):
            continue
        kept.append((t, sc))
    if not kept:
        return "", 0.0
    # join multi-box lines; for vertical captions RapidOCR often returns top→bottom
    text = _strip_ui("".join(t for t, _ in kept))
    score = sum(s for _, s in kept) / len(kept)
    if _is_noise(text):
        return "", 0.0
    return text, score


def sample_ocr_frames(
    video: Path,
    work_dir: Path,
    *,
    interval: float = 0.35,
    band: tuple[float, float] = (0.68, 0.95),
    region: tuple[float, float, float, float] | None = None,
    min_score: float = 0.5,
    max_frames: int = 0,
) -> list[OcrFrame]:
    video = Path(video).resolve()
    duration = _probe_duration(video)
    if duration <= 0:
        raise ValueError(f"无法读取时长: {video}")
    work_dir.mkdir(parents=True, exist_ok=True)
    frames: list[OcrFrame] = []
    t = 0.0
    idx = 0
    while t < duration - 0.05:
        if max_frames and idx >= max_frames:
            break
        png = work_dir / f"f_{idx:05d}_{t:.2f}.png"
        try:
            _extract_frame_png(video, t, png)
            img = Image.open(png)
            if region is not None:
                crop = _crop_region(img, *region)
            else:
                crop = _crop_band(img, band[0], band[1])
            text, score = ocr_image(crop, min_score=min_score)
        except Exception:
            text, score = "", 0.0
        frames.append(OcrFrame(t=round(t, 3), text=text, score=score))
        idx += 1
        t += interval
    return frames


def frames_to_cues(
    frames: list[OcrFrame],
    *,
    duration: float | None = None,
    min_hold: float = 0.35,
) -> list[SubtitleCue]:
    """Collapse consecutive same-text samples into timed cues."""
    cues: list[SubtitleCue] = []
    cur_text = ""
    cur_start = 0.0
    last_t = 0.0

    def flush(end: float) -> None:
        nonlocal cur_text, cur_start
        if cur_text and end - cur_start >= min_hold * 0.5:
            cues.append(SubtitleCue(start=cur_start, end=max(end, cur_start + 0.2), text=cur_text))
        cur_text = ""

    for fr in frames:
        last_t = fr.t
        text = fr.text
        if not text:
            if cur_text:
                flush(fr.t)
            continue
        if text == cur_text:
            continue
        if cur_text:
            # end previous slightly before new appears
            flush(max(cur_start + 0.15, fr.t - 0.05))
        cur_text = text
        cur_start = fr.t
    end = duration if duration is not None else (last_t + min_hold)
    if cur_text:
        flush(end)
    return cues


def write_srt(cues: list[SubtitleCue], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for i, c in enumerate(cues, 1):
        def ts(x: float) -> str:
            ms = int(round(x * 1000))
            h, rem = divmod(ms, 3600_000)
            m, rem = divmod(rem, 60_000)
            s, milli = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

        lines.append(str(i))
        lines.append(f"{ts(c.start)} --> {ts(c.end)}")
        lines.append(c.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def ocr_hardsubs_to_srt(
    video: Path,
    srt_out: Path | None = None,
    *,
    work_dir: Path | None = None,
    interval: float = 0.35,
    band: tuple[float, float] = (0.68, 0.95),
    region: tuple[float, float, float, float] | None = None,
    min_score: float = 0.5,
    max_frames: int = 0,
) -> tuple[list[SubtitleCue], Path]:
    """
    OCR burned-in subtitles from a screen recording / hardsub video.
    Writes sibling .srt (default: video stem + .srt) and returns cues.

    region: optional (x0,y0,x1,y1) relative crop — e.g. left vertical captions
    (0.02,0.15,0.42,0.70). If set, overrides band.
    """
    video = Path(video).resolve()
    if srt_out is None:
        srt_out = video.with_suffix(".srt")
    wd = Path(work_dir) if work_dir else video.parent / ".hardsub_ocr" / video.stem
    duration = _probe_duration(video)
    frames = sample_ocr_frames(
        video,
        wd,
        interval=interval,
        band=band,
        region=region,
        min_score=min_score,
        max_frames=max_frames,
    )
    cues = frames_to_cues(frames, duration=duration)
    write_srt(cues, srt_out)
    return cues, Path(srt_out)
