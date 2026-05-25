#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:?Usage: run_openhands_phase.sh PHASE [PROJECT]}"
PROJECT="${2:-example}"

PROMPT_DIR=".agents_tmp/prompts"
LOG_DIR=".agents_tmp/logs"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
PROMPT_FILE="${PROMPT_DIR}/phase-${PHASE}.md"
LOG_FILE="${LOG_DIR}/phase-${PHASE}-${RUN_ID}.jsonl"

mkdir -p "$PROMPT_DIR" "$LOG_DIR"

python3 scripts/write_phase_prompt.py \
  --phase "$PHASE" \
  --project "$PROJECT" \
  --out "$PROMPT_FILE"

echo "== Running OpenHands phase $PHASE =="
echo "Prompt: $PROMPT_FILE"
echo "Log:    $LOG_FILE"

openhands \
  --headless \
  --json \
  --override-with-envs \
  --file "$PROMPT_FILE" | tee "$LOG_FILE"

echo "== Auditing phase $PHASE =="
python3 scripts/audit_phase.py \
  --project "$PROJECT" \
  --phase "$PHASE" \
  --exports exports
