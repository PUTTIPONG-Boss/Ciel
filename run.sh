#!/usr/bin/env bash
# Start Ciel on macOS / Linux:  ./run.sh
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "✦ First run: creating virtual environment…"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

[ -f .env ] || cp .env.example .env

exec python -m ciel
