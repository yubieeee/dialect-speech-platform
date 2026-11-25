# CosyVoice3 × 文昌话（海南话）TTS 研究与开发细化计划

> 范围：优先 **TTS-28**（海南话发音人 / 工程 E-11）；ASR **DL-17** 不在本文件主责。  
> 产品依据：`方言语音平台功能介绍｜产品经理版.docx`（R2：混说识别 + 海南话发音人播报）。  
> 工程根：`dialect-speech-platform/`  
> 基座：`Fun-CosyVoice3-0.5B-2512` + conda `tts`  
> 对照：上海话 = 零样本参考音 + locale/instruction（`SH_COSY3_WU`），非基座自带「上海点」。  
> **负责人：TTS / 文昌话调试（本角色）**；平台联调、ASR、商务 HN-Q 由分工方配合。  
> **可读执行计划**：[`TTS开发计划-文昌话.md`](TTS开发计划-文昌话.md)（阶段表 / 本周清单）  
> 日期：2026-11-20；修订：**2026-11-23**（W0/W1 落地 + 105 训练盘点结论）  

---

## 0. 分工与目标

| 角色 | 做什么 | 不做什么 |
|------|--------|----------|
| **本文负责人（你）** | 让 Cosy **能稳定说出可懂的文昌话**（先 POC，再可接入） | 不背 DL-17 识别验收；不背 R1 上海交付 |
| 平台 / 其他 | mock 体验、挂节点、ASR 包、HN-Q 商务 | 不代替你做 Cosy 听感结论 |

**本阶段成功定义（对内）**：固定评测句上，母语认为「像参考说话人、能听出文昌、内容可懂」——对应 **W2 POC**，不是合同 MOS≥4.0。

**产品口径（TTS-28）**：输入 **普通话书面中文** → 按海南话（文昌为代表）读音与韵律合成；金融读法按海南习惯。

**接口边界**

```
当前主战场：conda tts / cosy-lab 直接调 Cosy（可不上 SPI）
听感过关后再：voice-engine presets + SPI Synthesize
微调：仅零样本不够且授权语料到位后，另开评估（见 §9）
```

---

## 1. 问题陈述（为什么要调试）

| 事实 | 含义 |
|------|------|
| Cosy 有 Minnan 等口音先验，无「文昌」现成 speaker | 不能下拉现成音色名 |
| 文昌 ≠ 福建/台闽南腔 | 「闽南 instruct」只作对照，不能当达标 |
| `dialect-assets/wenchang/` 仅 **3** 条参考 | 只够零样本；不够正式发音人，更不够开训 |
| `cosy_config` 目前只认 `zh-CN` / `wu-shanghai` | 进平台前必须做 **W3.0** 放开 `min-hainan` |

**主路径**：文昌参考音 zero-shot + instruct（+ 后续前端读法）。  
**微调**：可选项；105 盘点确认 **Cosy 文昌 SFT 尚未真训**（见 §9）。

---

## 2. 素材与目录（现状）

| 文件 | 角色 |
|------|------|
| `dialect-assets/wenchang/raw/*.m4a` | 原始 3 条（迎客 / 安全 / 结束） |
| `dialect-assets/wenchang/wav16k/*.wav` | 已转 16k mono |
| `dialect-assets/wenchang/refs/wc_primary.wav` | 主参考（已落） |
| `dialect-assets/wenchang/manifest.jsonl` | 3 条；`prompt_text` 暂用文件名，状态「待校」 |
| `dialect-assets/wenchang/evals/` | 已有 smoke / W2B instruct2 试听 wav |

```text
text_written = 文件名书面语     # 合成输入（普通话）
audio        = 文昌口播
prompt_text  = 与参考音对齐的转写（有母语就校；暂无则先用文件名并标注「待校」）
```

目录约定（已建）：

```text
dialect-assets/wenchang/
  raw/          # 原始 m4a
  wav16k/       # 16k mono PCM
  refs/         # 主参考 wc_primary.wav
  evals/        # W2 合成与听评
  train/exports/# cosy-lab 仅导出配置（无 exp/）
  manifest.jsonl
```

---

## 3. 技术路线

```
L0a  零样本探路     ← 当前主战场（W2 听感补全）
L0b  presets 工程化 + min-hainan（W3，须先改白名单）
L0c  文昌金融前端 / 词典（W4，可并行草案）
L0d  可选 Cosy SFT（W5 后 Go/No-Go；≠ Qwen3-TTS LoRA 历史链路）
```

**不要做**：3 条报交付；闽南结果写成文昌达标；数据不够就开训；把 WP-20 mock 或 Qwen LoRA 冒烟当成 Cosy 文昌已训；Key 进仓。

---

## 4. 阶段任务与状态

### W0 — 目录

