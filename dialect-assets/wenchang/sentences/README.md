# sentences · 评测与朗读文本

- `eval_bank_v0.md` / `eval_bank_v0.json` — 银行柜面冻结评测句（调试台下拉读 JSON）  
- `musheng_letter_gold.jsonl` / `musheng_letter.md` — 《木生的信》图截金标（有对应口播入库）  
- `short_texts_phonetic.md` + `*_gold.jsonl` — 水调歌头 / 小王子玫瑰 / 千年古盐田（仅文本音标，无口播）  
- `read_aloud_for_recording.md`（待建）— 交给高校/众包的朗读清单  

与 `evals/` 里的合成文件通过「句 ID」对应。增删句子改 JSON（并同步 md）后刷新调试台即可。
