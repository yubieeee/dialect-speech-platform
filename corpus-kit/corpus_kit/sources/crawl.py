"""URL → media + subtitle download (yt-dlp), with copyright gate."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .base import CollectedItem

_SAFE = re.compile(r"[^\w\u4e00-\u9fff.-]+", re.UNICODE)


def require_yt_dlp() -> list[str]:
    """Return argv prefix to invoke yt-dlp."""
    path = shutil.which("yt-dlp")
    if path:
        return [path]
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "未找到 yt-dlp。请先安装: pip install -U yt-dlp"
        ) from exc
    return ["python3", "-m", "yt_dlp"]


def _safe_name(text: str, fallback: str = "media") -> str:
    stem = _SAFE.sub("_", text).strip("._")
    return (stem[:80] or fallback)


def assert_crawl_rights(*, i_have_rights: bool, license_note: str) -> None:
    note = (license_note or "").strip()
    if not i_have_rights:
        raise PermissionError(
            "网络抓取已启用版权门：必须显式传入 --i-have-rights，"
            "表示你确认目标链接可合法用于本项目语料（自有/授权/许可协议允许）。"
        )
    if not note or note in {"local_media_drop", "TODO", "tbd", "none"}:
        raise PermissionError(
            "必须提供有效 --license-note（来源站点、授权方式或许可证，禁止占位符）。"
        )


def load_url_list(url: str = "", url_file: Path | None = None) -> list[str]:
    urls: list[str] = []
    if url:
        urls.append(url.strip())
    if url_file is not None:
        path = Path(url_file).expanduser().resolve()
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    # de-dupe keep order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    if not out:
        raise ValueError("请提供 --url 或 --url-file")
    return out


@dataclass
class DownloadedMedia:
    media_path: Path
    source_url: str
    title: str = ""
    subtitle_paths: list[Path] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)


def _normalize_sidecar_subs(media: Path) -> list[Path]:
    """Ensure at least media.srt if yt-dlp wrote media.zh.srt etc."""
    parent = media.parent
    stem = media.stem
    found = sorted(
        p
        for p in parent.glob(f"{stem}*")
        if p.suffix.lower() in {".srt", ".vtt", ".ass", ".ssa"} and p.is_file()
    )
    if not found:
        return []
    # prefer creating plain stem.srt for mine's find_sidecar_subtitle
    plain = parent / f"{stem}.srt"
    if not plain.exists():
        srt_like = [p for p in found if p.suffix.lower() == ".srt"]
        src = srt_like[0] if srt_like else found[0]
        if src.suffix.lower() == ".srt":
            shutil.copy2(src, plain)
            if plain not in found:
                found.insert(0, plain)
    return found


def _try_fetch_sibling_subtitles(media_url: str, media_path: Path) -> list[Path]:
    """
    For direct media links (…/talk.mp4), also try …/talk.srt|.vtt|.ass.
    Many static hosts / CDN folders publish media+sidecar this way.
    """
    import urllib.error
    import urllib.request

    parsed = urlparse(media_url)
    if parsed.scheme not in {"http", "https"}:
        return []
    # strip query for sibling guess
    path = parsed.path
    if "." not in path.rsplit("/", 1)[-1]:
        return []
    base = media_url
    # remove query/fragment
    if "?" in base:
        base = base.split("?", 1)[0]
    if "#" in base:
        base = base.split("#", 1)[0]
    dot = base.rfind(".")
    if dot < 0:
        return []
    root = base[:dot]
    saved: list[Path] = []
    for ext in (".srt", ".vtt", ".ass"):
        sub_url = root + ext
        dest = media_path.with_suffix(ext)
        if dest.exists():
            saved.append(dest)
            continue
        try:
            with urllib.request.urlopen(sub_url, timeout=20) as resp:
                data = resp.read()
            if not data or len(data) < 8:
                continue
            dest.write_bytes(data)
            saved.append(dest)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            continue
    if saved and not media_path.with_suffix(".srt").exists():
        # prefer srt for mine
        for p in saved:
            if p.suffix.lower() == ".srt":
                break
            if p.suffix.lower() == ".vtt":
                # leave vtt; find_sidecar handles it
                break
    return saved


def download_urls(
    urls: list[str],
    out_dir: Path,
    *,
    sub_langs: str = "zh.*,zh-Hans,zh-CN,zh,en.*,en",
    cookies_from_browser: str = "",
    max_downloads: int = 50,
    write_auto_subs: bool = True,
) -> list[DownloadedMedia]:
    """
    Download each URL's best audio/video + subtitles into out_dir.
    Uses yt-dlp (YouTube / B站 / 多数公开页可用；站点策略变化时可能失败)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    yt = require_yt_dlp()
    results: list[DownloadedMedia] = []

    for i, url in enumerate(urls[:max_downloads]):
        host = urlparse(url).netloc or "web"
        prefix = f"{i:03d}_{_safe_name(host)}"
        outtmpl = str(out_dir / f"{prefix}_%(id)s.%(ext)s")
        cmd = [
            *yt,
            "--no-playlist",
            "--newline",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "--write-info-json",
            "--write-subs",
            "--sub-langs",
            sub_langs,
            "--convert-subs",
            "srt",
            "-o",
            outtmpl,
        ]
        if write_auto_subs:
            cmd.append("--write-auto-subs")
        if cookies_from_browser:
            cmd.extend(["--cookies-from-browser", cookies_from_browser])
        cmd.append(url)

        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            # retry audio-only / simpler
            cmd_retry = [
                *yt,
                "--no-playlist",
                "--newline",
                "-f",
                "bestaudio/best",
                "--write-info-json",
                "--write-subs",
                "--sub-langs",
                sub_langs,
                "--convert-subs",
                "srt",
                "-o",
                outtmpl,
            ]
            if write_auto_subs:
                cmd_retry.append("--write-auto-subs")
            if cookies_from_browser:
                cmd_retry.extend(["--cookies-from-browser", cookies_from_browser])
            cmd_retry.append(url)
            proc2 = subprocess.run(cmd_retry, capture_output=True, text=True, check=False)
            if proc2.returncode != 0:
                err = (proc2.stderr or proc.stderr or proc2.stdout or "")[-2000:]
                raise RuntimeError(f"下载失败: {url}\n{err}")

        # locate media + info json written for this prefix
        media_candidates = sorted(
            p
            for p in out_dir.glob(f"{prefix}_*")
            if p.suffix.lower()
            in {".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac"}
            and p.is_file()
        )
        if not media_candidates:
            raise RuntimeError(f"下载完成但未找到媒体文件: {url} (prefix={prefix})")
        media = media_candidates[0]
        info: dict[str, Any] = {}
        info_path = media.with_suffix(".info.json")
        # yt-dlp names info as <outtmpl stem>.info.json — may differ from media ext
        if not info_path.is_file():
            alts = list(out_dir.glob(f"{prefix}_*.info.json"))
            if alts:
                info_path = alts[0]
        if info_path.is_file():
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                info = {}
        title = str(info.get("title") or media.stem)
        # sibling .srt on same host (direct links) then normalize yt-dlp names
        _try_fetch_sibling_subtitles(url, media)
        subs = _normalize_sidecar_subs(media)
        results.append(
            DownloadedMedia(
                media_path=media,
                source_url=url,
                title=title,
                subtitle_paths=subs,
                info=info,
            )
        )
    return results


