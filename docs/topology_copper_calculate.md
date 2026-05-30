# Topology Copper Calculate

`scripts/topology_copper_calculate.py` is the deterministic copper calculation stage. It consumes topology geometry evidence, calculation readiness, the missing data manifest, and optional explicit current sources, then emits schema-valid calculation results.

This stage does not infer current, infer ratings, create findings, or make pass/fail or compliance judgments.

## Inputs

Required:

- `--geometry-review`: PR10 topology geometry review artifact
- `--calculation-readiness`: PR15 calculation readiness inventory
- `--missing-data-manifest`: PR16 missing data manifest
- `--out`: output path

Optional:

- `--current-model`: explicit branch current fixture/artifact
- `--current-allocation`: PR20 topology current allocation artifact
- `--copper-resistivity-ohm-m`: explicit copper resistivity

If resistivity is not provided, the script uses `1.724e-8 ohm*m at 20C` and records that as an assumption in trace resistance results.

## Calculations

PR18 supports:

- `trace_cross_section`: width times copper thickness
- `trace_resistance`: resistivity times length divided by area
- `voltage_drop`: current times resistance
- `current_density`: current divided by area
- `via_current_density`: explicit branch current divided by explicit via barrel area

Current-dependent calculations are blocked unless an explicit branch current is available from one of these sources:

1. `--current-allocation`, using usable PR20 `allocation_records[]`
2. legacy `--current-model`, using explicit `branch_current_a`, when no allocation artifact is supplied

When both are supplied, PR20 current allocation is canonical. Matching legacy current-model values are preserved as corroborating provenance. Materially different values block current-dependent calculations with `current_source_conflict` rather than being merged or guessed.

## Blocked Results

Blocked calculations are emitted as valid `calculation_result_schema.json` records. A blocked result includes:

- `status: "blocked"`
- `missing_inputs[]`
- `blocked_by_manifest_items[]` when PR16 has matching blockers
- PR16 linkage fields such as `missing_data_group_ids`, `resolution_path`, `resolution_queue`, `blocked_by_categories`, and `blocked_by_calculations`

Unknown current, geometry, or thickness is never replaced with zero.

When a PR20 allocation artifact is supplied and a branch has no usable allocated current, blocked voltage-drop/current-density results carry unresolved allocation linkage where available, including `missing_data_manifest_item_ids`, `missing_data_group_ids`, `resolution_path`, `resolution_queue`, `blocked_by_categories`, and `blocked_by_calculations`.

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

## Current Allocation Artifact

PR21 accepts PR20 allocation records in this shape:

```json
{
  "allocation_records": [
    {
      "allocation_id": "alloc_deterministic_branch_sum_br_v3p3",
      "allocation_type": "deterministic_branch_sum",
      "branch_id": "br_v3p3_top_trace_group_000001",
      "allocated_current_a": 0.25,
      "usable_for_calculation": true,
      "source_current_record_ids": ["cur_u12_v3p3_max"],
      "evidence_refs": ["datasheet:U12:p14"],
      "assumptions": []
    }
  ],
  "unresolved_allocations": []
}
```

Accepted allocation types are:

- `explicit_branch_current`
- `deterministic_branch_sum`
- `deterministic_passthrough_current`
- `deterministic_single_path_rail_current`

Records are ignored for calculation if they lack `branch_id`, have `usable_for_calculation` other than `true`, omit `allocated_current_a`, or contain a non-finite current. `unresolved_allocations[]` and `passthrough_records[]` are not used as current sources; unresolved records are used only for blocked-result provenance.

## Via Current Density

PR22 adds `via_current_density` for via or via-cluster branches. A record is considered via-related only when the artifact explicitly marks it as a via/via cluster, includes via geometry fields, or has deterministic via/drill wording in the branch id. The calculation does not infer current, via count, diameter, or plating thickness.

Supported explicit via geometry fields include:

- `via_count`
- `hole_count`
- `finished_hole_diameter_mm`
- `drill_diameter_mm`
- `plated_hole_diameter_mm`
- `via_diameter_mm`
- `via_barrel_plating_thickness_mm`
- `plating_thickness_mm`
- `copper_thickness_mm`
- `copper_thickness_um`
- `barrel_length_mm`
- `board_thickness_mm`

The required inputs are explicit branch current, via count, finished-hole or drill diameter, and barrel plating thickness. A single-via default is only used when the artifact explicitly represents a single via, such as `branch_type: "via"` or `geometry_type: "via"`.

The formula is:

```text
area_per_via_mm2 = pi * finished_hole_diameter_mm * plating_thickness_mm
total_barrel_area_mm2 = area_per_via_mm2 * via_count
via_current_density_a_per_mm2 = allocated_current_a / total_barrel_area_mm2
```

For explicit clusters, current is evaluated against total parallel barrel area. The result records `current_per_via_a` as an intermediate when `via_count > 1`, but it does not make an equal-sharing safety conclusion.

Blocked via-current-density results list missing inputs such as `allocated_current_a`, `branch_current_a`, `via_count`, `finished_hole_diameter_mm`, or `via_barrel_plating_thickness_mm`, and preserve PR16/PR20 linkage where available.

## Output

The output artifact contains:

- `calculation_results[]`
- `blocked_calculations[]`
- summary counts by calculation family and missing-input category
- current source summary counts for PR20 allocation usage, legacy current-model usage, current-source conflicts, and unresolved allocation blockers
- via current density summary counts for calculated, blocked, missing geometry, missing plating, and missing via count cases
- no findings and no engineering pass/fail judgments

Later PRs can add more calculation families or workflow integration while preserving the blocked-result behavior.
