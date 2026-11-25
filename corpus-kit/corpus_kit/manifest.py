"""JSONL manifest load / save / merge."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ClipRecord


def load_manifest(path: Path) -> list[ClipRecord]:
    if not path.is_file():
        return []
    rows: list[ClipRecord] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(ClipRecord.from_dict(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} JSON 无效") from exc
    return rows


def save_manifest(path: Path, rows: list[ClipRecord], *, tts_only: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if tts_only:
        objs = [r.to_tts_obj() for r in rows if (r.wav and (r.prompt_text or r.text_zh))]
    else:
        objs = [r.to_json_obj() for r in rows]
    body = "\n".join(json.dumps(o, ensure_ascii=False) for o in objs)
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


def merge_records(existing: list[ClipRecord], incoming: list[ClipRecord]) -> list[ClipRecord]:
    """Prefer incoming fields when id matches; keep stable order (old then new ids)."""
    by_id = {r.id: r for r in existing}
    order = [r.id for r in existing]
    for row in incoming:
        if row.id in by_id:
            old = by_id[row.id]
            merged = ClipRecord.from_dict({**old.to_json_obj(), **row.to_json_obj()})
            by_id[row.id] = merged
        else:
            by_id[row.id] = row
            order.append(row.id)
    return [by_id[i] for i in order]
