# AI Candidate Materialization

PR29 materializes isolated candidate input files from PR28 AI patch bundles. It
does not call AI, execute packets, validate raw AI responses, rebuild patch
bundles, apply patches to core artifacts, run current/rating ingestion, run
current allocation, run copper/via/margin calculations, create findings, create
violations, emit severity, or make pass/fail/compliance judgments.

## Safety Boundary

Candidate files are reviewable inputs under a dedicated directory:

```text
exports/TestProject/ai_candidates/
```

They are not directly applied to normalized outputs and they do not overwrite:

- `exports/<project>-current-models-normalized.json`
- `exports/<project>-rating-models-normalized.json`
- `exports/<project>-topology-current-allocation.json`
- `exports/<project>-topology-copper-calculations.json`
- `exports/<project>-topology-margin-calculations.json`

Current and rating candidates are not automatically trusted. They remain
AI-derived candidate records until a future deterministic ingestion adapter and
approval flow accepts them.

## Emitted Files

The materializer writes a stable directory shape:

```text
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

`ai-candidate-inputs.json` is the manifest. `materialization-status.json`
records that candidate ingestion is safe to feed later tooling, but core
artifact overwrite is not safe.

## Candidate Families

- Current model candidates are future raw input candidates for current model
  ingestion.
- Rating model candidates are future raw input candidates for rating model
  ingestion.
- Role resolution addenda are candidate role facts, not merged role-resolution
  artifacts.
- Pin role addenda are candidate pin facts, not merged topology.
- Rail relationship hints are candidate hints. Datasheets can identify pin
  functions, but board-specific rail names still require schematic/topology
  mapping.
- Passive support candidates preserve support data such as ESR, impedance,
  ripple current, and voltage rating without making DFM, thermal, or pass/fail
  judgments.

## Conflict Handling

Conflicted patch IDs referenced by PR28 `conflicts[]` are blocked by default and
listed in `blocked_by_conflict[]`. The materializer never chooses a winning
value from conflicting candidates. Conflicts require human review before any
candidate can become ingestion input.

With `--allow-conflicted`, conflicted patches can be written only as non-usable
human-review candidates with `usable_for_ingestion=false` and conflict IDs
preserved.

## Human Review

Human-review patch candidates are excluded by default. With
`--include-human-review`, they are materialized into
`ai-human-review-candidates.json` with `usable_for_ingestion=false`.

## Future PRs

- Candidate current/rating ingestion adapters.
- Human approval queue.
- Role/pin/rail addenda merge validator.
- Rerun missing-data readiness after candidate application.
- Rerun current allocation and calculations only after explicit candidate
  ingestion.