| ID | 任务 | 状态 | 出口 |
|----|------|------|------|
| W0.1 | gitignore / 密钥隔离 | **完成** | 忽略命中；密钥在仓外 `private/` |
| W0.2 | `wenchang/` 规范目录 | **完成** | 目录存在 |
| W0.3 | API Key 轮换 | 配合方 | 控制台确认（云冒烟已用业务空间 Key，仍建议轮换） |

### W1 — 转码与 manifest

| ID | 任务 | 状态 | 出口 |
|----|------|------|------|
| W1.1 | m4a → 16k mono PCM wav | **完成** | `wav16k/*.wav` |
| W1.2 | 写 `manifest.jsonl` | **完成** | 3 条可加载 |
| W1.3 | 口播质检（有母语则听；暂无则自标「待母语」） | **待母语** | 简易表 |
| W1.4 | 选定 / 拼接主参考 | **完成（单条）** | `refs/wc_primary.wav`；拼接对照未做 |

### W2 — 零样本对照（**已结案 → 先扩录**）

| 组 | 设置 | 现状 |
|----|------|------|
| A | 文昌 ref + zero_shot | **已评**：音色像，长句不可懂；漏 prompt 后半句 |
| B | 文昌 ref + instruct「海南文昌话」 | **已评**：可懂，整句偏普通话，「像文昌」≈1 |
| C | 文昌 ref + instruct「闽南语」 | **已评**：比 B 更有方言腔，仍非文昌达标 |
| D | 普通话 ref + 同上 instruct | 暂缓（不挡扩录结论） |
| E | 文昌 ref + 金融句 | 并入扩录后复测 |

**出口**：听感表已填；**三选一 = 先扩录**（见 `dialect-assets/wenchang/evals/W2 听感表 · A _ B _ C.md`）。**暂不进 W3、不开微调。**

### W3 — 接入引擎（扩录后复测过关再开）

W3.0 放开 `min-hainan` → presets `HN_COSY3_WC_*` → SPI 冒烟 → 不覆盖沪语音色。

### W4 / W5 / W6

前端读法草案；**扩录（当前主线）** 与正式 MOS；ASR 错开。

---

## 5. 下一步清单（按优先级）— 扩录阶段

环境：`conda activate tts`；调试台仍可用于复测。

1. [x] W2 A/B/C × E01～E05 批量合成 + 听感打分  
2. [x] 三选一：**先扩录**  
3. [ ] 定扩录规格：同说话人、银行话术、目标句数（研究 10～20 → 正式 ≥30～50）、授权与采音方式  
4. [ ] 做**可复用语料管线**骨架（采集适配器 + 转码/切分/转写/manifest → `dialect-assets/<locale>/`）  
5. [ ] 首批扩录入库后，复跑 W2B（+ 可选拼接更长 ref），再决定 W3 / 微调  
6. [ ] （并行可选）排查 A 组 zero_shot「漏 prompt 后半句」是否配方/前缀问题  

**当前最低交付**：扩录规格一页 + 管线能吃进本地 wav 并写出 manifest。

---

## 6. 成功标准（你这条线）

| 级别 | 标准 |
|------|------|
| 已达成 | W0+W1 目录/转码/manifest/主参考 + cosy-lab + 至少 1 组 B 试听 |
| 本周 POC（W2） | 固定句上「像说话人且可懂文昌」有母语或你方可复述的记录 |
| 预演示（W3） | presets 可加载；银行 3 类话术可播 |
| 合同 TTS | MOS≥4.0 等 → 要 W5，不是本周范围 |

---

## 7. 风险（调试时盯住）

| 风险 | 你怎么处理 |
|------|------------|
| 参考音太短 | 同说话人拼接做对照，结论里写明 |
| 文件名 ≠ 口播 | prompt 标「待校」；有母语再改 |
| 闽南指令带偏 | 保留组 C，结论分开写 |
| 想直接微调 | 先写完 W2 三选一；对照 §9，数据不够不开训 |
| 进平台 locale 报错 | 走 W3.0，别硬改 presets 撞白名单 |
| 误认「平台已能训 TTS」 | WP-20 是编排+mock；Cosy 真训器未接（§9） |

---

## 8. 与总计划

- 波次 A（mock 体验）已基本完成，**不挡** Cosy 调试。  
- 上海 R1 验收不占用本周主目标。  
- 海南 R2 工程化（W3+）以 **W2 结论** 为准入。  

### 调试台（已落）

本地前端：`cosy-lab/`（`./cosy-lab/run.sh` → http://127.0.0.1:7865）

- 推理：zero_shot / instruct2 / cross_lingual，暴露 speed、seed、stream、text_frontend、fp16 等  
- 训练：参数面可编辑，**只导出**到 `dialect-assets/wenchang/train/exports/`（不默认开训）  
- 合成输出：`dialect-assets/wenchang/evals/`  

