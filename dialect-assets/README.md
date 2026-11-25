# dialect-assets · 多方言研究资产

本目录只放 **按方言划分的数据**。入库 / 调试等通用脚本在上一层：

| 共用工具（平台根） | 职责 |
|--------------------|------|
| [`../corpus-kit/`](../corpus-kit/) | crawl / mine / ingest / qc |
| [`../cosy-lab/`](../cosy-lab/) | CosyVoice3 调试台与批跑 |

## 布局

```text
dialect-assets/
├── README.md
├── .gitignore                 # 多方言共用忽略规则
└── <dialect>/                 # 例如 wenchang/；以后可加 shanghai/ …
    ├── image/                 # 该方言：音标/短文截图
    ├── video/                 # 该方言：录屏/成片 + .srt / .gold.srt
    ├── inbox/                 # mine 投放
    ├── raw/  wav16k/  refs/
    ├── sentences/  lexicon/  phonology/
    ├── train/data/  train/exports/
    ├── evals/  reports/
    ├── sources/               # 台账 + private_files
    └── manifest.jsonl
```

本目录无独立 Python 环境。入库 / 调试走上层工具，均用 conda **`tts`**：

```bash
conda activate tts
PYTHONPATH=corpus-kit python -m corpus_kit init --dialect <name>
```

## 当前方言

- [`wenchang/`](wenchang/) — 文昌话（TTS-28）

## 分层原则

| 层 | 放什么 | Git |
|----|--------|-----|
| 清单与摘录 | manifest、评测句、字音表、音系、书目 | **可提交** |
| 图截 | `image/` 小图 | 可提交 |
| 口播视频 / 整书 / wav | `video/`、`private_files/`、`wav16k/` | **不提交**（见 `.gitignore`） |

上游 Cosy 权重在 `voice-engine/.runtime/`，不要拷进本目录。
