"""Ingest pipeline steps."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .manifest import load_manifest, merge_records, save_manifest
from .media import sha256_file, transcode_to_wav16k
from .models import ClipRecord
from .paths import ensure_dialect_dirs, manifest_path, reports_dir
from .qc import qc_record
from .sources.base import CollectedItem
from .sources.local_import import LocalImportSource

_SAFE = re.compile(r"[^\w\u4e00-\u9fff.-]+", re.UNICODE)


def _safe_stem(name: str) -> str:
    stem = _SAFE.sub("_", name).strip("._")
    return stem[:120] or "clip"


def _make_id(dialect: str, index: int, stem: str) -> str:
    prefix = dialect[:2] if dialect else "xx"
    return f"{prefix}_{index:04d}_{_safe_stem(stem)[:40]}"


def init_dialect(dialect: str) -> Path:
    root = ensure_dialect_dirs(dialect)
    bib = root / "sources" / "BIBLIOGRAPHY.md"
    if not bib.exists():
        bib.write_text(
            "# 资料台账\n\n| 日期 | 资料 | 类型 | 版权/获取 | 用途 | 本机存放 |\n"
            "|------|------|------|-----------|------|----------|\n",
            encoding="utf-8",
        )
    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# {dialect}\n\n由 corpus-kit 初始化。见仓库 `dialect-assets/README.md`。\n",
            encoding="utf-8",
        )
    return root


def import_items(
    dialect: str,
    items: list[CollectedItem],
    *,
    locale: str = "",
    skip_copy: bool = False,
    id_start: int | None = None,
) -> list[ClipRecord]:
    root = ensure_dialect_dirs(dialect)
    raw_dir = root / "raw"
    existing = load_manifest(manifest_path(dialect))
    next_idx = id_start if id_start is not None else len(existing) + 1
    used = {r.id for r in existing}
    by_sha = {r.sha256: r.id for r in existing if r.sha256}
    records: list[ClipRecord] = []

    for item in items:
        src = item.path.resolve()
        stem = _safe_stem(src.stem)
        src_sha = sha256_file(src)
        if skip_copy:
            try:
                rel = src.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"--skip-copy 要求文件已在 {root}/ 下，收到: {src}") from exc
            raw_rel = str(rel).replace("\\", "/")
            if not raw_rel.startswith("raw/"):
                raise ValueError(f"--skip-copy 仅支持 raw/ 下文件，收到: {raw_rel}")
            dest = root / raw_rel
        else:
            dest = raw_dir / f"{stem}{src.suffix.lower()}"
            if dest.exists() and sha256_file(dest) != src_sha:
                dest = raw_dir / f"{stem}_{next_idx}{src.suffix.lower()}"
            if not dest.exists() or sha256_file(dest) != src_sha:
                shutil.copy2(src, dest)
            raw_rel = f"raw/{dest.name}"

        if src_sha in by_sha:
            cid = by_sha[src_sha]
        else:
            while True:
                cid = _make_id(dialect, next_idx, stem)
                next_idx += 1
                if cid not in used:
                    used.add(cid)
                    break
            by_sha[src_sha] = cid

        text = (item.text_zh or item.prompt_text or "").strip()
        records.append(
            ClipRecord(
                id=cid,
                text_zh=text,
                prompt_text=(item.prompt_text or text).strip(),
                prompt_text_status="待校" if text else "待填",
                raw=raw_rel,
                role=item.role,
                speaker=item.speaker,
                locale=locale,
                dialect=dialect,
                source="local",
                source_url=item.source_url,
                license_note=item.license_note or "local_upload",
                sha256=src_sha,
                extra=item.extra,
            )
        )
    merged = merge_records(existing, records)
    save_manifest(manifest_path(dialect), merged)
    return records


def transcode_dialect(dialect: str, *, only_ids: set[str] | None = None) -> list[ClipRecord]:
    root = ensure_dialect_dirs(dialect)
    rows = load_manifest(manifest_path(dialect))
    if not rows:
        raise ValueError(f"manifest 为空: {manifest_path(dialect)}")
    updated: list[ClipRecord] = []
    for row in rows:
        if only_ids is not None and row.id not in only_ids:
            updated.append(row)
            continue
        if not row.raw:
            updated.append(row)
            continue
        src = root / row.raw
        if not src.is_file():
            row.qc_status = "fail"
            row.qc_notes = [f"raw 缺失: {row.raw}"]
            updated.append(row)
            continue
        wav_name = Path(row.raw).stem + ".wav"
        wav_rel = f"wav16k/{wav_name}"
        dst = root / wav_rel
        stats = transcode_to_wav16k(src, dst)
        row.wav = wav_rel
        row.duration_sec = stats.get("duration_sec")
        row.sample_rate = stats.get("sample_rate")
        row.channels = stats.get("channels")
        row.sha256 = stats.get("sha256") or row.sha256
        updated.append(row)
    save_manifest(manifest_path(dialect), updated)
    return updated


def qc_dialect(dialect: str) -> dict:
    root = ensure_dialect_dirs(dialect)
    rows = load_manifest(manifest_path(dialect))
    checked = [qc_record(root, r) for r in rows]
    save_manifest(manifest_path(dialect), checked)
    summary = {
        "dialect": dialect,
        "total": len(checked),
        "pass": sum(1 for r in checked if r.qc_status == "pass"),
        "warn": sum(1 for r in checked if r.qc_status == "warn"),
        "fail": sum(1 for r in checked if r.qc_status == "fail"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "items": [
            {
                "id": r.id,
                "qc_status": r.qc_status,
                "qc_notes": r.qc_notes,
                "duration_sec": r.duration_sec,
                "wav": r.wav,
            }
            for r in checked
        ],
    }
    out = reports_dir(dialect) / f"qc_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["report_path"] = str(out)
    return summary


def ingest_local(
    dialect: str,
    input_path: Path,
    *,
    locale: str = "",
    speaker: str = "",
    text_from_filename: bool = False,
    skip_copy: bool = False,
    recursive: bool = True,
) -> dict:
    init_dialect(dialect)
    source = LocalImportSource(
        input_path,
        text_from_filename=text_from_filename,
        speaker=speaker,
        recursive=recursive,
    )
    items = source.collect()
    imported = import_items(dialect, items, locale=locale, skip_copy=skip_copy)
    ids = {r.id for r in imported}
    transcode_dialect(dialect, only_ids=ids)
    report = qc_dialect(dialect)
    report["imported"] = len(imported)
    report["imported_ids"] = sorted(ids)
    return report


def mine_media(
    dialect: str,
    input_path: Path | None = None,
    *,
    locale: str = "",
    speaker: str = "",
    license_note: str = "local_media_drop",
    split_mode: str = "auto",
    use_subtitles: bool = True,
    prefer_lang: str = "zh",
    ocr_hardsubs: bool = False,
    ocr_interval: float = 0.35,
    ocr_band: tuple[float, float] = (0.68, 0.95),
    ocr_region: tuple[float, float, float, float] | None = None,
    ocr_min_score: float = 0.5,
    require_text: bool = False,
    noise_db: float = -35.0,
    min_silence: float = 0.5,
    min_sec: float = 1.5,
    max_sec: float = 20.0,
    keep_original: bool = True,
    recursive: bool = True,
) -> dict:
    """
    从本机视频/音频「投放目录」抽音轨，优先用字幕做音文对齐切句，再入库。

    字幕来源：同名 .srt/.vtt/.ass、内嵌轨；可选 --ocr-hardsubs 硬字幕 OCR（录屏）。
    默认读 dialect-assets/<dialect>/inbox/；也可 --input 指定任意本机目录。
    """
    from .extract import list_media_files, mine_file_to_clips
    from .paths import MEDIA_INBOX

    root = init_dialect(dialect)
    inbox = root / MEDIA_INBOX
    src_root = Path(input_path).expanduser().resolve() if input_path else inbox.resolve()
    if not src_root.exists():
        raise FileNotFoundError(
            f"投放目录不存在: {src_root}\n"
            f"请把视频/音频（及同名字幕）放进 {inbox} 后重试，或用 --input 指定路径"
        )

    media_files = list_media_files(src_root, recursive=recursive)
    private = root / "sources" / "private_files"
    work_root = root / "sources" / "mine_work"
    work_root.mkdir(parents=True, exist_ok=True)

    items: list[CollectedItem] = []
    mined_clips = 0
    with_text = 0
    media_metas: list[dict] = []
    for media in media_files:
        if keep_original:
            dest_orig = private / media.name
            if not dest_orig.exists() or sha256_file(dest_orig) != sha256_file(media):
                if dest_orig.exists() and sha256_file(dest_orig) != sha256_file(media):
                    dest_orig = private / f"{media.stem}_{sha256_file(media)[:8]}{media.suffix.lower()}"
                shutil.copy2(media, dest_orig)
            # also keep sidecar subtitle next to private copy
            from .subtitles import find_sidecar_subtitle

            side = find_sidecar_subtitle(media)
            if side is not None:
                side_dest = private / side.name
                if not side_dest.exists():
                    shutil.copy2(side, side_dest)

        clip_dir = work_root / _safe_stem(media.stem)
        clips, meta = mine_file_to_clips(
            media,
            clip_dir,
            split_mode=split_mode,
            use_subtitles=use_subtitles,
            prefer_lang=prefer_lang,
            ocr_hardsubs=ocr_hardsubs,
            ocr_interval=ocr_interval,
            ocr_band=ocr_band,
            ocr_region=ocr_region,
            ocr_min_score=ocr_min_score,
            noise_db=noise_db,
            min_silence=min_silence,
            min_sec=min_sec,
            max_sec=max_sec,
            require_text=require_text,
        )
        media_metas.append(meta)
        mined_clips += len(clips)
        for clip in clips:
            text = (clip.text or "").strip()
            if text:
                with_text += 1
            items.append(
                CollectedItem(
                    path=clip.path,
                    text_zh=text,
                    prompt_text=text,
                    speaker=speaker,
                    license_note=license_note,
                    extra={
                        "origin_media": media.name,
                        "origin_path": str(media),
                        "mine": "local_media",
                        "t_start": clip.start,
                        "t_end": clip.end,
                        "text_source": clip.text_source,
                        "cue_source": meta.get("cue_source") or "",
                    },
                )
            )

    if not items:
        raise ValueError(
            "未能从媒资切出有效片段（可调 --min-sec / --split / 检查是否有字幕）"
        )

    imported = import_items(dialect, items, locale=locale, skip_copy=False)
    ids = {r.id for r in imported}
    rows = load_manifest(manifest_path(dialect))
    for r in rows:
        if r.id not in ids:
            continue
        r.source = "local_media"
        if r.text_zh.strip() and r.prompt_text.strip():
            # 来自字幕，仍建议人工抽检方言用字
            if r.prompt_text_status in ("", "待填"):
                r.prompt_text_status = "待校"
        else:
            r.prompt_text_status = "待填"
        if not r.license_note:
            r.license_note = license_note
    save_manifest(manifest_path(dialect), rows)
    transcode_dialect(dialect, only_ids=ids)
    report = qc_dialect(dialect)
    # 语料清单只保留 TTS 字段，不落信源/路径 provenance
    save_manifest(manifest_path(dialect), load_manifest(manifest_path(dialect)), tts_only=True)
    report["media_files"] = len(media_files)
    report["mined_clips"] = mined_clips
    report["with_text"] = with_text
    report["without_text"] = mined_clips - with_text
    report["imported"] = len(imported)
    report["imported_ids"] = sorted(ids)
    report["inbox"] = str(src_root)
    report["media_meta"] = media_metas
    return report


def asr_fill(
    dialect: str,
    *,
    key_file: Path | None = None,
    api_key: str = "",
    model: str = "qwen3-asr-flash",
    language: str = "zh",
    only_empty: bool = True,
    force: bool = False,
    ids: set[str] | None = None,
    limit: int = 0,
    enable_itn: bool = False,
) -> dict:
    """
    用百炼 qwen3-asr-flash 给 manifest 片段填草稿文本。
    文昌话无专用 ASR：结果一律 prompt_text_status=待校，仅作初稿。
    """
    from .asr_bailian import resolve_api_key, transcribe_file

    root = ensure_dialect_dirs(dialect)
    key = resolve_api_key(key_file, api_key)
    rows = load_manifest(manifest_path(dialect))
    if not rows:
        raise ValueError(f"manifest 为空: {manifest_path(dialect)}")

    targets: list[ClipRecord] = []
    for r in rows:
        if ids is not None and r.id not in ids:
            continue
        if not r.wav or not (root / r.wav).is_file():
            continue
        has_text = bool((r.text_zh or "").strip())
        # 默认不覆盖已有「待校/已定」文本；待填或空文本才跑 ASR
        if not force:
            if has_text and r.prompt_text_status not in ("待填", ""):
                continue
            if only_empty and has_text and r.prompt_text_status != "待填":
                continue
        targets.append(r)

    if limit and limit > 0:
        targets = targets[:limit]

    filled = 0
    failed: list[dict] = []
    samples: list[dict] = []
    by_id = {r.id: r for r in rows}
    for r in targets:
        try:
            result = transcribe_file(
                root / r.wav,
                api_key=key,
                model=model,
                language=language,
                enable_itn=enable_itn,
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"id": r.id, "error": str(exc)[:300]})
            continue
        text = (result.text or "").strip()
        if not text:
            failed.append({"id": r.id, "error": "empty_transcript"})
            continue
        cur = by_id[r.id]
        cur.text_zh = text
        cur.prompt_text = text
        cur.prompt_text_status = "待校"
        cur.extra = {
            **(cur.extra or {}),
            "asr_model": result.model,
            "asr_language": language,
            "text_source": "bailian_qwen_asr",
        }
        filled += 1
        if len(samples) < 5:
            samples.append({"id": r.id, "text": text, "wav": r.wav})

    save_manifest(manifest_path(dialect), list(by_id.values()))
    return {
        "dialect": dialect,
        "candidates": len(targets),
        "filled": filled,
        "failed": len(failed),
        "failures": failed[:20],
        "samples": samples,
        "model": model,
        "note": "千问 ASR 非文昌专用；结果均为待校草稿",
    }


def crawl_and_mine(
    dialect: str,
    *,
    urls: list[str],
    license_note: str,
    i_have_rights: bool = False,
    locale: str = "",
    speaker: str = "",
    sub_langs: str = "zh.*,zh-Hans,zh-CN,zh,en.*,en",
    cookies_from_browser: str = "",
    max_downloads: int = 50,
    write_auto_subs: bool = True,
    split_mode: str = "auto",
    use_subtitles: bool = True,
    prefer_lang: str = "zh",
    require_text: bool = True,
    min_sec: float = 1.5,
    max_sec: float = 20.0,
) -> dict:
    """
    网络 URL → yt-dlp 拉媒体+字幕 → mine 入库。
    必须 --i-have-rights + 有效 license_note；不负责破解/绕过付费墙。
    """
    from .sources.crawl import CrawlSource, assert_crawl_rights

    assert_crawl_rights(i_have_rights=i_have_rights, license_note=license_note)
    root = init_dialect(dialect)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = root / "sources" / "crawl_dl" / run_id
    src = CrawlSource(
        urls,
        out_dir,
        license_note=license_note,
        i_have_rights=i_have_rights,
        sub_langs=sub_langs,
        cookies_from_browser=cookies_from_browser,
        max_downloads=max_downloads,
        write_auto_subs=write_auto_subs,
    )
    collected = src.collect()
    if not collected:
        raise RuntimeError("下载结果为空")

    # 台账
    bib = root / "sources" / "BIBLIOGRAPHY.md"
    lines = []
    for d in src.downloads:
        has_sub = "是" if d.subtitle_paths else "否"
        lines.append(
            f"| {datetime.now().date()} | {d.title or d.media_path.name} | crawl |"
            f" {license_note} | 语料 | `{d.media_path.relative_to(root)}` / 字幕:{has_sub} / {d.source_url} |"
        )
    if lines:
        with bib.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    url_by_name = {d.media_path.name: d.source_url for d in src.downloads}
    report = mine_media(
        dialect,
        out_dir,
        locale=locale,
        speaker=speaker,
        license_note=license_note,
        split_mode=split_mode,
        use_subtitles=use_subtitles,
        prefer_lang=prefer_lang,
        require_text=require_text,
        min_sec=min_sec,
        max_sec=max_sec,
        keep_original=True,
        recursive=True,
    )

    # 回写 source / source_url
    rows = load_manifest(manifest_path(dialect))
    ids = set(report.get("imported_ids") or [])
    for r in rows:
        if r.id not in ids:
            continue
        r.source = "crawl"
        origin = (r.extra or {}).get("origin_media") or ""
        if origin in url_by_name:
            r.source_url = url_by_name[origin]
            r.extra = {**(r.extra or {}), "crawl_run": run_id}
    save_manifest(manifest_path(dialect), rows)

    report["crawl_dir"] = str(out_dir)
    report["downloaded"] = len(src.downloads)
    report["download_urls"] = [d.source_url for d in src.downloads]
    report["downloads_with_subs"] = sum(1 for d in src.downloads if d.subtitle_paths)
    return report
