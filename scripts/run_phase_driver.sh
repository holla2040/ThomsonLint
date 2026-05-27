#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-example}"
START_PHASE="${2:-1}"
END_PHASE="${3:-22}"

echo "== Checking LLM env =="
: "${LLM_API_KEY:?missing LLM_API_KEY}"
: "${LLM_MODEL:?missing LLM_MODEL}"
: "${LLM_BASE_URL:?missing LLM_BASE_URL}"

echo "LLM_MODEL=$LLM_MODEL"
echo "LLM_BASE_URL=$LLM_BASE_URL"

export SEARXNG_BASE="${SEARXNG_BASE:-http://192.168.5.5:8888}"
echo "SEARXNG_BASE=$SEARXNG_BASE"

echo "== Refreshing active plan =="
./scripts/refresh_agent_plan.sh

echo "== Verifying active plan =="
./scripts/verify_agent_plan.sh

echo "== Running phase driver: project=$PROJECT start=$START_PHASE end=$END_PHASE =="

for phase in $(seq "$START_PHASE" "$END_PHASE"); do
  echo
  echo "============================================================"
  echo "PHASE $phase"
  echo "============================================================"
  ./scripts/run_openhands_phase.sh "$phase" "$PROJECT"
done

echo
echo "PASS: phase driver completed phases $START_PHASE through $END_PHASE for project $PROJECT"
