#!/usr/bin/env bash
set -euo pipefail

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required: https://brew.sh/"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install with: brew install python"
  exit 1
fi

echo "[1/4] Installing liblsl..."
brew install labstreaminglayer/tap/lsl

echo "[2/4] Creating virtual environment..."
python3 -m venv .venv

echo "[3/4] Installing Python packages..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[4/4] Import test..."
.venv/bin/python - <<'PY'
import pylsl
import websockets
print("pylsl OK")
print("websockets OK")
PY

echo
echo "Installation complete."
echo "Activate with: source .venv/bin/activate"
echo "Then start with: python bridge.py --open"
