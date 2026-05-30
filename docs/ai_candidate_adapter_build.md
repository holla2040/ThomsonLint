# AI Candidate Adapter Build

PR30 builds deterministic adapter artifacts from PR29 AI candidate files. It does not call AI, execute packet prompts, validate raw AI responses, rebuild patch bundles, apply candidates to core artifacts, run ingestion automatically, rerun calculations, create findings, or make pass/fail or compliance judgments.

The adapter files are explicit manual inputs for later deterministic ingestion. They are written under an isolated output directory such as `exports/TestProject/ai_adapters/` and never overwrite normalized outputs such as `exports/TestProject-current-models-normalized.json`, `exports/TestProject-rating-models-normalized.json`, allocation artifacts, copper artifacts, or margin artifacts.

## Inputs

The builder reads the PR29 candidate directory:

```text
exports/TestProject/ai_candidates/
  ai-candidate-inputs.json
  ai-current-model-candidates.json
  ai-rating-model-candidates.json
  ai-role-resolution-addenda.json
  ai-pin-role-addenda.json
  ai-rail-relationship-hints.json
  ai-passive-support-candidates.json
  ai-human-review-candidates.json
  materialization-status.json
```

Only candidate records that are usable for ingestion, do not require human approval, are not conflicted, and include source/provenance/evidence are eligible for ingestion adapter records. Human-review candidates are excluded by default.

## Outputs

The output directory contains:

```text
exports/TestProject/ai_adapters/
  ai-adapter-manifest.json
  ai-current-model-ingest-input.json
  ai-rating-model-ingest-input.json
  ai-role-resolution-addenda-adapter.json
  ai-pin-role-addenda-adapter.json
  ai-rail-relationship-hints-adapter.json
  ai-passive-support-adapter.json
  ai-human-review-adapter.json
  adapter-status.json
```

`ai-current-model-ingest-input.json` uses the existing current model ingest raw input shape: `branch_currents`, `rail_currents`, and `component_currents`. It preserves candidate record IDs, patch IDs, packet IDs, source item IDs, accepted item IDs, missing-data item IDs, condition, basis, confidence, and evidence references.

`ai-rating-model-ingest-input.json` uses the existing current/rating normalization chain by writing `ratings` records that `current_model_ingest.py` can normalize and that `rating_model_ingest.py` can consume later. Connector-wide ratings are not expanded to pins. Regulator input/output side is not inferred. Voltage/passive-only data is not converted into current-margin ratings.

Role, pin, rail, and passive adapter files are reviewable addenda. They are not merged into role-resolution, rail-relationship, branch-topology, current, rating, copper, or margin artifacts in PR30.

## Human Review And Conflicts

Skipped, blocked, human-review, and conflicted candidates are routed to `ai-human-review-adapter.json` when appropriate. Conflicts are not resolved by this adapter and no winning value is chosen. Conflicted candidates remain non-usable for ingestion.

Human-review candidate records are only included when `--include-human-review` is passed, and they are still emitted as `usable_for_ingestion: false`.

## Provenance

Adapter files preserve the AI candidate provenance before deterministic ingestion:

- source candidate record ID
- source patch ID
- source packet ID
- source item ID
- source accepted item ID
- missing-data item IDs
- condition, basis, confidence
- evidence references

Existing ingestion scripts preserve the fields they already support, especially `basis`, `confidence`, string `evidence_refs`, and source artifact linkage. They do not yet consume every AI-specific provenance field as first-class normalized output. PR30 does not modify those scripts; deeper provenance carry-through is a PR31 follow-up.

## Guardrails

Adapter outputs must not contain findings, issue IDs, violations, severity, pass/fail fields, compliance judgments, final findings, mutation instructions, overwrite directives, deletes, or replacement operations.

The status file explicitly marks:

- candidate current/rating ingestion as safe to run manually
- core artifact overwrite as unsafe
- automatic calculation reruns as unsafe

## Future Work

Future PRs can add:

- candidate current/rating ingestion workflow wrapper
- human approval queue
- role/pin/rail addenda merge validator
- missing-data readiness rerun after approved candidate ingestion
- current allocation and calculations only after explicit candidate ingestion
