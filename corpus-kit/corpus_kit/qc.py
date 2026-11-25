"""Clip quality checks for TTS / ASR ingest."""

from __future__ import annotations

from pathlib import Path

from .media import audio_stats
from .models import ClipRecord

# Cosy reference guidance in project: roughly 3–20s mono
REF_MIN_SEC = 3.0
REF_MAX_SEC = 20.0
ABS_MAX_SEC = 120.0
TARGET_SR = 16000


def qc_wav(path: Path, *, role: str = "") -> tuple[str, list[str], dict]:
    notes: list[str] = []
    stats = audio_stats(path)
    dur = float(stats.get("duration_sec") or 0)
    sr = stats.get("sample_rate")
    ch = stats.get("channels")

    if sr != TARGET_SR:
        notes.append(f"采样率={sr}（期望 {TARGET_SR}）")
    if ch != 1:
        notes.append(f"声道={ch}（期望 mono）")
    if dur <= 0.2:
        notes.append("时长过短")
    if dur > ABS_MAX_SEC:
        notes.append(f"时长 {dur}s 超过 {ABS_MAX_SEC}s")

    if role == "ref" or path.name.startswith("wc_primary") or "refs/" in str(path):
        if dur < REF_MIN_SEC:
            notes.append(f"参考音建议 ≥{REF_MIN_SEC}s，当前 {dur}s")
        if dur > REF_MAX_SEC:
            notes.append(f"参考音建议 ≤{REF_MAX_SEC}s，当前 {dur}s")

    if notes:
        # hard fail only for clearly broken media
        hard = any(x.startswith("时长过短") or "超过" in x and "120" in x for x in notes)
        status = "fail" if hard else "warn"
    else:
        status = "pass"
    return status, notes, stats


def qc_record(dialect_root: Path, record: ClipRecord) -> ClipRecord:
    if not record.wav:
        record.qc_status = "fail"
        record.qc_notes = ["缺少 wav 字段"]
        return record
    path = dialect_root / record.wav
    if not path.is_file():
        record.qc_status = "fail"
        record.qc_notes = [f"找不到 wav: {record.wav}"]
        return record
    status, notes, stats = qc_wav(path, role=record.role)
    record.qc_status = status
    record.qc_notes = notes
    record.duration_sec = stats.get("duration_sec")
    record.sample_rate = stats.get("sample_rate")
    record.channels = stats.get("channels")
    return record
