# train/data · ASR / TTS 训练清单

生成时间：20261124-162607

## 筛选规则

| 清单 | 规则 | 条数 |
|------|------|------|
| `asr_train.jsonl` | 有汉字文本 + wav；时长 ≥ 0.8s；保留同文多遍（利于 ASR） | 71 |
| `tts_train.jsonl` | 时长 ≥ 1.2s；**按 text_zh 去重**（优先带 phonetic、其次更长）；适合 Cosy 微调 | 58 |
| `tts_dedup_skipped.jsonl` | TTS 去重掉的同文其它遍 | 11 |
| `../reports/manifest_dropped.jsonl` | 从主 manifest 剔除 | 1 |

主清单 `manifest.jsonl` 已同步清洗（当前 71 条）。

## 字段

- ASR：`id, wav, text_zh, duration_sec, speaker, dialect, locale, sample_rate`
- TTS：另含 `prompt_text`、可选 `phonetic`、`channels`

`wav` 相对 `dialect-assets/wenchang/`。

## 图截金标（无音频）

见 `../../sentences/short_texts_phonetic.md`（68 句）。用于 G2P / 评测句库 / 后续补录，**不在**上述音文对清单中。
