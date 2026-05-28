#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate

python -m pip install -r requirements-dev.txt

if [ "$#" -eq 0 ]; then
  python -m pytest -v
else
  python -m pytest "$@" -v
fi
