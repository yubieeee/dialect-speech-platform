"""Lazy CosyVoice3 runner for the debug lab (bypasses SPI presets)."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import (
    DEFAULT_COSY_SOURCE,
    DEFAULT_MODEL_DIR,
    EVALS,
    PREVIEW,
    env_path,
    ensure_lab_dirs,
)

ASSISTANT_PREFIX = "You are a helpful assistant.<|endofprompt|>"

INSTRUCT_PRESETS = [
    "You are a helpful assistant. 请用海南文昌话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用海南话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用闽南话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用上海话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用广东话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用四川话表达。<|endofprompt|>",
    "You are a helpful assistant. 请用尽可能慢地语速说一句话。<|endofprompt|>",
    "You are a helpful assistant. 请用尽可能快地语速说一句话。<|endofprompt|>",
    "You are a helpful assistant. 请非常开心地说一句话。<|endofprompt|>",
]


@dataclass
class SynthRequest:
    mode: str = "zero_shot"  # zero_shot | instruct2 | cross_lingual
    text: str = ""
    prompt_text: str = ""
    instruct_text: str = ""
    prompt_wav: str = ""
    speed: float = 1.0
    stream: bool = False
    text_frontend: bool = False
    seed: int = 42
    auto_prefix_prompt: bool = True
    auto_prefix_instruct: bool = True
    zero_shot_spk_id: str = ""
    group: str = "lab"
    note: str = ""
    # False：只写 lab 预览，不落 evals；True：直接写入 dialect-assets/.../evals/
    persist: bool = False
    # load-time knobs (applied only when model not yet loaded)
    fp16: bool = True
    load_trt: bool = False
    load_vllm: bool = False


@dataclass
class SynthResult:
    ok: bool
    wav_path: str = ""
    sample_rate: int = 24000
    duration_sec: float = 0.0
    elapsed_sec: float = 0.0
    error: str = ""
    meta: dict[str, Any] | None = None


class CosyEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._model = None
        self._sample_rate = 24000
        self._loaded_opts: dict[str, Any] = {}
        self.model_dir = env_path("COSY_MODEL_DIR", DEFAULT_MODEL_DIR)
        self.source = env_path("COSY_SOURCE", DEFAULT_COSY_SOURCE)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def status(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "model_dir": str(self.model_dir),
            "source": str(self.source),
            "sample_rate": self._sample_rate,
            "loaded_opts": self._loaded_opts,
            "instruct_presets": INSTRUCT_PRESETS,
            "assistant_prefix": ASSISTANT_PREFIX,
        }

    def load(self, *, fp16: bool = True, load_trt: bool = False, load_vllm: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._model is not None:
                return self.status()
            if not self.model_dir.is_dir():
                raise FileNotFoundError(f"模型目录不存在: {self.model_dir}")
            if not self.source.is_dir():
                raise FileNotFoundError(f"Cosy 源码不存在: {self.source}")
            sys.path.insert(0, str(self.source))
            sys.path.insert(0, str(self.source / "third_party" / "Matcha-TTS"))
            from cosyvoice.cli.cosyvoice import CosyVoice3

            t0 = time.perf_counter()
            self._model = CosyVoice3(
                str(self.model_dir),
                load_trt=load_trt,
                load_vllm=load_vllm,
                fp16=fp16,
            )
            self._sample_rate = int(self._model.sample_rate)
            self._loaded_opts = {
                "fp16": fp16,
                "load_trt": load_trt,
                "load_vllm": load_vllm,
                "load_sec": round(time.perf_counter() - t0, 2),
            }
            return self.status()

    def synthesize(self, req: SynthRequest) -> SynthResult:
        ensure_lab_dirs()
        text = (req.text or "").strip()
        if not text:
            return SynthResult(ok=False, error="合成文本不能为空")
        if len(text) > 2000:
            return SynthResult(ok=False, error="合成文本过长（≤2000）")
        if req.mode not in {"zero_shot", "instruct2", "cross_lingual"}:
            return SynthResult(ok=False, error=f"不支持的模式: {req.mode}")
        if not 0.5 <= float(req.speed) <= 2.0:
            return SynthResult(ok=False, error="speed 须在 0.5～2.0")
        if req.mode in {"zero_shot", "instruct2", "cross_lingual"} and not req.prompt_wav:
            return SynthResult(ok=False, error="需要参考音频 prompt_wav")
        prompt_wav = Path(req.prompt_wav)
        if not prompt_wav.is_file():
            return SynthResult(ok=False, error=f"参考音频不存在: {prompt_wav}")

        prompt_text = (req.prompt_text or "").strip()
        instruct_text = (req.instruct_text or "").strip()
        if req.mode == "zero_shot":
            if not prompt_text:
                return SynthResult(ok=False, error="zero_shot 需要 prompt_text（与参考音内容对齐）")
            if req.auto_prefix_prompt and ASSISTANT_PREFIX not in prompt_text:
                prompt_text = ASSISTANT_PREFIX + prompt_text
        if req.mode == "instruct2":
            if not instruct_text:
                return SynthResult(ok=False, error="instruct2 需要 instruct_text")
            if req.auto_prefix_instruct and "<|endofprompt|>" not in instruct_text:
                instruct_text = f"You are a helpful assistant. {instruct_text}<|endofprompt|>"

        with self._lock:
            if self._model is None:
                self.load(fp16=req.fp16, load_trt=req.load_trt, load_vllm=req.load_vllm)
            model = self._model
            assert model is not None

            import numpy as np
            import torch
            from cosyvoice.utils.common import set_all_random_seed

            set_all_random_seed(int(req.seed))
            torch.manual_seed(int(req.seed))
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(int(req.seed))

            t0 = time.perf_counter()
            chunks: list[Any] = []
            resolved_spk_id = (req.zero_shot_spk_id or "").strip()
            try:
                if req.mode == "zero_shot":
                    # CosyVoice3：先登记 spk，再以空 prompt 合成，避免
                    # 「合成文本远短于带 assistant 前缀的 prompt_text」触发漏播参考音。
                    if not resolved_spk_id:
                        digest = hashlib.sha1(
                            f"{prompt_wav.resolve()}|{prompt_text}".encode("utf-8")
                        ).hexdigest()[:12]
                        resolved_spk_id = f"lab_{digest}"
                    if resolved_spk_id not in model.frontend.spk2info:
                        model.add_zero_shot_spk(prompt_text, str(prompt_wav), resolved_spk_id)
                    iterator = model.inference_zero_shot(
                        text,
                        "",
                        "",
                        zero_shot_spk_id=resolved_spk_id,
                        stream=bool(req.stream),
                        speed=float(req.speed),
                        text_frontend=bool(req.text_frontend),
                    )
                elif req.mode == "instruct2":
                    iterator = model.inference_instruct2(
                        text,
                        instruct_text,
                        str(prompt_wav),
                        zero_shot_spk_id=resolved_spk_id,
                        stream=bool(req.stream),
                        speed=float(req.speed),
                        text_frontend=bool(req.text_frontend),
                    )
                else:
                    # cross_lingual：文本侧可自带 assistant 前缀 / 音素标记
                    tts_text = text
                    if req.auto_prefix_prompt and ASSISTANT_PREFIX not in tts_text:
                        tts_text = ASSISTANT_PREFIX + tts_text
                    iterator = model.inference_cross_lingual(
                        tts_text,
                        str(prompt_wav),
                        zero_shot_spk_id=resolved_spk_id,
                        stream=bool(req.stream),
                        speed=float(req.speed),
                        text_frontend=bool(req.text_frontend),
                    )
                for item in iterator:
                    chunks.append(item["tts_speech"])
            except Exception as exc:  # noqa: BLE001 — lab surface
                return SynthResult(ok=False, error=f"{type(exc).__name__}: {exc}")

            if not chunks:
                return SynthResult(ok=False, error="模型未返回音频")

            speech = torch.cat(chunks, dim=1).squeeze(0).detach().cpu().float().numpy()
            elapsed = time.perf_counter() - t0
            pcm = np.clip(speech, -1.0, 1.0)
            pcm16 = (pcm * 32767.0).astype(np.int16)
            sr = int(model.sample_rate)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safe_group = "".join(c if c.isalnum() or c in "-_" else "_" for c in (req.group or "lab"))[:32]
            ensure_lab_dirs()
            if req.persist:
                out = EVALS / f"{stamp}_{safe_group}_{req.mode}.wav"
            else:
                # 试听预览：固定文件名覆盖，避免每次合成污染 evals/
                out = PREVIEW / "preview_latest.wav"
            with wave.open(str(out), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm16.tobytes())

            meta = {
                "request": asdict(req),
                "resolved_prompt_text": prompt_text,
                "resolved_instruct_text": instruct_text,
                "resolved_zero_shot_spk_id": resolved_spk_id,
                "zero_shot_via_spk_cache": req.mode == "zero_shot",
                "wav_path": str(out),
                "sample_rate": sr,
                "duration_sec": round(len(pcm16) / sr, 3),
                "elapsed_sec": round(elapsed, 3),
                "model_dir": str(self.model_dir),
                "loaded_opts": self._loaded_opts,
                "persisted": bool(req.persist),
                "preview": not bool(req.persist),
            }
            meta_path = out.with_suffix(".json")
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            return SynthResult(
                ok=True,
                wav_path=str(out),
                sample_rate=sr,
                duration_sec=meta["duration_sec"],
                elapsed_sec=meta["elapsed_sec"],
                meta=meta,
            )

    def persist_preview(
        self,
        wav_path: str = "",
        *,
        group: str = "lab",
        mode: str = "",
        note: str = "",
    ) -> SynthResult:
        """Copy current preview wav into evals/ with a timestamped name."""
        ensure_lab_dirs()
        src = Path(wav_path).expanduser() if wav_path else (PREVIEW / "preview_latest.wav")
        if not src.is_file():
            return SynthResult(ok=False, error="没有可保存的预览音频，请先合成")
        preview_root = PREVIEW.resolve()
        try:
            resolved = src.resolve()
        except OSError:
            return SynthResult(ok=False, error="无效预览路径")
        # only allow saving from preview/ or already-in-evals re-save skip
        if not resolved.is_relative_to(preview_root):
            if resolved.is_relative_to(EVALS.resolve()):
                return SynthResult(
                    ok=True,
                    wav_path=str(resolved),
                    meta={"already_persisted": True, "wav_path": str(resolved)},
                )
            return SynthResult(ok=False, error="只能保存 lab 预览音频到 evals")

        meta_src = resolved.with_suffix(".json")
        meta: dict[str, Any] = {}
        if meta_src.is_file():
            try:
                meta = json.loads(meta_src.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
        req_meta = meta.get("request") if isinstance(meta.get("request"), dict) else {}
        use_mode = (mode or str(req_meta.get("mode") or "lab")).strip() or "lab"
        use_group = (group or str(req_meta.get("group") or "lab")).strip() or "lab"
        if note:
            req_meta = {**req_meta, "note": note}
            meta["request"] = req_meta
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_group = "".join(c if c.isalnum() or c in "-_" else "_" for c in use_group)[:32]
        safe_mode = "".join(c if c.isalnum() or c in "-_" else "_" for c in use_mode)[:24]
        dest = EVALS / f"{stamp}_{safe_group}_{safe_mode}.wav"
        import shutil

        shutil.copy2(resolved, dest)
        meta["wav_path"] = str(dest)
        meta["persisted"] = True
        meta["preview"] = False
        meta["saved_from"] = str(resolved)
        dest.with_suffix(".json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return SynthResult(
            ok=True,
            wav_path=str(dest),
            sample_rate=int(meta.get("sample_rate") or 24000),
            duration_sec=float(meta["duration_sec"]) if meta.get("duration_sec") is not None else 0.0,
            meta=meta,
        )


ENGINE = CosyEngine()
