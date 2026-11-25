# 文昌话（海南话）研究资产

对应产品 **TTS-28**；调试入口：平台根下 `cosy-lab/`。

## 目录

```text
wenchang/
├── manifest.jsonl      # 已入库音文对（TTS 精简字段）
├── raw/                # 原始录音片段
├── wav16k/             # 16k mono，训练/参考
├── refs/               # 主参考音
├── sentences/          # 评测句、图截金标 jsonl
├── lexicon/            # 汉字↔拼音表
├── phonology/          # 音系速查
├── train/
│   ├── data/           # asr_train.jsonl / tts_train.jsonl
│   ├── exports/        # cosy-lab 导出的训练配置模板
│   └── exp/            # checkpoint（gitignore）
├── evals/              # 听感表 md；合成 wav 按需保存（默认可清）
├── reports/            # qc / 清洗记录
├── inbox/              # mine 投放（gitignore，留 .gitkeep）
├── lab_uploads/        # 调试台临时上传/预览（可清）
└── sources/
    ├── BIBLIOGRAPHY.md
    ├── notes/
    └── private_files/  # 整书 PDF 等（gitignore）
```

## 流程

1. **登记** → `sources/BIBLIOGRAPHY.md`
2. **可公开摘录** → `lexicon/` / `phonology/` / `sentences/`
3. **整书/大批量** → `sources/private_files/` 或仓外盘
4. **口播训练** → `raw/` → `wav16k/` → `manifest.jsonl` → `train/data/`
5. **听感** → `evals/` 里 md；合成音频用调试台「保存到 evals」再落盘

## 边界

| 东西 | 位置 |
|------|------|
| Cosy 推理 / SPI | `voice-engine/` |
| 调试台 | `cosy-lab/` |
| 入库工具 | `corpus-kit/` |
| 计划 / 会议 | `docs/` |