优先用调试台跑满 W2 听感；微调仍等 W2 结论 + §9 门槛。

---

## 9. 105 训练盘点结论（2026-11-23）→ 对文昌微调的约束

盘点机：`192.168.0.105`（用户 `apc`）。与文昌 Cosy 微调相关的事实如下。

### 9.1 三条链路各是什么

| 链路 | 本盘状态 | 对文昌的含义 |
|------|----------|--------------|
| **CosyVoice3 SFT** | 上游 `train.py` 在 `.runtime/sources/CosyVoice/`；`train/exports` 仅有配置/`run_train.sh`；**无 `exp/`、无微调 checkpoint** | **未真训**；开训前须过 W2 + 语料门槛 |
| **Qwen3-TTS + ms-swift LoRA** | 2026-11-02 在 105 做过 2→3 步真训冒烟；脚本在 `asr-tts/validation/qwen3-tts-swift-lora/`；产物目录 `.validation/` **已不在盘上** | **历史选型证据**；2026-11-06 起默认 TTS 已改为 Cosy，**不能外推**为文昌 Cosy 已训 |
| **L1 WP-20 训练编排** | 控制台 / SPI / mock 闭环；`vp-engine-mock/train.py` 无真算法；E-07 `train-engine` **目录未建** | 管理能力可复用；**不等于** Cosy 训练器已接入 |

旁路：`/home/apc/dialectASR/.../ft-demo/` 为 **ASR** LoRA，与 TTS 无关。

### 9.2 相关绝对路径（速查）

| 路径 | 用途 |
|------|------|
| `voice-engine/.runtime/sources/CosyVoice/cosyvoice/bin/train.py` | Cosy 官方训练入口 |
| `voice-engine/.runtime/models/Fun-CosyVoice3-0.5B-2512/` | 基座权重（非微调产物） |
| `cosy-lab/train_export.py` | 只导出 YAML/脚本，不启动训练 |
| `dialect-assets/wenchang/train/exports/20261123-114627_smoke_export/` | smoke 导出；无 `exp/` |
| `asr-tts/docs/design/tasks/V-TTS-SWIFT-LORA*.md` | Qwen LoRA 验收与「改 Cosy」选型覆盖 |
| `asr-tts/docs/design/TRAINING-*.md` + `vp-server/.../studio/training/` | WP-20 契约与编排 |
| `asr-tts/validation/qwen3-tts-swift-lora/` | 历史验训脚本（可复跑，非文昌默认） |

### 9.3 开发思路（冻结口径）

```
平台 WP-20（任务/权限/日志/登记）
    └── 将来接 L0 train-engine（E-07，未实现）
            ├── 历史：Qwen3-TTS ms-swift LoRA（对照/回退）
            └── 目标：CosyVoice3 独立配方（与 ASR/Qwen-TTS 环境隔离）

当前文昌：
    cosy-lab 推理听感 → W2 结论
         →（不够）扩录 W5
         →（仍不够且授权到位）再评估 Cosy SFT，用 train/exports 模板起步
```

要点：

1. **一套平台管理、按模型独立执行器与 venv**（Qwen-ASR / Cosy / 历史 Qwen-TTS 不可默认共环境）。  
2. Cosy 开训条件：**W2 三选一完成** + 授权语料显著多于 3 条 + 明确 Go（听感不够且扩录后仍不够）。  
3. 开训前准备：`data.list` / parquet、独立 GPU 窗口（勿与现役 TTS worker 抢显存）、从 `train/exports` 的 `run_train.sh` 改路径后冒烟；产物须落可复现目录（勿只留在被 gitignore 的临时路径）。  
4. **不把** WP-20 绿勾、Qwen LoRA 历史通过、或 `train/exports` 存在，写成「文昌已微调」。

### 9.4 微调 Go / No-Go（W5 门）

| 条件 | Go | No-Go |
|------|----|-------|
| W2 A/B/C（至少）听感表 | 已完成且结论清晰 | 未写结论 |
| 语料 | 同说话人授权句达到研究门槛（计划原表：研究 10～20；正式 ≥30～50） | 仍仅 3 条 |
| 工程 | Cosy 训练环境与现役推理隔离方案写明 | 与线上/联调 worker 抢同一 GPU 无预案 |
| 预期 | 写清「期望改善的听感维」 | 为训而训、无验收句 |

---

## 10. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-11-20 | 初稿：文昌零样本主路径 |
| 2026-11-23 | 分工落地、cosy-lab、下午开工清单 |
| 2026-11-23 | **W0/W1 标完成**；W2 现状；新增 **§9 105 训练盘点** 约束微调口径 |
