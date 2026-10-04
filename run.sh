#!/usr/bin/env bash
cd "$(dirname "$0")"
./.venv/bin/python main.py "$@"
stty sane 2>/dev/null || true
