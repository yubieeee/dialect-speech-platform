"""Dialect asset layout under dialect-assets/."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIALECT_ASSETS = ROOT / "dialect-assets"
VOICE_DATA = DIALECT_ASSETS  # 旧名别名

DIALECT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".webm"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".m4v", ".webm"}
# webm 可音可视；list 阶段两边都会收，ffmpeg 自行取音轨

MEDIA_INBOX = "inbox"


def dialect_root(dialect: str) -> Path:
    name = dialect.strip().lower()
    if not DIALECT_RE.fullmatch(name):
        raise ValueError(f"非法方言目录名: {dialect!r}（建议如 wenchang / shanghai）")
    return VOICE_DATA / name


def ensure_dialect_dirs(dialect: str) -> Path:
    root = dialect_root(dialect)
    for rel in (
        "raw",
        "wav16k",
        "refs",
        "evals",
        "lab_uploads",
        MEDIA_INBOX,
        "image",
        "video",
        "sentences",
        "lexicon",
        "phonology",
        "sources/notes",
        "sources/private_files",
        "sources/mine_work",
        "sources/crawl_dl",
        "train/exports",
        "train/data",
        "train/exp",
        "reports",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def manifest_path(dialect: str) -> Path:
    return dialect_root(dialect) / "manifest.jsonl"


def reports_dir(dialect: str) -> Path:
    return dialect_root(dialect) / "reports"
