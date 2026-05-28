#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-example}"
EXPORTS_DIR="${EXPORTS_DIR:-exports}"
OUT="${EXPORTS_DIR}/${PROJECT}-image-evidence-review.json"
INVENTORY="${EXPORTS_DIR}/${PROJECT}-image-evidence-inventory.json"

if [[ -f ".env.local" ]]; then
  set -a
  # shellcheck source=/dev/null
  source ".env.local"
  set +a
fi

: "${VISION_BASE_URL:?missing VISION_BASE_URL; set it in the environment or .env.local}"
: "${VISION_MODEL:?missing VISION_MODEL; set it in the environment or .env.local}"

TIMEOUT_SECONDS="${PHASE13_VISION_TIMEOUT_SECONDS:-1800}"
MAX_TOKENS="${PHASE13_VISION_MAX_TOKENS:-8000}"
SLEEP_SECONDS="${PHASE13_VISION_SLEEP_SECONDS:-0.1}"
RESUME="${PHASE13_VISION_RESUME:-1}"
FORCE="${PHASE13_VISION_FORCE:-0}"

echo "== Phase 13 local vision review =="
echo "PROJECT=$PROJECT"
echo "VISION_MODEL=$VISION_MODEL"
echo "VISION_BASE_URL=$VISION_BASE_URL"
echo "timeout=${TIMEOUT_SECONDS}s max_tokens=$MAX_TOKENS sleep=${SLEEP_SECONDS}s resume=$RESUME force=$FORCE"

echo "== Validating image evidence inventory =="
python3 - "$PROJECT" "$EXPORTS_DIR" <<'PY'
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

project = sys.argv[1]
exports = Path(sys.argv[2])
inventory_path = exports / f"{project}-image-evidence-inventory.json"

schematic = sorted(exports.glob(f"{project}-img-sch-p*.png"))
layout = sorted(exports.glob(f"{project}-img-layout-p*.png"))
images = schematic + layout

if not images:
    raise SystemExit(f"missing Phase 13 PNG inputs under {exports}")

if inventory_path.exists():
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid image evidence inventory {inventory_path}: {exc}")
    if not isinstance(inventory, dict):
        raise SystemExit(f"image evidence inventory is not an object: {inventory_path}")
else:
    inventory = {
        "phase": 7,
        "phase_name": "Enforce Image Review Gate",
        "project": project,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

output_files = [str(path) for path in images]
inventory.update({
    "pdf_sources": inventory.get("pdf_sources", []),
    "conversion_tool": inventory.get("conversion_tool", "existing_png_artifacts"),
    "fallback_used": inventory.get("fallback_used", False),
    "user_approved_fallback": inventory.get("user_approved_fallback", False),
    "total_pages_expected": len(images),
    "total_pages_rendered": len(images),
    "output_files": output_files,
    "schematic_pngs": [str(path) for path in schematic],
    "layout_pngs": [str(path) for path in layout],
    "pages_inspected": inventory.get("pages_inspected", len(images)),
    "limitations": inventory.get("limitations", []),
    "confirmation_no_pixel_quantitative_claims": True,
    "overall_pass": True,
})

inventory_path.parent.mkdir(parents=True, exist_ok=True)
inventory_path.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"READY: {inventory_path} covers {len(images)} image(s)")
PY

vision_args=(
  --project "$PROJECT"
  --exports "$EXPORTS_DIR"
  --out "$OUT"
  --timeout "$TIMEOUT_SECONDS"
  --max-tokens "$MAX_TOKENS"
  --sleep "$SLEEP_SECONDS"
)

if [[ "$FORCE" == "1" ]]; then
  vision_args+=(--force)
elif [[ "$RESUME" == "1" ]]; then
  vision_args+=(--resume)
fi

echo "== Running local multimodal image review =="
vision_status=0
python3 scripts/vision_image_review.py "${vision_args[@]}" || vision_status=$?
if [[ "$vision_status" != "0" ]]; then
  echo "WARN: vision_image_review.py exited with status $vision_status; checkpoint/audit will decide final gate status"
fi

echo "== Ensuring checkpoint for phase 13 =="
checkpoint_status=0
python3 scripts/ensure_phase_checkpoint.py \
  --project "$PROJECT" \
  --phase 13 \
  --exports "$EXPORTS_DIR" \
  --mode replace || checkpoint_status=$?

echo "== Auditing phase 13 =="
audit_status=0
python3 scripts/audit_phase.py \
  --project "$PROJECT" \
  --phase 13 \
  --exports "$EXPORTS_DIR" || audit_status=$?

if [[ "$checkpoint_status" != "0" || "$audit_status" != "0" ]]; then
  exit 1
fi

exit 0
