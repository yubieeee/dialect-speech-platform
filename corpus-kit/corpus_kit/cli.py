"""CLI entrypoints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .paths import MEDIA_INBOX, VOICE_DATA, dialect_root, manifest_path
from .pipeline import (
    asr_fill,
    crawl_and_mine,
    import_items,
    ingest_local,
    init_dialect,
    mine_media,
    qc_dialect,
    transcode_dialect,
)
from .sources.crawl import load_url_list
from .sources.local_import import LocalImportSource


def _parse_band(raw: str) -> tuple[float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("OCR band 格式: y0,y1 例如 0.68,0.95")
    y0, y1 = float(parts[0]), float(parts[1])
    if not (0.0 <= y0 < y1 <= 1.0):
        raise argparse.ArgumentTypeError("OCR band 须满足 0 <= y0 < y1 <= 1")
    return y0, y1


def _parse_region(raw: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("OCR region 格式: x0,y0,x1,y1 例如 0.02,0.15,0.42,0.70")
    x0, y0, x1, y1 = (float(p) for p in parts)
    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        raise argparse.ArgumentTypeError("OCR region 坐标须在 0..1 且 x0<x1, y0<y1")
    return x0, y0, x1, y1


def _add_ocr_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--ocr-hardsubs",
        action="store_true",
        help="无软字幕时，对画面硬字幕做 OCR 生成时间轴（录屏适用）",
    )
    p.add_argument("--ocr-interval", type=float, default=0.35, help="OCR 抽帧间隔秒")
    p.add_argument(
        "--ocr-band",
        type=_parse_band,
        default=(0.68, 0.95),
        help="字幕竖向带 y0,y1（相对画面高度，默认 0.68,0.95）",
    )
    p.add_argument(
        "--ocr-region",
        type=_parse_region,
        default=None,
        help="字幕矩形 x0,y0,x1,y1（优先于 --ocr-band；竖排字幕用左侧区）",
    )
    p.add_argument("--ocr-min-score", type=float, default=0.5)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="corpus-kit",
        description="可复用方言语料入库：URL爬取 / 本机媒资+字幕 → 音文对 → manifest",
    )
    p.add_argument("--version", action="version", version=f"corpus-kit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="创建 dialect-assets/<dialect>/ 目录骨架（含 inbox/）")
    init_p.add_argument("--dialect", required=True)

    mine = sub.add_parser(
        "mine",
        help="本机视频/音频+字幕 → 音文对齐切句入库（默认读 inbox/）",
    )
    mine.add_argument("--dialect", required=True)
    mine.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"媒资目录；默认 dialect-assets/<dialect>/{MEDIA_INBOX}/",
    )
    mine.add_argument("--locale", default="")
    mine.add_argument("--speaker", default="")
    mine.add_argument(
        "--license-note",
        default="local_media_drop",
        help="版权/来源备注",
    )
    mine.add_argument(
        "--split",
        choices=("auto", "cues", "silence", "none"),
        default="auto",
        help="auto=有字幕按字幕切；cues=强制字幕；silence=静音切；none=整段",
    )
    mine.add_argument("--no-subs", action="store_true", help="忽略字幕")
    mine.add_argument("--prefer-lang", default="zh")
    mine.add_argument("--require-text", action="store_true")
    _add_ocr_flags(mine)
    mine.add_argument("--noise-db", type=float, default=-35.0)
    mine.add_argument("--min-silence", type=float, default=0.5)
    mine.add_argument("--min-sec", type=float, default=1.5)
    mine.add_argument("--max-sec", type=float, default=20.0)
    mine.add_argument("--no-keep-original", action="store_true")
    mine.add_argument("--no-recursive", action="store_true")

    ocr = sub.add_parser(
        "ocr-subs",
        help="仅对录屏/硬字幕视频 OCR，写出同名 .srt（不入库）",
    )
    ocr.add_argument("--input", required=True, type=Path, help="视频文件或目录")
    ocr.add_argument("--out", type=Path, default=None, help="输出 srt；目录输入时忽略")
    _add_ocr_flags(ocr)
    # ocr-subs 默认就做 OCR
    ocr.set_defaults(ocr_hardsubs=True)

    asr = sub.add_parser(
        "asr",
        help="用百炼千问 ASR（qwen3-asr-flash）给无文本片段填草稿（待校）",
    )
    asr.add_argument("--dialect", required=True)
    asr.add_argument(
        "--key-file",
        type=Path,
        default=None,
        help="百炼 API Key 文件；默认 DASHSCOPE_API_KEY 或 ~/xny/private/bailian.key",
    )
    asr.add_argument("--model", default="qwen3-asr-flash")
    asr.add_argument(
        "--language",
        default="zh",
        help="asr_options.language；zh 含普通话/四川话/闽南语/吴语等官方声明范围",
    )
    asr.add_argument("--force", action="store_true", help="覆盖已有非待填文本")
    asr.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0=不限制）")
    asr.add_argument("--ids", default="", help="只处理这些 id（逗号分隔）")
    asr.add_argument("--enable-itn", action="store_true")

    crawl = sub.add_parser(
        "crawl",
        help="网络 URL 下载音视频+字幕并入库（yt-dlp；需 --i-have-rights）",
    )
    crawl.add_argument("--dialect", required=True)
    crawl.add_argument("--url", default="", help="单个 URL")
    crawl.add_argument("--url-file", type=Path, default=None, help="URL 列表文件（一行一个）")
    crawl.add_argument(
        "--i-have-rights",
        action="store_true",
        help="确认链接可合法用于本项目（必填）",
    )
    crawl.add_argument(
        "--license-note",
        required=True,
        help="授权/来源说明（必填，禁止 TODO 占位）",
    )
    crawl.add_argument("--locale", default="")
    crawl.add_argument("--speaker", default="")
    crawl.add_argument(
        "--sub-langs",
        default="zh.*,zh-Hans,zh-CN,zh,en.*,en",
        help="yt-dlp 字幕语言优先级",
    )
    crawl.add_argument(
        "--cookies-from-browser",
        default="",
        help="可选：chrome/chromium/firefox（部分站点登录态）",
    )
    crawl.add_argument("--max-downloads", type=int, default=50)
    crawl.add_argument("--no-auto-subs", action="store_true", help="不要自动生成字幕轨")
    crawl.add_argument(
        "--split",
        choices=("auto", "cues", "silence", "none"),
        default="auto",
    )
    crawl.add_argument("--no-subs", action="store_true")
    crawl.add_argument("--prefer-lang", default="zh")
    crawl.add_argument(
        "--allow-empty-text",
        action="store_true",
        help="允许无字幕片段入库（默认 --require-text）",
    )
    crawl.add_argument("--min-sec", type=float, default=1.5)
    crawl.add_argument("--max-sec", type=float, default=20.0)

    imp = sub.add_parser("import", help="从本地目录/文件导入到 raw/ 并更新 manifest")
    imp.add_argument("--dialect", required=True)
    imp.add_argument("--input", required=True, type=Path)
    imp.add_argument("--locale", default="")
    imp.add_argument("--speaker", default="")
    imp.add_argument("--text-from-filename", action="store_true")
    imp.add_argument("--skip-copy", action="store_true")
    imp.add_argument("--no-recursive", action="store_true")

    tr = sub.add_parser("transcode", help="raw → wav16k 并回写 manifest")
    tr.add_argument("--dialect", required=True)

    qc = sub.add_parser("qc", help="质检 wav 并写 reports/qc_*.json")
    qc.add_argument("--dialect", required=True)

    slim = sub.add_parser("slim", help="manifest 精简为 TTS 字段（去掉信源/路径等）")
    slim.add_argument("--dialect", required=True)

    ing = sub.add_parser("ingest", help="已是短音频时：import + transcode + qc")
    ing.add_argument("--dialect", required=True)
    ing.add_argument("--input", required=True, type=Path)
    ing.add_argument("--locale", default="")
    ing.add_argument("--speaker", default="")
    ing.add_argument("--text-from-filename", action="store_true")
    ing.add_argument("--skip-copy", action="store_true")
    ing.add_argument("--no-recursive", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "init":
            root = init_dialect(args.dialect)
            print(f"OK dialect root: {root}")
            print(f"drop media+subs here: {root / MEDIA_INBOX}")
            print(f"dialect-assets: {VOICE_DATA}")
            return 0

        if args.cmd == "ocr-subs":
            from .hardsubs import ocr_hardsubs_to_srt
            from .paths import VIDEO_SUFFIXES

            inp = Path(args.input).expanduser().resolve()
            band = args.ocr_band
            results = []
            files: list[Path]
            if inp.is_file():
                files = [inp]
            else:
                files = sorted(
                    p
                    for p in inp.rglob("*")
                    if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
                )
            if not files:
                raise FileNotFoundError(f"未找到视频: {inp}")
            for vid in files:
                out = args.out if (args.out and inp.is_file()) else vid.with_suffix(".srt")
                cues, srt = ocr_hardsubs_to_srt(
                    vid,
                    out,
                    interval=args.ocr_interval,
                    band=band,
                    region=args.ocr_region,
                    min_score=args.ocr_min_score,
                )
                results.append(
                    {"video": str(vid), "srt": str(srt), "cues": len(cues)}
                )
            print(json.dumps({"items": results}, ensure_ascii=False, indent=2))
            return 0 if any(r["cues"] > 0 for r in results) else 2

        if args.cmd == "mine":
            report = mine_media(
                args.dialect,
                args.input,
                locale=args.locale,
                speaker=args.speaker,
                license_note=args.license_note,
                split_mode=args.split,
                use_subtitles=not args.no_subs,
                prefer_lang=args.prefer_lang,
                ocr_hardsubs=args.ocr_hardsubs,
                ocr_interval=args.ocr_interval,
                ocr_band=args.ocr_band,
                ocr_region=args.ocr_region,
                ocr_min_score=args.ocr_min_score,
                require_text=args.require_text,
                noise_db=args.noise_db,
                min_silence=args.min_silence,
                min_sec=args.min_sec,
                max_sec=args.max_sec,
                keep_original=not args.no_keep_original,
                recursive=not args.no_recursive,
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
            print(
                json.dumps(
                    {k: report[k] for k in keys if k in report},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if report["fail"] == 0 else 2

        if args.cmd == "asr":
            id_set = {x.strip() for x in args.ids.split(",") if x.strip()} or None
            report = asr_fill(
                args.dialect,
                key_file=args.key_file,
                model=args.model,
                language=args.language,
                force=args.force,
                ids=id_set,
                limit=args.limit,
                enable_itn=args.enable_itn,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["failed"] == 0 or report["filled"] > 0 else 2

        if args.cmd == "crawl":
            urls = load_url_list(args.url, args.url_file)
            report = crawl_and_mine(
                args.dialect,
                urls=urls,
                license_note=args.license_note,
                i_have_rights=args.i_have_rights,
                locale=args.locale,
                speaker=args.speaker,
                sub_langs=args.sub_langs,
                cookies_from_browser=args.cookies_from_browser,
                max_downloads=args.max_downloads,
                write_auto_subs=not args.no_auto_subs,
                split_mode=args.split,
                use_subtitles=not args.no_subs,
                prefer_lang=args.prefer_lang,
                require_text=not args.allow_empty_text,
                min_sec=args.min_sec,
                max_sec=args.max_sec,
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
            print(
                json.dumps(
                    {k: report[k] for k in keys if k in report},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if report["fail"] == 0 else 2

        if args.cmd == "import":
            init_dialect(args.dialect)
            src = LocalImportSource(
                args.input,
                text_from_filename=args.text_from_filename,
                speaker=args.speaker,
                recursive=not args.no_recursive,
            )
            items = src.collect()
            rows = import_items(
                args.dialect,
                items,
                locale=args.locale,
                skip_copy=args.skip_copy,
            )
            print(f"OK imported {len(rows)} → {manifest_path(args.dialect)}")
            for r in rows:
                print(f"  {r.id}\t{r.raw}")
            return 0

        if args.cmd == "transcode":
            rows = transcode_dialect(args.dialect)
            print(f"OK transcoded {len(rows)} → {dialect_root(args.dialect) / 'wav16k'}")
            return 0

        if args.cmd == "qc":
            report = qc_dialect(args.dialect)
            print(
                f"OK qc total={report['total']} pass={report['pass']} "
                f"warn={report['warn']} fail={report['fail']}"
            )
            print(f"report: {report['report_path']}")
            return 0 if report["fail"] == 0 else 2

        if args.cmd == "slim":
            from .manifest import load_manifest, save_manifest

            rows = load_manifest(manifest_path(args.dialect))
            save_manifest(manifest_path(args.dialect), rows, tts_only=True)
            print(f"OK slimmed {len(rows)} → {manifest_path(args.dialect)} (TTS fields only)")
            return 0

        if args.cmd == "ingest":
            report = ingest_local(
                args.dialect,
                args.input,
                locale=args.locale,
                speaker=args.speaker,
                text_from_filename=args.text_from_filename,
                skip_copy=args.skip_copy,
                recursive=not args.no_recursive,
            )
            print(
                json.dumps(
                    {
                        k: report[k]
                        for k in ("imported", "total", "pass", "warn", "fail", "report_path")
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if report["fail"] == 0 else 2

        raise AssertionError(args.cmd)
    except PermissionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
