# dialect-assets · 方言研究资产

语料、词典摘录、听感评测、资料台账。**不放**平台业务代码、不放模型权重。

## 目录一览

```text
dialect-assets/
├── README.md
├── .gitignore
├── image/                 # 投放：音标/短文截图（金标文本）
├── video/                 # 投放：录屏/成片 + .srt / .gold.srt
└── wenchang/              # 正式方言资产（见该目录 README）
    ├── manifest.jsonl
    ├── wav16k/  raw/  refs/
    ├── sentences/  lexicon/  phonology/
    ├── train/data/  train/exports/
    ├── evals/  reports/
    └── sources/           # 台账 + private_files（整书等，gitignore）
```

## 分层原则

| 层 | 放什么 | Git |
|----|--------|-----|
| 清单与摘录 | manifest、评测句、字音表、音系、书目 | **可提交** |
| 小样音频 | 少量参考 wav、代表性听感样例 | 可选 / LFS |
| 大批量原始件 | 整书、爬取包、OCR 中间帧 | **不提交**（见 `.gitignore`） |
| 密钥 | API Key | **禁止**；仓外存放 |

## 怎么用

1. 新媒体丢进 `image/` 或 `video/`（字幕配对 `.gold.srt`）
2. `corpus-kit mine` / `ingest` → 写入 `wenchang/`
3. 训练清单：[`wenchang/train/data/`](wenchang/train/data/)
4. 图截拼音金标：[`wenchang/sentences/short_texts_phonetic.md`](wenchang/sentences/short_texts_phonetic.md)

上游 Cosy 源码与权重在 `voice-engine/.runtime/`，不要拷进本目录。
