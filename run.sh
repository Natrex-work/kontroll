#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -d ".venv" ]; then
  . .venv/bin/activate
fi
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
