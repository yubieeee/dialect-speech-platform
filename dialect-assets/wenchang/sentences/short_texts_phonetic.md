# 带音标短文金标（图截）

来源：`dialect-assets/wenchang/image/带音标短文/` 微信短文练习截图（文昌口音）。
仅文本+拼音金标，**无对应口播音频** → 不进 ASR/TTS 音文对清单；供 G2P / 评测文本 / 朗读采集用。

| 篇目 | 句数 | 金标 | lexicon |
|------|------|------|---------|
| 水调歌头·明月几时有（苏轼） | 19 | `sentences/shui_diao_ge_tou_gold.jsonl` | `lexicon/shui_diao_ge_tou.tsv` |
| 《小王子》中的玫瑰（圣埃克絮佩里） | 13 | `sentences/little_prince_rose_gold.jsonl` | `lexicon/little_prince_rose.tsv` |
| 千年古盐田（乔柒裕） | 11 | `sentences/qiannian_guyantian_gold.jsonl` | `lexicon/qiannian_guyantian.tsv` |
| 五指山歌（黎族民歌） | 5 | `sentences/wuzhi_shange_gold.jsonl` | `lexicon/wuzhi_shange.tsv` |
| 中秋饼（古老的童谣） | 5 | `sentences/zhongqiu_bing_gold.jsonl` | `lexicon/zhongqiu_bing.tsv` |
| 各国国歌（绕口令） | 1 | `sentences/geguo_guoge_gold.jsonl` | `lexicon/geguo_guoge.tsv` |
| 久久不见久久见（海南民歌） | 8 | `sentences/jiujiu_bujian_gold.jsonl` | `lexicon/jiujiu_bujian.tsv` |
| 饶舌顺口溜（齐） | 6 | `sentences/raoshe_shunkouliu_gold.jsonl` | `lexicon/raoshe_shunkouliu.tsv` |

**合计 68 句。**

## 清洗约定（ASR/TTS 向）

- 去掉括注（如「一种野果」），正文只留可朗读汉字。
- 民歌重复段保留（如「久久不见」阿妹/阿哥两段），供朗读多样性。
- `lp_07`「把罩子放好」音节偏少，按截图保留待校。

