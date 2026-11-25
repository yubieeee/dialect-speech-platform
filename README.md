# dialect-speech-platform

方言语音研究与交付工作区。

| 目录 | 职责 |
|------|------|
| [`docs/`](docs/) | 计划、会议、产品文档 |
| [`corpus-kit/`](corpus-kit/) | **共用**媒资入库（CLI + [`web/`](corpus-kit/web/) 入库台） |
| [`cosy-lab/`](cosy-lab/) | **共用** CosyVoice3 调试台与批跑 |
| [`dialect-assets/`](dialect-assets/) | **按方言**数据：`<dialect>/{image,video,wav16k,…}` |
| `asr-tts/` | 语音平台（交付，独立仓） |
| `voice-engine/` | 引擎与 `.runtime` 权重（独立仓） |

文昌话数据：`dialect-assets/wenchang/`（含 `image/`、`video/`）。

## 运行环境（勿污染系统 Python）

不要用 `/usr/bin/python3 -m pip` 往系统装包。各目录绑定如下：

| 目录 | 环境 | 启动 |
|------|------|------|
| `cosy-lab/` | conda **`tts`**（`~/miniconda3/envs/tts`） | `./cosy-lab/run.sh` → :7865 |
| `corpus-kit/` | 同上；`run.sh` 默认该解释器 | `./corpus-kit/web/run.sh` → :7870 |
| `dialect-assets/`、`docs/` | 无运行时 | 纯数据 / 文档 |
| `asr-tts/voice-platform/` | 项目 **uv `.venv`**（CPython 3.12） | `cd asr-tts/voice-platform && uv sync --locked && uv run …` |
| `voice-engine` ASR worker | conda **`qwen3-asr`** | `.runtime/asr.json` 的 `model_python` |
| `voice-engine` TTS worker | conda **`tts`** | `.runtime/tts.json` 的 `model_python` |

`ffmpeg` 可用系统 `/usr/bin/ffmpeg`。本机另有 `asr_ai_main` 等 env，与文昌调试主路径无关。
