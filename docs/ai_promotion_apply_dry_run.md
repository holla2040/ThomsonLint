# AI Promotion Apply Dry Run v0 (PR34)

## Overview

`ai_promotion_apply_dry_run.py` consumes PR32 promotion-plan artifacts and PR33 approval-decision
artifacts, then produces a deterministic dry-run apply plan for approved candidates only.

This script creates six preview artifacts under `--out-dir`. It does not promote or apply data.

## What This Script Does NOT Do

- **does not call ai** — no AI service invocations of any kind.
- **does not invoke ai** — equivalent statement for clarity.
- **does not apply approvals** — approved decisions are recorded as dry-run operations only.
- **does not promote data** — no core artifacts are modified or written.
- **does not write core artifacts** — current/rating/topology/copper/margin core outputs are never written by PR34.
- **normalized outputs are not overwritten** — PR32 and PR33 artifacts remain read-only.
- **ingestion, allocation, and calculation reruns are not performed** — current allocation, copper/via/margin calculations are never invoked.
- **does not run ingestion** — no `current_model_ingest.py` or `rating_model_ingest.py`.
- **does not run allocation** — no `topology_current_allocate.py`.
- **does not run calculations** — no `topology_copper_calculate.py` or `topology_margin_calculate.py`.

## What This Script Does

1. Reads PR32 promotion plan (`ai-candidate-promotion-plan.json`), approval queue, and status from `--promotion-dir`.
2. Reads PR33 approval decisions (`ai-approval-decisions.json`) and validation artifact (`ai-approval-decision-validation.json`).
3. Filters to **approved-only** decisions that pass local revalidation against the PR33 validation artifact.
4. Skips pending, rejected, and needs_info decisions (recorded in `skipped_decisions`, not blocked).
5. Generates dry-run operations with deterministic IDs for each valid approved candidate.
6. Produces six preview artifacts under `--out-dir`.

## Output Artifacts

| File | Purpose |
|------|---------|
| `ai-approved-promotion-apply-dry-run.json` | Main artifact: all dry-run operations, blocked operations, skipped decisions, and summary counts. |
| `ai-approved-promotion-apply-status.json` | Status artifact confirming nothing was applied; all safety flags are false. |
| `ai-approved-current-model-merge-preview.json` | Preview of current-model candidates that would be added or skipped as duplicates. |
| `ai-approved-rating-model-merge-preview.json` | Preview of rating-model candidates that would be added or skipped as duplicates. |
| `ai-approved-addenda-merge-preview.json` | Preview of addenda candidates (always requires merge validator). |
| `ai-promotion-apply-blockers.json` | All blocked operations with reason codes and details. |

## Dry-Run Operation Classes

| Class | Meaning |
|-------|---------|
| `would_add` | No core match; candidate would be added as a new record. |
| `would_update` | Core match exists but values differ; preview of what update would look like. |
| `would_skip_duplicate` | Exact duplicate found in core; no write needed. |
| `would_block_conflict` | Value/identity conflict detected; blocked by default (or previewed with `--allow-conflict-preview`). |
| `would_require_merge_validator` | Addenda candidate always requires a future merge validator stage. |

## Approved-Only Rules

- Only decisions with `decision == "approved"` become dry-run operations or blocker entries.
- Approved decisions must have valid PR33 validation (`validation_status == "valid"`).
- Approved decisions without an `approval_note` are blocked.
- Decisions with `safe_to_apply: true` in PR33 input are invalid and blocked.
- Decisions with `safe_for_future_apply_stage: true` in PR33 validation are invalid and blocked.
- Unknown `approval_item_id` or `promotion_candidate_id` is blocked.
- Duplicate decisions for the same `approval_item_id` are invalid.

## Preview Rules

- Approved current-model candidates preview as `would_add` (no core match) or `would_skip_duplicate` (exact duplicate).
- Approved rating-model candidates preview similarly at connector level only; must not expand to pins.
- Regulator input/output side is never inferred from any source.
- Conflicts block by default; `--allow-conflict-preview` includes conflict context in warnings but still blocks core writes.
- Addenda always require a future merge validator and are preview-only.
- Passive support remains preview-only.

## Dry-Run Artifact Constraints

All dry-run operations include:
- `dry_run_only: true` (const)
- `writes_core_artifact: false` (const)
- `safe_to_apply_in_pr34: false` (const)
- `requires_future_apply_stage: true` (const)

The status artifact confirms:
- `applied_anything: false`
- `wrote_core_artifacts: false`
- `ran_ingestion: false`
- `ran_current_allocation: false`
- `ran_calculations: false`
- `merged_addenda: false`

## CLI Usage

```bash
python scripts/ai_promotion_apply_dry_run.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --decisions exports/TestProject/ai_promotion/ai-approval-decisions.json \
  --decision-validation exports/TestProject/ai_promotion/ai-approval-decision-validation.json \
  --out-dir exports/TestProject/ai_promotion_apply_dry_run \
  [--core-current-models-normalized path] \
  [--core-rating-models-normalized path] \
  [--strict] \
  [--include-addenda] \
  [--allow-conflict-preview]
```

### Optional Flags

| Flag | Purpose |
|------|---------|
| `--core-current-models-normalized` | Path to core current models for conflict detection. |
| `--core-rating-models-normalized` | Path to core rating models for conflict detection. |
| `--strict` | Fail if PR32 promotion status is "failed". |
| `--include-addenda` | Always include addenda merge preview even with no candidates. |
| `--allow-conflict-preview` | Preview conflict context in warnings; still blocks core writes. |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Dry run completed (may have blockers/warnings). |
| 1 | Promotion plan failed or validation errors present. |
| 2 | Missing/malformed inputs, CLI error. |

## Future Apply Stage Requirements

PR34 dry-run artifacts are **inputs to future apply stages only**. They do not perform any actual application.

Future PRs will need to implement:

1. **Candidate core-input apply** — actual write of approved current-model and rating-model candidates to core normalized artifacts.
2. **Explicit flag for core-input apply** — a new script or flag that requires explicit opt-in before writing core data.
3. **Addenda merge validator** — a dedicated stage for merging role, pin, rail, and passive-support addenda safely.
4. **Provenance carry-through** — ensuring AI-extracted provenance is preserved through the apply pipeline.
5. **Readiness rerun** — re-running calculation readiness inventory after core inputs are updated.
6. **Calculation rerun only after explicit promotion** — copper/via/margin calculations run only when explicitly triggered post-promotion.

## Guardrails

- No forbidden output filenames (core model/calculation files).
- No forbidden fields (finding_id, violation, severity, compliance_pass, etc.).
- All outputs stay inside `--out-dir`.
- PR32 and PR33 artifacts are never modified.
- Deterministic operation IDs based on SHA1 digest of approval_item_id + candidate_kind.
