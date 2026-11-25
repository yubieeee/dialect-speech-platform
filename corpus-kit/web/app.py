#!/usr/bin/env python3
"""corpus-kit 入库台：把 CLI 能力暴露成可复用本地 Web UI。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT.parent
sys.path.insert(0, str(ROOT))

from corpus_kit import __version__  # noqa: E402
from corpus_kit.manifest import load_manifest  # noqa: E402
from corpus_kit.paths import (  # noqa: E402
    AUDIO_SUFFIXES,
    DIALECT_ASSETS,
    MEDIA_INBOX,
    VIDEO_SUFFIXES,
    dialect_root,
    ensure_dialect_dirs,
    manifest_path,
)
from corpus_kit.pipeline import (  # noqa: E402
    crawl_and_mine,
    ingest_local,
    init_dialect,
    mine_media,
    qc_dialect,
    transcode_dialect,
)

STATIC = Path(__file__).resolve().parent / "static"
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="corpus-kit-web")
_JOBS: dict[str, dict] = {}


def _json(data, status: int = 200):
    return web.json_response(data, status=status, dumps=lambda x: json.dumps(x, ensure_ascii=False))


def _list_dialects() -> list[str]:
    if not DIALECT_ASSETS.is_dir():
        return []
    out = []
    for p in sorted(DIALECT_ASSETS.iterdir()):
        if not p.is_dir() or p.name.startswith(".") or p.name in {"kitdemo"}:
            continue
        if any(
            (p / name).exists()
            for name in ("manifest.jsonl", MEDIA_INBOX, "wav16k", "raw", "sentences", "video", "image")
        ):
            out.append(p.name)
    return out


def _media_listing(dialect: str, kind: str, limit: int = 80) -> list[dict]:
    root = dialect_root(dialect)
    folder = {
        "inbox": root / MEDIA_INBOX,
        "video": root / "video",
        "image": root / "image",
        "wav16k": root / "wav16k",
        "raw": root / "raw",
    }.get(kind)
    if not folder or not folder.is_dir():
        return []
    suffixes = AUDIO_SUFFIXES | VIDEO_SUFFIXES | {".srt", ".vtt", ".ass", ".png", ".jpg", ".jpeg", ".webp"}
    items = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.name.startswith("."):
            continue
        rel = str(path.relative_to(root))
        items.append(
            {
                "name": path.name,
                "rel": rel,
                "path": str(path),
                "size": path.stat().st_size,
                "suffix": path.suffix.lower(),
            }
        )
        if len(items) >= limit:
            break
    return items


def _manifest_summary(dialect: str) -> dict:
    path = manifest_path(dialect)
    if not path.is_file():
        return {"count": 0, "speakers": {}, "with_text": 0, "path": str(path)}
    rows = load_manifest(path)
    speakers: dict[str, int] = {}
    with_text = 0
    for r in rows:
        sp = r.speaker or "(none)"
        speakers[sp] = speakers.get(sp, 0) + 1
        if (r.text_zh or r.prompt_text or "").strip():
            with_text += 1
    return {
        "count": len(rows),
        "with_text": with_text,
        "speakers": speakers,
        "path": str(path),
    }


def _parse_band(raw: str | None) -> tuple[float, float]:
    if not raw:
        return (0.68, 0.95)
    parts = [p.strip() for p in str(raw).split(",")]
    if len(parts) != 2:
        raise ValueError("ocr_band 格式: y0,y1")
    y0, y1 = float(parts[0]), float(parts[1])
    if not (0.0 <= y0 < y1 <= 1.0):
        raise ValueError("ocr_band 须满足 0<=y0<y1<=1")
    return y0, y1


def _parse_region(raw: str | None):
    if not raw:
        return None
    parts = [p.strip() for p in str(raw).split(",")]
    if len(parts) != 4:
        raise ValueError("ocr_region 格式: x0,y0,x1,y1")
    x0, y0, x1, y1 = (float(p) for p in parts)
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise ValueError("ocr_region 坐标非法")
    return (x0, y0, x1, y1)


def _new_job(kind: str, payload: dict) -> str:
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    _JOBS[job_id] = {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "payload": payload,
        "result": None,
        "error": None,
    }
    return job_id


def _set_job(job_id: str, **kwargs) -> None:
    job = _JOBS.get(job_id)
    if not job:
        return
    job.update(kwargs)


async def _run_job(job_id: str, fn, *args, **kwargs):
    _set_job(job_id, status="running", started_at=datetime.now().isoformat(timespec="seconds"))
    loop = asyncio.get_running_loop()

    def _call():
        return fn(*args, **kwargs)

    try:
        result = await loop.run_in_executor(_EXECUTOR, _call)
        _set_job(
            job_id,
            status="ok",
            result=result,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )
    except Exception as exc:  # noqa: BLE001
        _set_job(
            job_id,
            status="error",
            error=str(exc),
            traceback=traceback.format_exc(),
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


async def api_status(_request: web.Request):
    dialects = _list_dialects()
    return _json(
        {
            "ok": True,
            "version": __version__,
            "dialect_assets": str(DIALECT_ASSETS),
            "dialects": dialects,
            "jobs_running": sum(1 for j in _JOBS.values() if j["status"] in {"queued", "running"}),
        }
    )


async def api_dialect(request: web.Request):
    dialect = request.match_info["dialect"]
    root = dialect_root(dialect)
    exists = root.is_dir()
    summary = _manifest_summary(dialect) if exists else {"count": 0, "with_text": 0, "speakers": {}}
    return _json(
        {
            "ok": True,
            "dialect": dialect,
            "exists": exists,
            "root": str(root),
            "manifest": summary,
            "media": {
                "inbox": _media_listing(dialect, "inbox") if exists else [],
                "video": _media_listing(dialect, "video") if exists else [],
                "image": _media_listing(dialect, "image", limit=40) if exists else [],
                "wav16k": _media_listing(dialect, "wav16k", limit=40) if exists else [],
            },
        }
    )


async def api_manifest(request: web.Request):
    dialect = request.rel_url.query.get("dialect", "").strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)
    limit = int(request.rel_url.query.get("limit", "80"))
    path = manifest_path(dialect)
    if not path.is_file():
        return _json({"ok": True, "items": [], "total": 0, "path": str(path)})
    rows = load_manifest(path)
    items = []
    for r in rows[: max(1, min(limit, 500))]:
        obj = r.to_tts_obj() if hasattr(r, "to_tts_obj") else r.to_json_obj()
        items.append(obj)
    return _json({"ok": True, "items": items, "total": len(rows), "path": str(path)})


async def api_init(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)
    try:
        root = init_dialect(dialect)
    except Exception as exc:  # noqa: BLE001
        return _json({"ok": False, "error": str(exc)}, 400)
    return _json({"ok": True, "root": str(root), "inbox": str(root / MEDIA_INBOX)})


async def api_job(request: web.Request):
    job = _JOBS.get(request.match_info["job_id"])
    if not job:
        return _json({"ok": False, "error": "job 不存在"}, 404)
    return _json({"ok": True, "job": job})


async def api_jobs(_request: web.Request):
    items = sorted(_JOBS.values(), key=lambda j: j["created_at"], reverse=True)[:40]
    return _json({"ok": True, "items": items})


async def api_mine(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)
    ensure_dialect_dirs(dialect)
    input_path = body.get("input") or None
    if input_path:
        input_path = Path(str(input_path)).expanduser()

    def _do():
        report = mine_media(
            dialect,
            input_path,
            locale=str(body.get("locale", "")),
            speaker=str(body.get("speaker", "")),
            license_note=str(body.get("license_note", "local_media_drop")),
            split_mode=str(body.get("split", "auto")),
            use_subtitles=not bool(body.get("no_subs", False)),
            prefer_lang=str(body.get("prefer_lang", "zh")),
            ocr_hardsubs=bool(body.get("ocr_hardsubs", False)),
            ocr_interval=float(body.get("ocr_interval", 0.35)),
            ocr_band=_parse_band(body.get("ocr_band")),
            ocr_region=_parse_region(body.get("ocr_region")),
            ocr_min_score=float(body.get("ocr_min_score", 0.5)),
            require_text=bool(body.get("require_text", False)),
            noise_db=float(body.get("noise_db", -35.0)),
            min_silence=float(body.get("min_silence", 0.5)),
            min_sec=float(body.get("min_sec", 1.5)),
            max_sec=float(body.get("max_sec", 20.0)),
            keep_original=not bool(body.get("no_keep_original", False)),
            recursive=not bool(body.get("no_recursive", False)),
        )
        keys = (
            "inbox",
            "media_files",
            "mined_clips",
            "with_text",
            "without_text",
            "imported",
            "total",
            "pass",
            "warn",
            "fail",
            "report_path",
        )
        return {k: report[k] for k in keys if k in report}

    job_id = _new_job("mine", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_ocr(request: web.Request):
    body = await request.json()
    inp = Path(str(body.get("input", ""))).expanduser()
    if not str(body.get("input", "")).strip():
        return _json({"ok": False, "error": "缺少 input"}, 400)

    def _do():
        from corpus_kit.hardsubs import ocr_hardsubs_to_srt

        inp_r = inp.resolve()
        files: list[Path]
        if inp_r.is_file():
            files = [inp_r]
        elif inp_r.is_dir():
            files = sorted(
                p for p in inp_r.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
            )
        else:
            raise FileNotFoundError(f"未找到: {inp_r}")
        if not files:
            raise FileNotFoundError(f"未找到视频: {inp_r}")
        results = []
        for vid in files:
            cues, srt = ocr_hardsubs_to_srt(
                vid,
                vid.with_suffix(".srt"),
                interval=float(body.get("ocr_interval", 0.35)),
                band=_parse_band(body.get("ocr_band")),
                region=_parse_region(body.get("ocr_region")),
                min_score=float(body.get("ocr_min_score", 0.5)),
            )
            results.append({"video": str(vid), "srt": str(srt), "cues": len(cues)})
        return {"items": results, "videos": len(results)}

    job_id = _new_job("ocr-subs", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_crawl(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)
    if not bool(body.get("i_have_rights", False)):
        return _json({"ok": False, "error": "必须勾选 i_have_rights（确认可合法使用）"}, 400)
    license_note = str(body.get("license_note", "")).strip()
    if not license_note or license_note.upper() == "TODO":
        return _json({"ok": False, "error": "license_note 必填且不能是 TODO"}, 400)

    urls_raw = str(body.get("urls", "")).strip()
    urls = [u.strip() for u in urls_raw.splitlines() if u.strip() and not u.strip().startswith("#")]
    single = str(body.get("url", "")).strip()
    if single:
        urls.insert(0, single)
    if not urls:
        return _json({"ok": False, "error": "请提供至少一个 URL"}, 400)

    def _do():
        report = crawl_and_mine(
            dialect,
            urls=urls,
            license_note=license_note,
            i_have_rights=True,
            locale=str(body.get("locale", "")),
            speaker=str(body.get("speaker", "")),
            sub_langs=str(body.get("sub_langs", "zh.*,zh-Hans,zh-CN,zh,en.*,en")),
            cookies_from_browser=str(body.get("cookies_from_browser", "")),
            max_downloads=int(body.get("max_downloads", 50)),
            write_auto_subs=not bool(body.get("no_auto_subs", False)),
            split_mode=str(body.get("split", "auto")),
            use_subtitles=not bool(body.get("no_subs", False)),
            prefer_lang=str(body.get("prefer_lang", "zh")),
            require_text=not bool(body.get("allow_empty_text", False)),
            min_sec=float(body.get("min_sec", 1.5)),
            max_sec=float(body.get("max_sec", 20.0)),
        )
        keys = (
            "crawl_dir",
            "downloaded",
            "downloads_with_subs",
            "download_urls",
            "mined_clips",
            "with_text",
            "without_text",
            "imported",
            "total",
            "pass",
            "warn",
            "fail",
            "report_path",
        )
        return {k: report[k] for k in keys if k in report}

    job_id = _new_job("crawl", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_ingest(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    input_path = str(body.get("input", "")).strip()
    if not dialect or not input_path:
        return _json({"ok": False, "error": "需要 dialect 与 input"}, 400)

    def _do():
        report = ingest_local(
            dialect,
            Path(input_path).expanduser(),
            locale=str(body.get("locale", "")),
            speaker=str(body.get("speaker", "")),
            text_from_filename=bool(body.get("text_from_filename", False)),
            skip_copy=bool(body.get("skip_copy", False)),
            recursive=not bool(body.get("no_recursive", False)),
        )
        return {
            k: report[k]
            for k in ("imported", "total", "pass", "warn", "fail", "report_path")
            if k in report
        }

    job_id = _new_job("ingest", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_qc(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)

    def _do():
        return qc_dialect(dialect)

    job_id = _new_job("qc", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_slim(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)

    def _do():
        from corpus_kit.manifest import save_manifest

        rows = load_manifest(manifest_path(dialect))
        save_manifest(manifest_path(dialect), rows, tts_only=True)
        return {"slimmed": len(rows), "path": str(manifest_path(dialect))}

    job_id = _new_job("slim", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_transcode(request: web.Request):
    body = await request.json()
    dialect = str(body.get("dialect", "")).strip()
    if not dialect:
        return _json({"ok": False, "error": "缺少 dialect"}, 400)

    def _do():
        rows = transcode_dialect(dialect)
        return {"transcoded": len(rows), "wav16k": str(dialect_root(dialect) / "wav16k")}

    job_id = _new_job("transcode", body)
    asyncio.create_task(_run_job(job_id, _do))
    return _json({"ok": True, "job_id": job_id})


async def api_upload(request: web.Request):
    """上传文件到 dialect inbox/ 或 video/。"""
    reader = await request.multipart()
    dialect = ""
    dest_kind = "inbox"
    saved = []
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "dialect":
            dialect = (await part.text()).strip()
            continue
        if part.name == "dest":
            dest_kind = (await part.text()).strip() or "inbox"
            continue
        if part.name == "file":
            if not dialect:
                return _json({"ok": False, "error": "请先选 dialect"}, 400)
            root = ensure_dialect_dirs(dialect)
            folder = root / ("video" if dest_kind == "video" else MEDIA_INBOX)
            folder.mkdir(parents=True, exist_ok=True)
            filename = Path(part.filename or "upload.bin").name
            out = folder / filename
            with out.open("wb") as f:
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            saved.append({"name": filename, "path": str(out), "rel": str(out.relative_to(root))})
    if not saved:
        return _json({"ok": False, "error": "未收到文件"}, 400)
    return _json({"ok": True, "saved": saved})


async def index(_request: web.Request):
    return web.FileResponse(STATIC / "index.html")


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024**3)
    app.router.add_get("/", index)
    app.router.add_static("/static/", STATIC)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/dialect/{dialect}", api_dialect)
    app.router.add_get("/api/manifest", api_manifest)
    app.router.add_get("/api/jobs", api_jobs)
    app.router.add_get("/api/jobs/{job_id}", api_job)
    app.router.add_post("/api/init", api_init)
    app.router.add_post("/api/mine", api_mine)
    app.router.add_post("/api/ocr", api_ocr)
    app.router.add_post("/api/crawl", api_crawl)
    app.router.add_post("/api/ingest", api_ingest)
    app.router.add_post("/api/qc", api_qc)
    app.router.add_post("/api/slim", api_slim)
    app.router.add_post("/api/transcode", api_transcode)
    app.router.add_post("/api/upload", api_upload)
    return app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="corpus-kit 入库台")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7870)
    args = p.parse_args(argv)
    DIALECT_ASSETS.mkdir(parents=True, exist_ok=True)
    print(f"corpus-kit web {__version__}")
    print(f"dialect-assets: {DIALECT_ASSETS}")
    print(f"open http://{args.host}:{args.port}")
    web.run_app(create_app(), host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
