#!/usr/bin/env bash
set -euo pipefail

ROOT_PLAN="./PLAN.md"
TMP_DIR="./.agents_tmp"
TMP_PLAN="${TMP_DIR}/PLAN.md"

if [[ ! -f "$ROOT_PLAN" ]]; then
  echo "BLOCKED: root PLAN.md not found"
  exit 2
fi

mkdir -p "$TMP_DIR"
cp "$ROOT_PLAN" "$TMP_PLAN"

if cmp -s "$ROOT_PLAN" "$TMP_PLAN"; then
  echo "READY: .agents_tmp/PLAN.md is byte-for-byte identical to PLAN.md"
else
  echo "BLOCKED: .agents_tmp/PLAN.md differs from PLAN.md"
  exit 2
fi

echo "== sha256 =="
sha256sum "$ROOT_PLAN" "$TMP_PLAN"

echo "== line counts =="
wc -l "$ROOT_PLAN" "$TMP_PLAN"
