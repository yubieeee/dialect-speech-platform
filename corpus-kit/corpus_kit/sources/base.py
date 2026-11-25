"""Pluggable source adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class CollectedItem:
    path: Path
    text_zh: str = ""
    prompt_text: str = ""
    role: str = ""
    speaker: str = ""
    source_url: str = ""
    license_note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    name: str

    def collect(self) -> list[CollectedItem]:
        """Return local file paths ready to copy/import."""
        ...
