#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname)" != Darwin ]]; then
  echo 'macOS上で実行してください。'; exit 1
fi
PYTHON_BIN="${JUNO_PYTHON:-python3}"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -c 'import tkinter; import rtmidi'
.venv/bin/python -m pytest -q
.venv/bin/python -m PyInstaller --noconfirm JunoSketch.spec
open dist
