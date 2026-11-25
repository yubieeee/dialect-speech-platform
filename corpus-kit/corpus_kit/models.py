"""Manifest record schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class ClipRecord:
    id: str
    text_zh: str = ""
    prompt_text: str = ""
    prompt_text_status: str = "待校"
    wav: str = ""
    raw: str = ""
    role: str = ""
    speaker: str = ""
    locale: str = ""
    dialect: str = ""
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    sha256: str = ""
    source: str = "local"
    source_url: str = ""
    license_note: str = ""
    qc_status: str = ""
    qc_notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json_obj(self) -> dict[str, Any]:
        obj = asdict(self)
        # drop empty optional noise for readability
        cleaned: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "extra":
                if value:
                    cleaned[key] = value
                continue
            if key == "qc_notes":
                if value:
                    cleaned[key] = value
                continue
            if value in ("", None, []):
                continue
            cleaned[key] = value
        return cleaned

    def to_tts_obj(self) -> dict[str, Any]:
        """TTS training row: audio + text (+ optional phonetic); no provenance."""
        text = (self.prompt_text or self.text_zh or "").strip()
        out: dict[str, Any] = {
            "id": self.id,
            "text_zh": (self.text_zh or text).strip(),
            "prompt_text": text,
            "wav": self.wav,
        }
        for key in ("speaker", "role", "dialect", "locale", "duration_sec", "sample_rate", "channels"):
            val = getattr(self, key)
            if val not in ("", None):
                out[key] = val
        ph = (self.extra or {}).get("phonetic")
        if ph:
            out["phonetic"] = ph
        return {k: v for k, v in out.items() if v not in ("", None, [])}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClipRecord:
        known = {f.name for f in fields(cls)}
        data = dict(data)
        # TTS slim rows may carry phonetic at top-level
        phonetic = data.pop("phonetic", None)
        kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        if phonetic:
            extra = {**extra, "phonetic": phonetic}
        if extra:
            kwargs["extra"] = {**kwargs.get("extra", {}), **extra}
        if "qc_notes" in kwargs and kwargs["qc_notes"] is None:
            kwargs["qc_notes"] = []
        return cls(**kwargs)
