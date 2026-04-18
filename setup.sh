#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
printf '\n[OK] Miljoet er satt opp. Start appen med: ./run.sh\n'
