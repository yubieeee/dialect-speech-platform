#!/usr/bin/env python3
"""CosyVoice3 local debug lab — inference + train-param export."""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import web

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cosy-lab")

from cosy_engine import ENGINE, SynthRequest
from paths import (
    DIALECT_ASSETS,
    EVALS,
    EVAL_BANK_JSON,
    PREVIEW,
    REFS,
    RUNTIME_REFS,
    UPLOADS,
    WAV16K,
    WENCHANG,
    ensure_lab_dirs,
)
from train_export import default_train_params, export_train_config

STATIC = Path(__file__).resolve().parent / "static"


def _json(data, status: int = 200):
    return web.json_response(data, status=status, dumps=lambda x: json.dumps(x, ensure_ascii=False))


def _list_audio(root: Path, limit: int = 80) -> list[dict]:
    if not root.is_dir():
        return []
    items = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".wav", ".m4a", ".mp3", ".flac"}:
            continue
        if not path.is_file():
            continue
        items.append(
            {
                "path": str(path),
                "name": path.name,
                "rel": str(path.relative_to(root)) if path.is_relative_to(root) else path.name,
                "size": path.stat().st_size,
            }
        )
        if len(items) >= limit:
            break
    return items


def _load_eval_bank() -> list[dict]:
    if not EVAL_BANK_JSON.is_file():
        return []
    try:
        data = json.loads(EVAL_BANK_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id", "")).strip()
        text = str(item.get("text", "")).strip()
        if not sid or not text:
            continue
        out.append(
            {
                "id": sid,
                "text": text,
                "scene": str(item.get("scene", "")).strip(),
            }
        )
    return out


async def api_status(_request: web.Request):
    ensure_lab_dirs()
    st = ENGINE.status()
    st["refs"] = _list_audio(REFS) + _list_audio(RUNTIME_REFS) + _list_audio(WAV16K)
    st["dialect_assets_raw"] = _list_audio(DIALECT_ASSETS)
    st["evals"] = _list_audio(EVALS, limit=40)
    st["wenchang"] = str(WENCHANG)
    st["eval_sentences"] = _load_eval_bank()
    st["train_defaults"] = default_train_params()
    return _json(st)


async def api_load(request: web.Request):
    body = await request.json() if request.can_read_body else {}
    loop = asyncio.get_running_loop()
    try:
        status = await loop.run_in_executor(
            _EXECUTOR,
            lambda: ENGINE.load(
                fp16=bool(body.get("fp16", True)),
                load_trt=bool(body.get("load_trt", False)),
                load_vllm=bool(body.get("load_vllm", False)),
            ),
        )
        return _json({"ok": True, **status})
    except Exception as exc:  # noqa: BLE001
        return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


async def api_synthesize(request: web.Request):
    body = await request.json()
    req = SynthRequest(
        mode=str(body.get("mode", "zero_shot")),
        text=str(body.get("text", "")),
        prompt_text=str(body.get("prompt_text", "")),
        instruct_text=str(body.get("instruct_text", "")),
        prompt_wav=str(body.get("prompt_wav", "")),
        speed=float(body.get("speed", 1.0)),
        stream=bool(body.get("stream", False)),
        text_frontend=bool(body.get("text_frontend", False)),
        seed=int(body.get("seed", 42)),
        auto_prefix_prompt=bool(body.get("auto_prefix_prompt", True)),
        auto_prefix_instruct=bool(body.get("auto_prefix_instruct", True)),
        zero_shot_spk_id=str(body.get("zero_shot_spk_id", "")),
        group=str(body.get("group", "lab")),
        note=str(body.get("note", "")),
        # 调试台默认不落 evals；批量脚本传 persist=true
        persist=bool(body.get("persist", False)),
        fp16=bool(body.get("fp16", True)),
        load_trt=bool(body.get("load_trt", False)),
        load_vllm=bool(body.get("load_vllm", False)),
    )
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(_EXECUTOR, ENGINE.synthesize, req)
        payload = {
            "ok": result.ok,
            "wav_path": result.wav_path,
            "sample_rate": result.sample_rate,
            "duration_sec": result.duration_sec,
            "elapsed_sec": result.elapsed_sec,
            "error": result.error,
            "meta": result.meta,
            "audio_url": f"/media?path={result.wav_path}" if result.ok else "",
        }
        return _json(payload, status=200 if result.ok else 400)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


async def api_save_eval(request: web.Request):
    """把当前预览音频保存进 dialect-assets/wenchang/evals/。"""
    body = await request.json() if request.can_read_body else {}
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _EXECUTOR,
            lambda: ENGINE.persist_preview(
                str(body.get("wav_path", "")),
                group=str(body.get("group", "")),
                mode=str(body.get("mode", "")),
                note=str(body.get("note", "")),
            ),
        )
        payload = {
            "ok": result.ok,
            "wav_path": result.wav_path,
            "error": result.error,
            "meta": result.meta,
            "audio_url": f"/media?path={result.wav_path}" if result.ok and result.wav_path else "",
        }
        return _json(payload, status=200 if result.ok else 400)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


async def api_upload(request: web.Request):
    ensure_lab_dirs()
    reader = await request.multipart()
    field = await reader.next()
    if field is None or field.name != "file":
        return _json({"ok": False, "error": "缺少 file 字段"}, status=400)
    filename = Path(field.filename or "upload.bin").name
    dest = UPLOADS / filename
    with dest.open("wb") as out:
        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            out.write(chunk)
    # optional copy into refs if wav
    copied = ""
    if dest.suffix.lower() == ".wav":
        target = REFS / dest.name
        shutil.copy2(dest, target)
        copied = str(target)
    return _json({"ok": True, "path": str(dest), "ref_copy": copied})


async def api_train_defaults(_request: web.Request):
    return _json({"ok": True, "params": default_train_params()})


async def api_train_export(request: web.Request):
    body = await request.json()
    try:
        result = export_train_config(body.get("params") or body)
        return _json(result)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)


async def api_media(request: web.Request):
    path = Path(request.rel_url.query.get("path", ""))
    allowed_roots = [EVALS, REFS, WAV16K, UPLOADS, PREVIEW, RUNTIME_REFS, DIALECT_ASSETS, WENCHANG]
    try:
        resolved = path.resolve()
    except OSError:
        raise web.HTTPBadRequest(text="bad path") from None
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots if root.exists()):
        raise web.HTTPForbidden(text="path not allowed")
    if not resolved.is_file():
        raise web.HTTPNotFound()
    ctype, _ = mimetypes.guess_type(str(resolved))
    return web.FileResponse(resolved, headers={"Content-Type": ctype or "application/octet-stream"})


async def index(_request: web.Request):
    return web.FileResponse(STATIC / "index.html")


def build_app() -> web.Application:
    ensure_lab_dirs()
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/load", api_load)
    app.router.add_post("/api/synthesize", api_synthesize)
    app.router.add_post("/api/save_eval", api_save_eval)
    app.router.add_post("/api/upload", api_upload)
    app.router.add_get("/api/train/defaults", api_train_defaults)
    app.router.add_post("/api/train/export", api_train_export)
    app.router.add_get("/media", api_media)
    app.router.add_static("/static/", STATIC, show_index=False)
    return app


def main():
    parser = argparse.ArgumentParser(description="CosyVoice3 debug lab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7865)
    args = parser.parse_args()
    web.run_app(build_app(), host=args.host, port=args.port, print=lambda *a: print(*a, flush=True))


if __name__ == "__main__":
    main()
