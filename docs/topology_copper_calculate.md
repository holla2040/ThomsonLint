# Topology Copper Calculate

`scripts/topology_copper_calculate.py` is the PR18 deterministic copper calculation stage. It consumes topology geometry evidence, calculation readiness, and the missing data manifest, then emits schema-valid calculation results.

This stage does not infer current, infer ratings, create findings, or make pass/fail or compliance judgments.

## Inputs

Required:

- `--geometry-review`: PR10 topology geometry review artifact
- `--calculation-readiness`: PR15 calculation readiness inventory
- `--missing-data-manifest`: PR16 missing data manifest
- `--out`: output path

Optional:

- `--current-model`: explicit branch current fixture/artifact
- `--copper-resistivity-ohm-m`: explicit copper resistivity

If resistivity is not provided, the script uses `1.724e-8 ohm*m at 20C` and records that as an assumption in trace resistance results.

## Calculations

PR18 supports:

- `trace_cross_section`: width times copper thickness
- `trace_resistance`: resistivity times length divided by area
- `voltage_drop`: current times resistance
- `current_density`: current divided by area

Current-dependent calculations are blocked unless an explicit `branch_current_a` is present in `--current-model`.

## Blocked Results

Blocked calculations are emitted as valid `calculation_result_schema.json` records. A blocked result includes:

- `status: "blocked"`
- `missing_inputs[]`
- `blocked_by_manifest_items[]` when PR16 has matching blockers
- PR16 linkage fields such as `missing_data_group_ids`, `resolution_path`, `resolution_queue`, `blocked_by_categories`, and `blocked_by_calculations`

Unknown current, geometry, or thickness is never replaced with zero.

## Current Model Fixture

PR18 accepts explicit branch currents in this shape:

```json
{
  "project": "TestProject",
  "branch_currents": [
    {
      "branch_id": "br_v3p3_top_trace_group_000001",
      "branch_current_a": 0.25,
      "basis": "manual_test_fixture",
      "confidence": 1.0,
      "evidence_refs": []
    }
  ]
}
```

Only `branch_current_a` values keyed directly by `branch_id` are used.

## Output

The output artifact contains:

- `calculation_results[]`
- `blocked_calculations[]`
- summary counts by calculation family and missing-input category
- no findings and no engineering pass/fail judgments

PR19/PR20 can build on this by adding more calculation families and explicit current/rating ingestion, while preserving the blocked-result behavior.
