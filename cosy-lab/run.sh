#!/usr/bin/env bash
# CosyVoice3 文昌调试台
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${COSY_PYTHON:-/home/apc/miniconda3/envs/tts/bin/python}"
export COSY_MODEL_DIR="${COSY_MODEL_DIR:-$ROOT/voice-engine/.runtime/models/Fun-CosyVoice3-0.5B-2512}"
export COSY_SOURCE="${COSY_SOURCE:-$ROOT/voice-engine/.runtime/sources/CosyVoice}"
cd "$(dirname "$0")"
exec "$PY" app.py --host "${HOST:-127.0.0.1}" --port "${PORT:-7865}"
