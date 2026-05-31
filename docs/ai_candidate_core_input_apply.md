# AI Candidate Core Input Apply v0 (PR35)

## Overview

`ai_candidate_core_input_apply.py` consumes PR34 approved-only dry-run artifacts and writes isolated candidate core-input files. It is an intermediate apply stage only.

PR35 does not call AI, does not write core artifacts, does not write core normalized outputs, does not overwrite normalized outputs, does not run ingestion, does not run allocation, does not run calculations, and does not merge addenda into authoritative topology data.

## Inputs

PR35 reads:

```bash
exports/TestProject/ai_promotion_apply_dry_run/
  ai-approved-promotion-apply-dry-run.json
  ai-approved-promotion-apply-status.json
  ai-promotion-apply-blockers.json
```

Optional base inputs may be supplied:

```bash
--base-current-input exports/TestProject/current-model-input.json
--base-rating-input exports/TestProject/rating-model-input.json
```

Base records are preserved and candidate records append after them. No existing base record is changed.

## Outputs

PR35 writes only under `--out-dir`:

```bash
exports/TestProject/ai_candidate_core_inputs/
  ai-candidate-core-input-apply-manifest.json
  ai-candidate-core-input-apply-status.json
  ai-candidate-current-model-input.json
  ai-candidate-rating-model-input.json
  ai-candidate-role-addenda.json
  ai-candidate-pin-role-addenda.json
  ai-candidate-rail-relationship-hints.json
  ai-candidate-passive-support-inputs.json
  ai-candidate-core-input-apply-diff.json
  ai-candidate-core-input-apply-blockers.json
```

Candidate current/rating files are inputs for future explicit stages. PR35 does not run `current_model_ingest.py`, `rating_model_ingest.py`, `topology_current_allocate.py`, `topology_copper_calculate.py`, or `topology_margin_calculate.py`.

These files are not ready for direct core mutation; a future core apply stage is required.

## Candidate Current And Rating Behavior

Only PR34 operations that are approved for candidate apply are materialized:

- `dry_run_only: true`
- `writes_core_artifact: false`
- `safe_to_apply_in_pr34: false`
- `requires_future_apply_stage: true`
- preview operation status
- `dry_run_operation: would_add`
- `candidate_kind: current_model` or `rating_model`

`would_skip_duplicate` operations are recorded as skipped duplicates and do not create duplicate candidate records.

Candidate records preserve:

- approval provenance
- PR34 operation provenance
- source evidence refs
- target identity
- candidate value, unit, and condition exactly as supplied

PR35 does not infer missing current values, does not treat unknown current as zero, does not infer missing ratings, does not expand connector-wide ratings to pins, does not infer regulator input/output side, and does not calculate margins.

## Addenda Behavior

By default, role addenda, pin-role addenda, rail relationship hints, and passive support records are not materialized. They are recorded as blocked because addenda require a future merge validator.

With `--include-addenda`, PR35 writes isolated candidate addenda files only. These files always set:

- `safe_to_merge_automatically: false`
- `merged_addenda: false`

PR35 never updates authoritative topology, role, pin, rail, passive, or board artifacts.

## CLI

```bash
python scripts/ai_candidate_core_input_apply.py \
  --project TestProject \
  --dry-run-dir exports/TestProject/ai_promotion_apply_dry_run \
  --out-dir exports/TestProject/ai_candidate_core_inputs
```

Optional:

```bash
--base-current-input exports/TestProject/current-model-input.json
--base-rating-input exports/TestProject/rating-model-input.json
--include-addenda
--strict
```

## Manual Validation Commands

```bash
python -m py_compile scripts/ai_candidate_core_input_apply.py tests/test_ai_candidate_core_input_apply.py
python -m pytest tests/test_ai_candidate_core_input_apply.py -v
git diff --check
```

Manual artifact inspection:

```bash
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-core-input-apply-manifest.json | head -120
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-core-input-apply-status.json | head -120
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-current-model-input.json | head -160
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-rating-model-input.json | head -160
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-core-input-apply-diff.json | head -160
python -m json.tool exports/TestProject/ai_candidate_core_inputs/ai-candidate-core-input-apply-blockers.json | head -160
```

## Future PRs

Future work remains explicit and separate:

1. Candidate input ingestion workflow.
2. Explicit core-input apply with opt-in flag.
3. Addenda merge validator.
4. Provenance carry-through improvements.
5. Missing-data readiness rerun.
6. Allocation/calculation rerun only after explicit promotion.
