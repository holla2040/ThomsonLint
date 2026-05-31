# AI Approval Queue Editor v0 (PR33)

This script creates and validates human approval decision artifacts for the ThomsonLint AI candidate promotion workflow. It does not call AI, apply approvals, overwrite normalized outputs, run ingestion/allocation/calculations, merge addenda, create findings, or make pass/fail or compliance judgments.

## Scope

PR33 produces two artifact types:

1. **Decision artifact** (`ai-approval-decisions.json`) — records human decisions (pending/approved/rejected/needs_info) for each approval queue item from PR32.
2. **Validation artifact** (`ai-approval-decision-validation.json`) — validates a decision artifact against schema rules and PR32 source data.

Approval decisions are inputs for a future apply stage only. They do not trigger any promotion or mutation until a later PR implements that stage.

## Safety Guarantees

- `safe_to_apply` is always `false` in all PR33 artifacts.
- `safe_for_future_apply_stage` is always `false` in the validation artifact.
- PR33 does not apply approvals or modify any core artifacts.
- No apply instructions are emitted.
- No findings, violations, severity levels, pass/fail judgments, or compliance judgments are created.
- Core normalized outputs (`*-current-models-normalized.json`, `*-rating-models-normalized.json`) are never written or modified.
- Topology/copper/margin artifacts are never written or modified.
- No ingestion scripts (`current_model_ingest.py`, `rating_model_ingest.py`) are invoked.
- No allocation or calculation scripts (`topology_current_allocate.py`, `topology_copper_calculate.py`, `topology_margin_calculate.py`) are invoked.
- No network calls, no AI client imports (openai, anthropic, google.generativeai, requests, httpx).

## Inputs

PR33 reads PR32 artifacts from the promotion directory:

```text
exports/{project}/ai_promotion/
  ai-candidate-promotion-plan.json   (optional — used for candidate validation)
  ai-candidate-approval-queue.json   (required — source of approval items)
  ai-candidate-promotion-status.json (optional — used in strict mode)
```

## Outputs

By default, PR33 writes to the promotion directory:

```text
exports/{project}/ai_promotion/
  ai-approval-decisions.json              (decision artifact)
  ai-approval-decision-validation.json    (validation artifact)
```

Custom output paths can be specified with `--out` and `--validate-out`.

## Usage: Create Template

Create a pending decision for every approval queue item:

```bash
python scripts/ai_approval_decision_edit.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --decision-template
```

This produces `ai-approval-decisions.json` with all decisions set to `"pending"`, `safe_to_apply: false`, and no reviewer or notes.

## Usage: Approve a Single Item

Approve one approval item (requires `--note`):

```bash
python scripts/ai_approval_decision_edit.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --approve aq_001 \
  --note "verified against datasheet page 92" \
  --reviewer "engineer-1"
```

The decision is set to `"approved"` with the current UTC timestamp. `safe_to_apply` remains `false`. This decision is valid for a future apply stage only.

## Usage: Reject a Single Item

Reject one approval item (requires `--note` or `--reason-code`):

```bash
python scripts/ai_approval_decision_edit.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --reject aq_002 \
  --note "value conflicts with core model" \
  --reason-code rejected_conflicts_with_core
```

The decision is set to `"rejected"` with the current UTC timestamp. `safe_to_apply` remains `false`.

## Usage: Needs Info

Mark one approval item as needing more information (requires `--note`):

```bash
python scripts/ai_approval_decision_edit.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --needs-info aq_003 \
  --note "missing datasheet page 45"
```

The decision is set to `"needs_info"` with the current UTC timestamp. `safe_to_apply` remains `false`.

## Usage: Validate Decisions

Validate an existing decision artifact without mutating it:

```bash
python scripts/ai_approval_decision_edit.py \
  --project TestProject \
  --promotion-dir exports/TestProject/ai_promotion \
  --decisions exports/TestProject/ai_promotion/ai-approval-decisions.json \
  --validate-only \
  --out exports/TestProject/ai_promotion/ai-approval-decision-validation.json
```

This produces `ai-approval-decision-validation.json` with validated decisions, invalid decisions (with reasons), and missing decisions (queue items without corresponding decisions).

## Decision Rules

| Decision | Note Required | Reason Code Required |
|----------|--------------|---------------------|
| `pending` | No | No |
| `approved` | Yes | No |
| `rejected` | Yes or reason code | Yes or note |
| `needs_info` | Yes | No |

### Allowed Reason Codes

- `approved_evidence_sufficient`
- `approved_matches_datasheet`
- `approved_engineer_verified`
- `rejected_insufficient_evidence`
- `rejected_conflicts_with_core`
- `rejected_wrong_target`
- `rejected_wrong_unit`
- `rejected_wrong_condition`
- `rejected_duplicate_not_needed`
- `needs_info_missing_datasheet_page`
- `needs_info_ambiguous_condition`
- `needs_info_unclear_target`
- `needs_info_requires_engineer_review`

### Validation Rules

1. Every `approval_item_id` must exist in the PR32 approval queue.
2. Every `promotion_candidate_id` (if not null) must match a candidate in the PR32 plan or queue.
3. Duplicate decisions for the same `approval_item_id` are invalid.
4. Approved decisions require non-empty `approval_note`.
5. Rejected decisions require non-empty `approval_note` or `reason_code`.
6. Needs_info decisions require non-empty `approval_note`.
7. Pending decisions may have empty note (valid).
8. If `reviewed_at_utc` is present, it must be valid ISO-8601 format.
9. In strict mode, if PR32 promotion status is `"failed"`, all decisions are marked invalid.

## Decision Artifact Shape

```json
{
  "project": "TestProject",
  "generated_at_utc": "...",
  "schema_version": "ai_approval_decisions_v1",
  "source_artifacts": [...],
  "source_promotion_plan": "...",
  "source_approval_queue": "...",
  "decision_set_status": "draft|validated|invalid",
  "decisions": [...],
  "summary": {
    "approval_queue_count": 0,
    "decision_count": 0,
    "pending_count": 0,
    "approved_count": 0,
    "rejected_count": 0,
    "needs_info_count": 0,
    "invalid_decision_count": 0,
    "missing_decision_count": 0,
    "safe_to_apply_count": 0,
    "error_count": 0,
    "warning_count": 0
  },
  "errors": [],
  "warnings": []
}
```

## Validation Artifact Shape

```json
{
  "project": "TestProject",
  "generated_at_utc": "...",
  "schema_version": "ai_approval_decision_validation_v1",
  "source_artifacts": [...],
  "source_decisions": "...",
  "validation_pass": true,
  "validated_decisions": [...],
  "invalid_decisions": [...],
  "missing_decisions": [...],
  "summary": {
    "decision_count": 0,
    "valid_decision_count": 0,
    "invalid_decision_count": 0,
    "pending_decision_count": 0,
    "missing_decision_count": 0,
    "approved_count": 0,
    "rejected_count": 0,
    "needs_info_count": 0,
    "safe_for_future_apply_count": 0,
    "error_count": 0,
    "warning_count": 0
  },
  "errors": [],
  "warnings": []
}
```

## Future Work

Future PRs can add:

- Approved-only promotion apply dry-run
- Promotion apply to candidate core-input files
- Promotion apply to actual core inputs with explicit flag
- Provenance carry-through improvements
- Role/pin/rail addenda merge validator
- Rerun missing-data readiness after approved promotion
- Rerun allocation/calculations only after explicit promotion
