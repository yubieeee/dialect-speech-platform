# 木生的信 · 《给阿嬷的情书》

## 对应关系结论

| 材料 | 内容 | 结论 |
|------|------|------|
| `dialect-assets/wenchang/image/带音标短文/木生的信*.png` | 短文练习：汉字 + 文昌口音拼音（调号 1–8） | **金标文本/音标**（25 句） |
| `dialect-assets/wenchang/video/木生的信_男声.mp4` | 文昌市融媒体中心口播；左侧竖排字幕 | **同篇朗读音频**；字幕与金标高度同篇，措辞偶有差异（汝/你、有/在；视频另有口播衔接） |

**可以对应上**：同一作品、同一方言口播。训练文本优先用图片金标 `musheng_letter_gold.jsonl`；时间轴来自竖排字幕 OCR 后人工切分的 `../video/木生的信_男声.gold.srt`。

## 金标句表

见同目录 `musheng_letter_gold.jsonl`（`text_zh` + `phonetic`）。

## 入库

- 音频切句：`corpus-kit mine` + `木生的信_男声.gold.srt`
- 音标不进入 Cosy `prompt_text`（合成仍用书面汉字）；音标进 `lexicon/` / 本文件供正音对照

## 版权备注

视频号/融媒体公开传播内容；研究摘录入库，台账见 `sources/BIBLIOGRAPHY.md`。对外发布前需再核授权。
