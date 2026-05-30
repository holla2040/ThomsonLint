# AI Candidate Ingestion Workflow

PR31 runs PR30 adapter-generated current and rating inputs through existing deterministic ingestion scripts into isolated AI candidate output files. It does not call AI, execute packet prompts, validate raw AI responses, rebuild patches, rebuild candidate materialization, rebuild adapter outputs, apply candidates to core artifacts, overwrite normalized outputs, run allocation, run copper/via/margin calculations, merge addenda, create findings, or make pass/fail or compliance judgments.

The workflow is intentionally a wrapper around existing local scripts:

- `current_model_ingest.py` normalizes `ai-current-model-ingest-input.json`
- `current_model_ingest.py` normalizes `ai-rating-model-ingest-input.json` as a rating-current intermediate
- `rating_model_ingest.py` consumes the rating-current intermediate

All outputs are written under an isolated directory such as `exports/TestProject/ai_ingested/`.

## Inputs

The wrapper reads:

```text
exports/TestProject/ai_adapters/
  ai-adapter-manifest.json
  adapter-status.json
  ai-current-model-ingest-input.json
  ai-rating-model-ingest-input.json
  ai-role-resolution-addenda-adapter.json
  ai-pin-role-addenda-adapter.json
  ai-rail-relationship-hints-adapter.json
  ai-passive-support-adapter.json
  ai-human-review-adapter.json
```

## Outputs

The workflow writes:

```text
exports/TestProject/ai_ingested/
  ai-candidate-ingestion-manifest.json
  ai-candidate-ingestion-status.json
  ai-current-models-normalized.json
  ai-rating-current-models-normalized.json
  ai-rating-models-normalized.json
  ai-addenda-index.json
  ai-human-review-index.json
  ai-candidate-ingestion-review.json
```

These are candidate outputs, not core outputs. The wrapper never writes `exports/TestProject-current-models-normalized.json`, `exports/TestProject-rating-models-normalized.json`, current allocation artifacts, copper calculation artifacts, or margin calculation artifacts.

## Execution Steps

The manifest records each subprocess step as a command array with input path, output path, return code, and truncated stdout/stderr previews. The wrapper does not use `shell=True`.

If the current candidate ingest step fails, the workflow records the failure and marks the workflow failed. If the rating-current ingest step fails, the dependent rating model ingest step is skipped. `--skip-current` skips only the current candidate ingest step. `--skip-rating` skips both rating path steps.

## Addenda And Human Review

Role, pin, rail, and passive adapter files are indexed in `ai-addenda-index.json`. They remain reviewable addenda and are not merged into role-resolution, rail-relationship, branch-topology, current, rating, copper, or margin artifacts.

Human-review adapter records and workflow failures/skips are indexed in `ai-human-review-index.json`.

## Safety

Before running subprocesses, the wrapper checks that:

- adapter inputs are inside the adapter directory
- candidate outputs are inside the output directory
- output filenames are not forbidden core artifact names
- script overrides exist and are local paths
- command execution uses argument arrays

The status artifact marks:

- `safe_to_use_as_candidate_inputs`
- `safe_to_overwrite_core_artifacts: false`
- `safe_to_rerun_current_allocation_automatically: false`
- `safe_to_rerun_calculations_automatically: false`

## Provenance

Existing ingestion scripts preserve their current supported fields, including basis, confidence, string evidence references, and source artifact linkage. They may not preserve every AI-specific field from PR30 adapter records, such as source candidate record ID, patch ID, packet ID, accepted item ID, or AI evidence objects.

PR31 does not modify ingestion scripts just to add provenance carry-through. Instead, `ai-candidate-ingestion-review.json` records known provenance gaps when adapter fields are not present in normalized candidate outputs.

## Manual Inspection

Review these files before any future promotion:

- `ai-current-models-normalized.json`
- `ai-rating-current-models-normalized.json`
- `ai-rating-models-normalized.json`
- `ai-addenda-index.json`
- `ai-human-review-index.json`
- `ai-candidate-ingestion-review.json`

Candidate-normalized outputs are still not trusted core source data. Promotion requires a later explicit approval workflow.

## Future Work

Future PRs can add:

- explicit provenance carry-through if needed
- human approval queue
- role/pin/rail addenda merge validator
- candidate-to-core promotion with explicit approval
- missing-data readiness rerun after approved candidate ingestion
- current allocation and calculations only after explicit promotion
