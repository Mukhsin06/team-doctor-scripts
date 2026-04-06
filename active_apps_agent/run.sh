#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
VENV_DIR="$(pwd)/venv"
VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  rm -rf "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
"$VENV_PYTHON" -m pip install -r requirements.txt
"$VENV_PYTHON" main.py
