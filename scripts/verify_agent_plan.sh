#!/usr/bin/env bash
set -euo pipefail

ROOT_PLAN="./PLAN.md"
TMP_PLAN="./.agents_tmp/PLAN.md"

fail() {
  echo "BLOCKED: $1"
  exit 2
}

require_file() {
  [[ -f "$1" ]] || fail "missing file: $1"
}

require_text() {
  local file="$1"
  local text="$2"
  grep -Fq "$text" "$file" || fail "missing required text in $file: $text"
}

reject_text() {
  local file="$1"
  local text="$2"
  if grep -Fq "$text" "$file"; then
    fail "found forbidden regressed text in $file: $text"
  fi
}

require_file "$ROOT_PLAN"
require_file "$TMP_PLAN"

cmp -s "$ROOT_PLAN" "$TMP_PLAN" || fail ".agents_tmp/PLAN.md is not byte-for-byte identical to PLAN.md"

require_text "$TMP_PLAN" "Artifact-Based Phase Completion Rule"
require_text "$TMP_PLAN" "Phase-Local Gate Enforcement Rule"
require_text "$TMP_PLAN" "Universal phase checkpoint artifact"
require_text "$TMP_PLAN" "No Phase Consolidation"
require_text "$TMP_PLAN" "Status values limited"
require_text "$TMP_PLAN" "local"
require_text "$TMP_PLAN" "found"
require_text "$TMP_PLAN" "ambiguous"
require_text "$TMP_PLAN" "missing"
require_text "$TMP_PLAN" "not_applicable_generic"
require_text "$TMP_PLAN" "Every raw BOM CSV row"
require_text "$TMP_PLAN" "exports/<project>-image-evidence-inventory.json"
require_text "$TMP_PLAN" "exports/<project>-board-evidence-inventory.json"
require_text "$TMP_PLAN" "exports/<project>-board-evidence-inventory-validation.json"
require_text "$TMP_PLAN" "exports/<project>-pre-findings-gate.json"
require_text "$TMP_PLAN" "exports/<project>-review.html"
require_text "$TMP_PLAN" "exports/<project>-report-generation-validation.json"

reject_text "$TMP_PLAN" "found/url_only"
reject_text "$TMP_PLAN" "download_unavailable"
reject_text "$TMP_PLAN" "missing_generic"
reject_text "$TMP_PLAN" "photographs, X-rays, microscopy"

echo "PASS: active plan is verified"
sha256sum "$ROOT_PLAN" "$TMP_PLAN"
wc -l "$ROOT_PLAN" "$TMP_PLAN"
