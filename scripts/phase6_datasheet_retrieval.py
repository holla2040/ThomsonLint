#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "datasheet_helper.py"

if not HELPER.exists():
    print(f"ERROR: missing helper: {HELPER}", file=sys.stderr)
    raise SystemExit(2)

cmd = [sys.executable, str(HELPER), "run-phase6"]
raise SystemExit(subprocess.call(cmd, cwd=str(ROOT)))
