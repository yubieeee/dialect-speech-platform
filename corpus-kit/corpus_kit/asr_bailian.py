"""Bailian Qwen ASR (qwen3-asr-flash) for draft transcripts — not Wenchang-specialized."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "qwen3-asr-flash"
DEFAULT_ENDPOINT = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
)
DEFAULT_KEY_CANDIDATES = (
    Path.home() / "xny" / "private" / "bailian.key",
    Path("/home/apc/xny/private/bailian.key"),
)

MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".webm": "audio/webm",
}


@dataclass
class AsrResult:
    text: str
    model: str
    language: str = ""
    raw: dict | None = None


def resolve_api_key(key_file: Path | None = None, api_key: str = "") -> str:
    if api_key.strip():
        return api_key.strip()
    env = (os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("BAILIAN_API_KEY") or "").strip()
    if env:
        return env
    path = Path(key_file).expanduser() if key_file else None
    if path is None:
        for cand in DEFAULT_KEY_CANDIDATES:
            if cand.is_file():
                path = cand
                break
    if path is None or not path.is_file():
        raise FileNotFoundError(
            "未找到百炼 Key。请设 DASHSCOPE_API_KEY，或 --key-file /home/apc/xny/private/bailian.key"
        )
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"空 Key 文件: {path}")
    return key


def _extract_text(payload: dict) -> str:
    """Best-effort parse of DashScope multimodal ASR response."""
    out = payload.get("output") or {}
    # common: output.choices[0].message.content[{text: ...}]
    choices = out.get("choices") or payload.get("choices") or []
    texts: list[str] = []
    for ch in choices:
        msg = ch.get("message") or {}
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content.strip())
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    t = part.get("text") or part.get("transcript") or ""
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
                elif isinstance(part, str) and part.strip():
                    texts.append(part.strip())
    if texts:
        return "".join(texts).strip()
    # fallback fields
    for key in ("text", "transcript", "result"):
        val = out.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    raise ValueError(f"ASR 响应无文本: {json.dumps(payload, ensure_ascii=False)[:800]}")


def transcribe_file(
    wav_path: Path,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    language: str = "zh",
    enable_itn: bool = False,
    timeout: float = 60.0,
) -> AsrResult:
    path = Path(wav_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    mime = MIME.get(path.suffix.lower(), "audio/wav")
    data_uri = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
    asr_options: dict = {"enable_itn": bool(enable_itn)}
    if language:
        asr_options["language"] = language
    body = {
        "model": model,
        "input": {
            "messages": [
                {"role": "system", "content": [{"text": ""}]},
                {"role": "user", "content": [{"audio": data_uri}]},
            ]
        },
        "parameters": {"asr_options": asr_options},
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"百炼 ASR HTTP {exc.code}: {detail}") from exc
    text = _extract_text(payload)
    return AsrResult(text=text, model=model, language=language, raw=payload)