class CrawlSource:
    """Download remote URLs then expose paths as CollectedItem (pre-mine)."""

    name = "crawl"

    def __init__(
        self,
        urls: list[str],
        out_dir: Path,
        *,
        license_note: str,
        i_have_rights: bool = False,
        sub_langs: str = "zh.*,zh-Hans,zh-CN,zh,en.*,en",
        cookies_from_browser: str = "",
        max_downloads: int = 50,
        write_auto_subs: bool = True,
    ) -> None:
        assert_crawl_rights(i_have_rights=i_have_rights, license_note=license_note)
        self.urls = urls
        self.out_dir = Path(out_dir)
        self.license_note = license_note
        self.sub_langs = sub_langs
        self.cookies_from_browser = cookies_from_browser
        self.max_downloads = max_downloads
        self.write_auto_subs = write_auto_subs
        self.downloads: list[DownloadedMedia] = []

    def collect(self) -> list[CollectedItem]:
        self.downloads = download_urls(
            self.urls,
            self.out_dir,
            sub_langs=self.sub_langs,
            cookies_from_browser=self.cookies_from_browser,
            max_downloads=self.max_downloads,
            write_auto_subs=self.write_auto_subs,
        )
        items: list[CollectedItem] = []
        for d in self.downloads:
            items.append(
                CollectedItem(
                    path=d.media_path,
                    text_zh="",
                    prompt_text="",
                    speaker="",
                    source_url=d.source_url,
                    license_note=self.license_note,
                    extra={
                        "title": d.title,
                        "subtitle_paths": [str(p) for p in d.subtitle_paths],
                        "crawl": "yt-dlp",
                    },
                )
            )
        return items
