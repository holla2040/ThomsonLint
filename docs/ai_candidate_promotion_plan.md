# AI Candidate Promotion Plan

PR32 creates a reviewable promotion plan and approval queue from isolated PR31 AI candidate-normalized outputs. It does not call AI, execute packets, rebuild upstream AI artifacts, rerun ingestion, promote data, overwrite normalized outputs, run current allocation, run copper/via/margin calculations, merge addenda, create findings, or make pass/fail or compliance judgments.

The promotion plan compares candidate outputs under `exports/TestProject/ai_ingested/` against optional core normalized artifacts:

- `exports/TestProject-current-models-normalized.json`
- `exports/TestProject-rating-models-normalized.json`

If core artifacts are missing, the comparison basis is recorded as `core_missing`. This creates add-only promotion candidates with warnings, and human approval is still required.

## Outputs

PR32 writes only promotion review artifacts:

```text
exports/TestProject/ai_promotion/
  ai-candidate-promotion-plan.json
  ai-candidate-approval-queue.json
  ai-candidate-promotion-diff.json
  ai-candidate-promotion-status.json
  ai-addenda-promotion-review.json
  ai-human-review-promotion-index.json
```

These files are not core artifacts and are not ingestion inputs. They are approval planning records.

## Comparison Results

Current candidates are matched by record type, refdes, rail name, branch ID, current field or current type, and condition where available.

Rating candidates are matched by target type, refdes, pin, rating name, and condition where available. Connector-wide ratings are not expanded to pins. Regulator input/output side is not inferred.

The comparison can classify records as:

- `add_candidate`: no matching core record exists
- `duplicate_existing`: the candidate matches an existing core record value and unit
- `conflict_with_core`: the candidate targets the same identity but differs by value, unit, or condition
- `needs_human_review`: identity, evidence, or provenance is insufficient

No candidate is automatically approved. Every candidate has `approval_required: true`, `approved: false`, and `safe_to_apply_automatically: false`.

## Approval Queue

The approval queue is a review list only. Queue items use:

- `approve_add` for add candidates
- `review_duplicate` for exact duplicates
- `resolve_conflict` for core conflicts
- `human_review_required` for blocked candidates
- `addenda_merge_review` for future addenda review

The recommended action in PR32 is always `review_only`.

Candidate-normalized outputs are still not trusted core source data. Future promotion requires explicit approval through a later approval workflow.

## Addenda And Human Review

Role, pin, rail, and passive addenda remain unmerged. `ai-addenda-promotion-review.json` indexes them only when requested and marks `safe_to_merge_automatically: false`.

`ai-human-review-promotion-index.json` carries forward PR31 human-review records when requested and also indexes PR32 blocked candidates, conflicts, and approval queue references.

## Safety

PR32 never writes forbidden core output filenames and never modifies source AI candidate files or core artifacts. It does not invoke ingestion or calculation scripts and does not use network or live AI clients.

The status artifact always marks:

- `safe_to_apply_automatically: false`
- `safe_to_overwrite_core_artifacts: false`
- `safe_to_rerun_current_allocation_automatically: false`
- `safe_to_rerun_calculations_automatically: false`

## Future Work

Future PRs can add:

- explicit human approval queue editor
- promotion apply using approved-only inputs
- provenance carry-through improvements
- role/pin/rail addenda merge validator
- missing-data readiness rerun after approved promotion
- current allocation and calculations only after explicit promotion
