# Current Model Ingest

`scripts/current_model_ingest.py` is the PR19 deterministic current model
normalization stage. It consumes explicit current and rating data and emits a
stable normalized artifact for later current allocation and calculation stages.

This stage does not infer current, allocate current through topology, infer
ratings, create findings, or make pass/fail or compliance judgments.

## Inputs

Required:

- `--current-model`: explicit current model JSON
- `--out`: output path

Optional:

- `--missing-data-manifest`: PR16 missing data manifest for best-effort linkage
- `--branch-topology-enriched`: recorded as source context only
- `--rail-relationships`: recorded as source context only
- `--role-resolution`: recorded as source context only

If `--out` is omitted, the default output is
`exports/{project}-current-models-normalized.json`.

## Supported Current Model Shapes

PR19 supports explicit branch currents:

```json
{
  "project": "TestProject",
  "branch_currents": [
    {
      "branch_id": "br_v3p3_top_trace_group_000001",
      "branch_current_a": 0.25,
      "basis": "manual_design_requirement",
      "confidence": 1.0,
      "evidence_refs": ["manual_current_model:line1"]
    }
  ]
}
```

It also preserves explicit rail currents, component currents, and ratings. Rail
and component currents are not allocated to branches in PR19. Ratings are not
converted into margin calculations in PR19.

## Normalization

Current units normalize to amps only when the conversion is unambiguous:

- `A`
- `mA`
- `uA`
- `µA`

Fields ending in `_current_a`, such as `branch_current_a`, imply amps. Generic
`value` records must include a supported unit. Negative values, non-numeric
values, unsupported units, and records without targets are rejected into
`rejected_currents[]`.

Only normalized `branch_current` records are marked
`usable_for_calculation: true` for PR18 copper calculations. Explicit rail
currents, component currents, and ratings remain normalized source data for
later stages.

## Output

The artifact contains:

- `normalized_currents[]`
- `rejected_currents[]`
- `unresolved_references[]`
- source artifact provenance
- summary counts that match the emitted arrays
- `errors[]` and `warnings[]`

The output is valid JSON and is written without `NaN` or `Infinity`.

## Missing Data Manifest Linkage

When a PR16 missing data manifest is provided, PR19 links normalized records to
matching manifest items where deterministic identity matches are available:

- branch currents to `branch_current_unknown` items for the same `branch_id`
- rail currents to current-model missing groups for the same `rail_name`
- component currents to component or rail current-model missing items
- ratings to `rating_missing` items when present

Unresolved manifest linkage is a warning, not a failure. Missing current remains
missing; PR19 does not treat unknown current as zero.
