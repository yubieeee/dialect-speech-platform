# 文昌话（海南话）研究资产

对应产品 **TTS-28**。通用工具在平台根 `corpus-kit/`、`cosy-lab/`（conda **`tts`**）；**本目录只放文昌数据**，无单独运行环境。

## 目录

```text
wenchang/
├── image/              # 音标/短文截图（金标）
├── video/              # 录屏/成片 + .srt / .gold.srt
├── inbox/              # mine 投放（gitignore）
├── raw/  wav16k/  refs/
├── sentences/  lexicon/  phonology/
├── train/
│   ├── data/           # asr_train.jsonl / tts_train.jsonl
│   ├── exports/        # cosy-lab 导出配置
│   └── exp/            # checkpoint（gitignore）
├── evals/  reports/
├── lab_uploads/        # 调试台临时预览（可清）
├── sources/
│   ├── BIBLIOGRAPHY.md
│   ├── notes/
│   └── private_files/  # 整书等（如海南音字典；gitignore）
└── manifest.jsonl
```

## 流程

1. 新媒体 → `image/` 或 `video/`（字幕配对 `.gold.srt`）
2. 登记 → `sources/BIBLIOGRAPHY.md`
3. `corpus-kit mine --dialect wenchang …` → `wav16k/` + `manifest.jsonl`
4. 训练清单 → `train/data/`
5. 听感 → `evals/`（合成默认预览，显式保存才落盘）

图截拼音索引：[`sentences/short_texts_phonetic.md`](sentences/short_texts_phonetic.md)
