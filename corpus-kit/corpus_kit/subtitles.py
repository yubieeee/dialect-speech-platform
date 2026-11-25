"""Subtitle discovery, extraction, and cue parsing (SRT / VTT / ASS)."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .media import require_ffmpeg

TIME_SRT = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})"
)
TIME_VTT = re.compile(
    r"(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})\.(?P<ms>\d{1,3})"
)
ASS_DIALOGUE = re.compile(
    r"^Dialogue:\s*\d+,"
    r"(?P<start>\d+:\d+:\d+\.\d+),"
    r"(?P<end>\d+:\d+:\d+\.\d+),"
    r"[^,]*,"  # style
    r"[^,]*,"  # name
    r"[^,]*,"  # marginL
    r"[^,]*,"  # marginR
    r"[^,]*,"  # marginV
    r"[^,]*,"  # effect
    r"(?P<text>.*)$"
)
TAG_RE = re.compile(r"<[^>]+>")
ASS_OVERRIDE = re.compile(r"\{[^}]*\}")


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _hms_to_sec(h: str | None, m: str, s: str, ms: str) -> float:
    hours = int(h or 0)
    millis = int(ms.ljust(3, "0")[:3])
    return hours * 3600 + int(m) * 60 + int(s) + millis / 1000.0


def _parse_ass_time(raw: str) -> float:
    # H:MM:SS.cs (centiseconds)
    parts = raw.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"bad ASS time: {raw}")
    h, m, rest = parts
    if "." in rest:
        sec, cs = rest.split(".", 1)
        frac = int(cs.ljust(2, "0")[:2]) / 100.0
    else:
        sec, frac = rest, 0.0
    return int(h) * 3600 + int(m) * 60 + int(sec) + frac


def clean_subtitle_text(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = ASS_OVERRIDE.sub("", t)
    t = TAG_RE.sub("", t)
    t = t.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n+", "", t)  # join multi-line cue into one sentence blob
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    # keep Chinese punctuation spacing tidy
    return t.strip(" \t-–—")


def parse_srt(content: str) -> list[SubtitleCue]:
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n").replace("\r", "\n").strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        # optional index line
        idx = 0
        if lines[0].strip().isdigit():
            idx = 1
        if idx >= len(lines):
            continue
        m = re.search(
            r"(?P<a>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(?P<b>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
            lines[idx],
        )
        if not m:
            continue
        def _one(raw: str) -> float:
            # accept 00:00:01,000 or 00:00:01.000
            norm = raw.strip()
            if "." in norm and "," not in norm:
                # last component millis with dot
                head, ms = norm.rsplit(".", 1)
                norm = f"{head},{ms}"
            mm = TIME_SRT.fullmatch(norm) or TIME_SRT.search(norm)
            if not mm:
                raise ValueError(raw)
            return _hms_to_sec(mm.group("h"), mm.group("m"), mm.group("s"), mm.group("ms"))

        try:
            start = _one(m.group("a"))
            end = _one(m.group("b"))
        except ValueError:
            continue
        text = clean_subtitle_text("\n".join(lines[idx + 1 :]))
        if text and end > start:
            cues.append(SubtitleCue(start=start, end=end, text=text))
    return cues


def parse_vtt(content: str) -> list[SubtitleCue]:
    body = content.replace("\r\n", "\n").replace("\r", "\n")
    if body.lstrip().startswith("WEBVTT"):
        body = re.sub(r"^WEBVTT[^\n]*\n", "", body.lstrip(), count=1)
    # drop NOTE / STYLE blocks lightly
    body = re.sub(r"(?m)^(NOTE|STYLE|REGION).*?(?:\n\n|\Z)", "", body, flags=re.S)
    blocks = re.split(r"\n\s*\n", body.strip())
    cues: list[SubtitleCue] = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        idx = 0
        if "-->" not in lines[0] and len(lines) > 1 and "-->" in lines[1]:
            idx = 1
        if "-->" not in lines[idx]:
            continue
        m = re.search(
            r"(?P<a>[0-9:.]{4,})\s*-->\s*(?P<b>[0-9:.]{4,})",
            lines[idx],
        )
        if not m:
            continue

        def _one(raw: str) -> float:
            mm = TIME_VTT.fullmatch(raw.strip()) or TIME_VTT.search(raw.strip())
            if not mm:
                # try srt-like
                raw2 = raw.strip().replace(".", ",")
                mm2 = TIME_SRT.fullmatch(raw2)
                if not mm2:
                    raise ValueError(raw)
                return _hms_to_sec(mm2.group("h"), mm2.group("m"), mm2.group("s"), mm2.group("ms"))
            return _hms_to_sec(mm.group("h"), mm.group("m"), mm.group("s"), mm.group("ms"))

        try:
            start = _one(m.group("a"))
            end = _one(m.group("b"))
        except ValueError:
            continue
        text = clean_subtitle_text("\n".join(lines[idx + 1 :]))
        if text and end > start:
            cues.append(SubtitleCue(start=start, end=end, text=text))
    return cues


def parse_ass(content: str) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    for line in content.replace("\r\n", "\n").split("\n"):
        if not line.startswith("Dialogue:"):
            continue
        m = ASS_DIALOGUE.match(line)
        if not m:
            continue
        try:
            start = _parse_ass_time(m.group("start"))
            end = _parse_ass_time(m.group("end"))
        except ValueError:
            continue
        text = clean_subtitle_text(m.group("text"))
        if text and end > start:
            cues.append(SubtitleCue(start=start, end=end, text=text))
    return cues


def parse_subtitle_file(path: Path) -> list[SubtitleCue]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suf = path.suffix.lower()
    if suf == ".srt":
        return parse_srt(raw)
    if suf in {".vtt", ".webvtt"}:
        return parse_vtt(raw)
    if suf in {".ass", ".ssa"}:
        return parse_ass(raw)
    # sniff
    if "WEBVTT" in raw[:20]:
        return parse_vtt(raw)
    if "[Script Info]" in raw or "Dialogue:" in raw:
        return parse_ass(raw)
    return parse_srt(raw)


def find_sidecar_subtitle(media: Path) -> Path | None:
    """Look for foo.srt / foo.zh.srt / foo.chs.vtt next to media."""
    parent = media.parent
    stem = media.stem
    candidates: list[Path] = []
    for suf in (".srt", ".vtt", ".webvtt", ".ass", ".ssa"):
        candidates.append(parent / f"{stem}{suf}")
    # language-tagged
    for p in sorted(parent.glob(f"{stem}.*")):
        if p.suffix.lower() in {".srt", ".vtt", ".webvtt", ".ass", ".ssa"}:
            candidates.append(p)
        # foo.zh.srt → suffix .srt, stem foo.zh
        if p.name.startswith(stem + ".") and any(
            p.name.endswith(ext) for ext in (".srt", ".vtt", ".ass", ".ssa")
        ):
            candidates.append(p)
    seen: set[Path] = set()
    for c in candidates:
        c = c.resolve()
        if c in seen or not c.is_file():
            continue
        seen.add(c)
        return c
    return None


def list_embedded_subtitle_streams(media: Path) -> list[dict]:
    require_ffmpeg()
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "s",
        str(media),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return list(data.get("streams") or [])


def extract_embedded_subtitle(media: Path, out_srt: Path, *, stream_index: int = 0) -> Path:
    """Dump soft subtitle stream to SRT via ffmpeg."""
    require_ffmpeg()
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media),
        "-map",
        f"0:s:{stream_index}",
        str(out_srt),
    ]
    subprocess.check_call(cmd)
    if not out_srt.is_file() or out_srt.stat().st_size == 0:
        raise RuntimeError(f"内嵌字幕导出失败: {media}")
    return out_srt


def load_cues_for_media(
    media: Path,
    *,
    work_dir: Path | None = None,
    prefer_lang: str = "",
    ocr_hardsubs: bool = False,
    ocr_interval: float = 0.35,
    ocr_band: tuple[float, float] = (0.68, 0.95),
    ocr_region: tuple[float, float, float, float] | None = None,
    ocr_min_score: float = 0.5,
) -> tuple[list[SubtitleCue], str]:
    """
    Resolve cues for a media file.
    Order: sidecar → embedded → optional hardsub OCR.
    Returns (cues, source_tag) e.g. sidecar_srt / embedded_0 / hardsub_ocr / "".
    """
    side = find_sidecar_subtitle(media)
    if side is not None:
        cues = parse_subtitle_file(side)
        if cues:
            return cues, f"sidecar_{side.suffix.lower().lstrip('.')}"

    streams = list_embedded_subtitle_streams(media)
    if streams:
        chosen = 0
        if prefer_lang:
            want = prefer_lang.lower()
            for i, st in enumerate(streams):
                tags = st.get("tags") or {}
                lang = str(tags.get("language") or tags.get("LANGUAGE") or "").lower()
                title = str(tags.get("title") or "").lower()
                if want in lang or want in title or want in {"zh", "chi", "zho"} and lang in {
                    "zh",
                    "chi",
                    "zho",
                    "zh-cn",
                    "zh-hans",
                }:
                    chosen = i
                    break

        out_dir = work_dir or (media.parent / ".subs_cache")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_srt = out_dir / f"{media.stem}__emb{chosen}.srt"
        try:
            extract_embedded_subtitle(media, out_srt, stream_index=chosen)
            cues = parse_srt(out_srt.read_text(encoding="utf-8", errors="replace"))
            if cues:
                return cues, f"embedded_{chosen}"
        except Exception:
            pass

    if ocr_hardsubs:
        from .hardsubs import ocr_hardsubs_to_srt
        from .paths import VIDEO_SUFFIXES

        if media.suffix.lower() not in VIDEO_SUFFIXES and media.suffix.lower() not in {
            ".mp4",
            ".mkv",
            ".mov",
            ".avi",
            ".webm",
            ".m4v",
        }:
            return [], ""
        out_dir = work_dir or (media.parent / ".hardsub_ocr")
        try:
            cues, srt_path = ocr_hardsubs_to_srt(
                media,
                media.with_suffix(".srt"),
                work_dir=out_dir / media.stem,
                interval=ocr_interval,
                band=ocr_band,
                region=ocr_region,
                min_score=ocr_min_score,
            )
        except Exception:
            return [], ""
        if cues:
            return cues, f"hardsub_ocr:{srt_path.name}"
    return [], ""


def merge_cues(
    cues: list[SubtitleCue],
    *,
    min_sec: float = 1.5,
    max_sec: float = 20.0,
    max_gap: float = 0.45,
) -> list[SubtitleCue]:
    """Merge consecutive short/nearby cues into training-sized utterances."""
    if not cues:
        return []
    ordered = sorted(cues, key=lambda c: (c.start, c.end))
    merged: list[SubtitleCue] = []
    cur = SubtitleCue(start=ordered[0].start, end=ordered[0].end, text=ordered[0].text)
    for nxt in ordered[1:]:
        gap = nxt.start - cur.end
        new_end = max(cur.end, nxt.end)
        new_dur = new_end - cur.start
        # 只在当前句仍短于 min_sec 时吞并下一句，避免正常字幕被糊成一条
        should_merge = cur.duration < min_sec and gap <= max_gap and new_dur <= max_sec
        if should_merge:
            cur = SubtitleCue(
                start=cur.start,
                end=new_end,
                text=clean_subtitle_text(f"{cur.text}{nxt.text}"),
            )
        else:
            if cur.text.strip():
                merged.append(cur)
            cur = SubtitleCue(start=nxt.start, end=nxt.end, text=nxt.text)
    if cur.text.strip():
        merged.append(cur)

    # hard-split overlong
    final: list[SubtitleCue] = []
    for c in merged:
        if c.duration <= max_sec or not c.text:
            if c.duration >= min_sec * 0.5:  # keep slightly short with text
                final.append(c)
            elif c.text:
                final.append(c)
            continue
        # no reliable word timings — keep as one overlong (QC will warn)
        final.append(c)
    return final


def text_for_span(
    cues: list[SubtitleCue],
    start: float,
    end: float,
    *,
    min_overlap: float = 0.15,
) -> str:
    """Collect cue text overlapping [start, end]."""
    parts: list[str] = []
    for c in cues:
        ov = min(end, c.end) - max(start, c.start)
        if ov >= min_overlap or (ov > 0 and ov / max(c.duration, 1e-6) >= 0.5):
            parts.append(c.text)
    return clean_subtitle_text("".join(parts))
