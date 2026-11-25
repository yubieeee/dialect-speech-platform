# CosyVoice3 文昌调试台

本地直连 `Fun-CosyVoice3-0.5B-2512`：推理参数尽量暴露；训练参数可编辑并**导出配置**（默认不开训）。

## 目录

```text
cosy-lab/
├── app.py / cosy_engine.py / paths.py / train_export.py
├── run.sh / run_w2_batch.py
├── static/          # 前端
└── README.md
```

## 运行环境

conda **`tts`**（`/home/apc/miniconda3/envs/tts/bin/python`）。`run.sh` 默认该解释器；可用 `COSY_PYTHON` 覆盖。  
与 `voice-engine` TTS worker **共用**此 env，争 GPU 时先停现役或错开显存。不要用系统 pip 给本台装包。

## 启动

```bash
conda activate tts
./cosy-lab/run.sh
# http://127.0.0.1:7865
```

可选环境变量：`COSY_MODEL_DIR`、`COSY_SOURCE`、`HOST`、`PORT`、`COSY_PYTHON`。

## 页签

| 页 | 用途 |
|----|------|
| 推理调试 | zero_shot / instruct2 / cross_lingual；合成默认只预览，**「保存到 evals」** 才落盘 |
| 训练/微调参数 | 导出到 `dialect-assets/wenchang/train/exports/` |
| 输出历史 | 浏览 `dialect-assets/wenchang/evals/` |

## 注意

- 不走平台 SPI / presets；听感过关后再接交付链路。
- 语料很少时不要真开训。
- 与现役 TTS worker 争 GPU 时先停现役或错开显存。
