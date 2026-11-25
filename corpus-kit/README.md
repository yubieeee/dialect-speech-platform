# corpus-kit · 可复用方言语料入库工具

目标产物：**音频 + 文本对齐**的 `manifest.jsonl`。

## 依赖

- Python ≥ 3.10
- `ffmpeg` / `ffprobe`
- **网络爬取**：`pip install -U yt-dlp`

## 路径 A：网络爬取（推荐省事）

给公开可合法使用的 URL（或 URL 列表），自动拉 **音视频 + 字幕** 并切句入库：

```bash
cd /home/apc/xny/dialect-speech-platform
pip install -U yt-dlp   # 若未装

# urls.txt 一行一个链接
PYTHONPATH=corpus-kit python3 -m corpus_kit crawl \
  --dialect wenchang \
  --url-file urls.txt \
  --i-have-rights \
  --license-note "示例：CC-BY / 官方可下载 / 已获授权-台账见 BIBLIOGRAPHY" \
  --locale min-hainan
```

单条：

```bash
PYTHONPATH=corpus-kit python3 -m corpus_kit crawl \
  --dialect wenchang \
  --url 'https://…' \
  --i-have-rights \
  --license-note "已获授权-内部采集"
```

| 开关 | 说明 |
|------|------|
| `--i-have-rights` | **必填**版权确认 |
| `--license-note` | **必填**来源/授权说明 |
| `--cookies-from-browser chrome` | 需登录的站点可借浏览器 Cookie |
| `--allow-empty-text` | 允许无字幕也入库（默认要求有文本） |
| `--no-auto-subs` | 不要 yt-dlp 自动字幕 |

下载落在 `dialect-assets/<dialect>/sources/crawl_dl/<时间戳>/`（gitignore）。

**边界**：基于 yt-dlp，覆盖 YouTube / B 站等常见公开页；**不**破解 DRM、不绕过付费墙、不针对盗版站写专用爬虫。无软字幕时自动字幕（若有）可作初稿，仍需人工 `待校`。

## 路径 B：录屏 + 硬字幕 OCR（视频号等）

微信视频号等无法直链下载时：本机录屏（画面上有字幕）→ OCR 出时间轴 → 切音文对。

```bash
pip install -U rapidocr onnxruntime opencv-python-headless Pillow

# 只生成 srt
PYTHONPATH=corpus-kit python3 -m corpus_kit ocr-subs \
  --input ~/Videos/文昌新闻录屏.mp4 \
  --ocr-band 0.68,0.95

# 或一步入库（无软字幕时自动 OCR）
# 把录屏丢进 inbox/ 后：
PYTHONPATH=corpus-kit python3 -m corpus_kit mine \
  --dialect wenchang \
  --ocr-hardsubs \
  --require-text \
  --license-note "screen_record_channels_ocr"
```

| 参数 | 说明 |
|------|------|
| `--ocr-hardsubs` | 开启硬字幕 OCR |
| `--ocr-band 0.68,0.95` | 只认画面下方字幕带（避开视频号顶栏/进度条） |
| `--ocr-interval 0.35` | 抽帧间隔；越小越准越慢 |

OCR 结果仍建议人工 `待校`。文昌话**不要用**百炼 ASR 当字幕（已实测不可用）。

## 路径 C：本机投放（已有软字幕）

```text
dialect-assets/wenchang/inbox/
  节目.mp4
  节目.srt
```

```bash
PYTHONPATH=corpus-kit python3 -m corpus_kit mine \
  --dialect wenchang --require-text --license-note "self_record"
```

## 其它命令

`init` / `ingest` / `import` / `transcode` / `qc`
