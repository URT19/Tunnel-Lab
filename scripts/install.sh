#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[*] Installing python dependencies..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -r requirements.txt
echo "[*] Done. Run: python3 main.py"