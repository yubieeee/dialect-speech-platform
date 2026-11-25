#!/usr/bin/env python3
"""Batch-run W2 A/B/C × eval_bank_v0 via local cosy-lab HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_BANK = ROOT / "dialect-assets" / "wenchang" / "sentences" / "eval_bank_v0.json"
PRIMARY_REF = ROOT / "dialect-assets" / "wenchang" / "refs" / "wc_primary.wav"
PROMPT_TEXT = "老乡你好，今天想办什么业务"  # 与 wc_primary 对齐
SHEET = ROOT / "dialect-assets" / "wenchang" / "evals" / "W2_listen_sheet.md"

GROUPS = [
    {
        "group": "W2A",
        "mode": "zero_shot",
        "instruct_text": "",
        "prompt_text": PROMPT_TEXT,
        "auto_prefix_prompt": True,
        "auto_prefix_instruct": False,
    },
    {
        "group": "W2B",
        "mode": "instruct2",
        "instruct_text": "请用海南文昌话表达。",
        "prompt_text": "",
        "auto_prefix_prompt": True,
        "auto_prefix_instruct": True,
    },
    {
        "group": "W2C",
        "mode": "instruct2",
        "instruct_text": "请用闽南话表达。",
        "prompt_text": "",
        "auto_prefix_prompt": True,
        "auto_prefix_instruct": True,
    },
]


def post_json(url: str, payload: dict, timeout: float = 600) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, timeout: float = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def update_sheet(results: list[dict]) -> None:
    """Fill 合成文件名 column from batch results; leave scores blank."""
    if not SHEET.is_file():
        return
    text = SHEET.read_text(encoding="utf-8")
    by_key = {(r["group"], r["sentence_id"]): Path(r["wav_path"]).name for r in results if r.get("ok")}
    # Replace empty filename cells for known rows: "| E0x |  |  |  |  |  |" pattern variants
    for group, sid in by_key:
        name = by_key[(group, sid)]
        # Match table rows that still have empty last cell for this sentence under that section
        # Simpler: append a machine index block at end
        pass
    block_lines = [
        "",
        "---",
        "",
        f"## 脚本批量索引（{time.strftime('%Y-%m-%d %H:%M')}）",
        "",
        "以下由 `cosy-lab/run_w2_batch.py` 生成；分数请人工听后填上表。",
        "",
        "| 组 | 句 ID | 模式 | 合成文件 | 时长 s |",
        "|----|-------|------|----------|--------|",
    ]
    for r in results:
        if not r.get("ok"):
            block_lines.append(
                f"| {r['group']} | {r['sentence_id']} | {r['mode']} | FAILED: {r.get('error','')} |  |"
            )
            continue
        block_lines.append(
            f"| {r['group']} | {r['sentence_id']} | {r['mode']} | `{Path(r['wav_path']).name}` | {r.get('duration_sec','')} |"
        )
    # Replace previous script index if present
    marker = "## 脚本批量索引"
    if marker in text:
        text = text.split(marker)[0].rstrip() + "\n"
    text = text.rstrip() + "\n" + "\n".join(block_lines) + "\n"
    SHEET.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:7865")
    parser.add_argument("--ref", default=str(PRIMARY_REF))
    parser.add_argument("--groups", default="W2A,W2B,W2C", help="comma list")
    parser.add_argument("--sentences", default="", help="comma ids, default all")
    args = parser.parse_args()

    bank = json.loads(EVAL_BANK.read_text(encoding="utf-8"))
    if args.sentences.strip():
        want = {x.strip() for x in args.sentences.split(",") if x.strip()}
        bank = [x for x in bank if x["id"] in want]
    want_groups = {x.strip() for x in args.groups.split(",") if x.strip()}
    groups = [g for g in GROUPS if g["group"] in want_groups]

    ref = Path(args.ref)
    if not ref.is_file():
        print(f"参考音不存在: {ref}", file=sys.stderr)
        return 1

    try:
        st = get_json(f"{args.base}/api/status")
    except Exception as exc:  # noqa: BLE001
        print(f"无法连接调试台 {args.base}: {exc}", file=sys.stderr)
        print("请先: cd cosy-lab && ./run.sh", file=sys.stderr)
        return 1

    if not st.get("ready"):
        print("模型未加载，正在预加载…")
        load = post_json(f"{args.base}/api/load", {"fp16": True})
        if not load.get("ok") and "ready" not in load:
            print(f"加载失败: {load}", file=sys.stderr)
            return 1
        print("加载完成", load.get("loaded_opts") or load)

    results: list[dict] = []
    total = len(groups) * len(bank)
    i = 0
    for g in groups:
        for sent in bank:
            i += 1
            payload = {
                "mode": g["mode"],
                "text": sent["text"],
                "prompt_text": g["prompt_text"],
                "instruct_text": g["instruct_text"],
                "prompt_wav": str(ref),
                "speed": 1.0,
                "stream": False,
                "text_frontend": False,
                "seed": 42,
                "auto_prefix_prompt": g["auto_prefix_prompt"],
                "auto_prefix_instruct": g["auto_prefix_instruct"],
                "group": g["group"],
                "note": sent["id"],
                "fp16": True,
                "persist": True,  # 批量听感跑写入 evals/
            }
            print(f"[{i}/{total}] {g['group']} {sent['id']} {g['mode']} …", flush=True)
            t0 = time.perf_counter()
            try:
                out = post_json(f"{args.base}/api/synthesize", payload)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                try:
                    out = json.loads(body)
                except json.JSONDecodeError:
                    out = {"ok": False, "error": body}
            except Exception as exc:  # noqa: BLE001
                out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            row = {
                "group": g["group"],
                "sentence_id": sent["id"],
                "mode": g["mode"],
                "ok": bool(out.get("ok")),
                "wav_path": out.get("wav_path") or "",
                "duration_sec": out.get("duration_sec"),
                "elapsed_sec": out.get("elapsed_sec") or round(time.perf_counter() - t0, 3),
                "error": out.get("error") or "",
            }
            results.append(row)
            if row["ok"]:
                print(f"  ok  {Path(row['wav_path']).name}  dur={row['duration_sec']}s")
            else:
                print(f"  FAIL  {row['error']}")

    out_json = ROOT / "dialect-assets" / "wenchang" / "evals" / f"W2_batch_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    update_sheet(results)
    ok_n = sum(1 for r in results if r["ok"])
    print(f"\n完成 {ok_n}/{len(results)} → {out_json}")
    print(f"听感表已追加索引: {SHEET}")
    return 0 if ok_n == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
