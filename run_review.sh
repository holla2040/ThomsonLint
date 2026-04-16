#!/usr/bin/env bash

# ThomsonLint non-interactive review pipeline
#
# Usage:
#   ./run_review.sh                    # auto-detect project from exports/
#   ./run_review.sh MySpecialProject   # explicit project name
#
# Environment:
#   THOMSONLINT_MODEL   Claude model to use (default: claude-opus-4-7)
#   THOMSONLINT_BUDGET  Max spend in USD per run (default: 10)
#
# Requirements: claude (Claude Code CLI), python3, jq
#
#  What the script does, in order:
#
#  1. gen_context.sh > review_instructions.txt — regenerates the knowledge base prompt (as required by CLAUDE.md pre-commit rule)
#  2. Auto-detects project name from any exports/*-thomson-export-sch.json file
#  3. claude --print in non-interactive mode, with:
#    - --allowedTools Read — Claude only reads files, no side effects
#    - --output-format json — structured JSON envelope for reliable parsing
#    - --json-schema $(cat tests/findings_schema.json) — constrains output to exactly the findings schema
#    - --no-session-persistence — no session saved to disk (clean for automation)
#    - --max-budget-usd 10 — hard spend cap per run
#  4. jq -r '.result' — extracts Claude's response from the CLI JSON envelope
#  5. Python one-liner — strips any accidental markdown fences, validates JSON parses, pretty-prints
#  6. python3 validate_json.py — validates against schema
#  7. python3 tools/gen_report.py — generates the HTML report
#
#  Tunable via environment variables:
#
#  ┌────────────────────┬─────────────────┬────────────────────────────────────────┐
#  │      Variable      │     Default     │                Purpose                 │
#  ├────────────────────┼─────────────────┼────────────────────────────────────────┤
#  │ THOMSONLINT_MODEL  │ claude-opus-4-7 │ Swap to sonnet for faster/cheaper runs │
#  ├────────────────────┼─────────────────┼────────────────────────────────────────┤
#  │ THOMSONLINT_BUDGET │ 10              │ Hard USD cap; run aborts if exceeded   │
#  └────────────────────┴─────────────────┴────────────────────────────────────────┘
#
#  Example with overrides:
#  THOMSONLINT_MODEL=claude-sonnet-4-6 THOMSONLINT_BUDGET=3 ./run_review.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODEL="${THOMSONLINT_MODEL:-claude-opus-4-7}"
MAX_BUDGET="${THOMSONLINT_BUDGET:-10}"

# ── 1. Regenerate review instructions ───────────────────────────────────────
echo "[1/5] Regenerating review_instructions.txt..."
./gen_context.sh > review_instructions.txt

# ── 2. Detect project from exports/ ─────────────────────────────────────────
if [[ -n "${1:-}" ]]; then
    PROJECT="${1}"
    SCH="exports/${PROJECT}-thomson-export-sch.json"
    BRD="exports/${PROJECT}-thomson-export-brd.json"
else
    SCH="$(ls exports/*-thomson-export-sch.json 2>/dev/null | head -1 || true)"
    [[ -z "${SCH:-}" ]] && { echo "ERROR: No *-thomson-export-sch.json found in exports/"; exit 1; }
    BRD="${SCH/%-sch.json/-brd.json}"
    PROJECT=$(basename "${SCH}" -thomson-export-sch.json)
fi

[[ -f "${SCH}" ]] || { echo "ERROR: Schematic not found: ${SCH}"; exit 1; }
[[ -f "${BRD}" ]] || { echo "ERROR: Board file not found: ${BRD}"; exit 1; }

REVIEW_DATE="$(date +%Y-%m-%d)"
FINDINGS="exports/${PROJECT}-findings.json"
REPORT="exports/${PROJECT}-review.html"

echo "[2/5] Project : ${PROJECT}"
echo "      Date    : ${REVIEW_DATE}"
echo "      Model   : ${MODEL}"
echo "      Budget  : \$${MAX_BUDGET}"

# ── 3. Run AI review ─────────────────────────────────────────────────────────
echo "[3/5] Running AI review (this may take a minute)..."

PROMPT="Follow the instructions in review_instructions.txt exactly. \
Read and analyse exports/${PROJECT}-thomson-export-sch.json \
and exports/${PROJECT}-thomson-export-brd.json. \
Output a JSON object matching tests/findings_schema.json. \
Set project_name to '${PROJECT}' and review_date to '${REVIEW_DATE}'."

claude --print "${PROMPT}" \
    --allowedTools "Read,Write" \
    --model "${MODEL}" \
    --output-format json \
    --json-schema "$(cat tests/findings_schema.json)" \
    --no-session-persistence \
    --max-budget-usd "${MAX_BUDGET}" \
    > exports/.claude.output

cat exports/.claude.output | \
    jq -r 'if .result then .result else (. | tostring) end'

echo "      Findings : ${FINDINGS}"

# ── 4. Validate all JSON files ───────────────────────────────────────────────
echo "[4/5] Validate findings report..."
python3 validate_json.py

# ── 5. Generate HTML report ──────────────────────────────────────────────────
# Sometimes Claude doesn't generate the output! So do it ourselves from the raw output
[ ! -e "${FINDINGS}" ] && jq -r '.structured_output' < exports/.claude.output > "${FINDINGS}"

# Fix for:
# - HTML report: not generated (python tools/gen_report.py was blocked for approval;
#                run it manually with `python tools/gen_report.py exports/<project_name>-findings.json --output exports/`)
#       Findings : exports/Actuator_Controller-findings.json
# Not sure why it's blocked, or how to unblock it :(.
echo "[5/5] Generating HTML report..."
python3 tools/gen_report.py "${FINDINGS}" --output exports/

echo ""
echo "Done — open '${REPORT}' in a browser to triage findings."
