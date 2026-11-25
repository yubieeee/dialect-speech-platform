#!/usr/bin/env bash
# corpus-kit 入库台
set -euo pipefail
cd "$(dirname "$0")"
PY="${CORPUS_KIT_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if [[ -x /home/apc/miniconda3/envs/tts/bin/python ]]; then
    PY=/home/apc/miniconda3/envs/tts/bin/python
  else
    PY=python3
  fi
fi
exec "$PY" app.py --host "${HOST:-127.0.0.1}" --port "${PORT:-7870}"
