"""Import audio files from a local directory."""

from __future__ import annotations

from pathlib import Path

from ..paths import AUDIO_SUFFIXES
from .base import CollectedItem


class LocalImportSource:
    name = "local"

    def __init__(
        self,
        input_path: Path,
        *,
        text_from_filename: bool = False,
        speaker: str = "",
        recursive: bool = True,
    ) -> None:
        self.input_path = Path(input_path).expanduser().resolve()
        self.text_from_filename = text_from_filename
        self.speaker = speaker
        self.recursive = recursive

    def collect(self) -> list[CollectedItem]:
        if not self.input_path.exists():
            raise FileNotFoundError(self.input_path)
        files: list[Path]
        if self.input_path.is_file():
            files = [self.input_path]
        elif self.recursive:
            files = sorted(p for p in self.input_path.rglob("*") if p.is_file())
        else:
            files = sorted(p for p in self.input_path.iterdir() if p.is_file())
        items: list[CollectedItem] = []
        for path in files:
            if path.suffix.lower() not in AUDIO_SUFFIXES:
                continue
            text = path.stem if self.text_from_filename else ""
            items.append(
                CollectedItem(
                    path=path,
                    text_zh=text,
                    prompt_text=text,
                    speaker=self.speaker,
                    license_note="local_upload",
                )
            )
        if not items:
            raise ValueError(f"未找到音频文件: {self.input_path}")
        return items
