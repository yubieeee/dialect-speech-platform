"""Shared paths for CosyVoice3 debug lab."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOICE_ENGINE = ROOT / "voice-engine"
RUNTIME = VOICE_ENGINE / ".runtime"
DEFAULT_MODEL_DIR = RUNTIME / "models" / "Fun-CosyVoice3-0.5B-2512"
DEFAULT_COSY_SOURCE = RUNTIME / "sources" / "CosyVoice"
DIALECT_ASSETS = ROOT / "dialect-assets"
WENCHANG = DIALECT_ASSETS / "wenchang"
EVALS = WENCHANG / "evals"
REFS = WENCHANG / "refs"
WAV16K = WENCHANG / "wav16k"
UPLOADS = WENCHANG / "lab_uploads"
PREVIEW = UPLOADS / "preview"
TRAIN_EXPORTS = WENCHANG / "train" / "exports"
EVAL_BANK_JSON = WENCHANG / "sentences" / "eval_bank_v0.json"
RUNTIME_REFS = RUNTIME / "tts" / "refs"

UPSTREAM_YAML = (
    DEFAULT_COSY_SOURCE / "examples" / "libritts" / "cosyvoice3" / "conf" / "cosyvoice3.yaml"
)
UPSTREAM_DS = (
    DEFAULT_COSY_SOURCE / "examples" / "libritts" / "cosyvoice3" / "conf" / "ds_stage2.json"
)


def env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def ensure_lab_dirs() -> None:
    for path in (
        WENCHANG,
        EVALS,
        REFS,
        WAV16K,
        UPLOADS,
        PREVIEW,
        TRAIN_EXPORTS,
        WENCHANG / "raw",
        WENCHANG / "lexicon",
        WENCHANG / "phonology",
        WENCHANG / "sentences",
        WENCHANG / "sources" / "notes",
        WENCHANG / "train" / "data",
    ):
        path.mkdir(parents=True, exist_ok=True)
