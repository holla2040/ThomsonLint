# Topology Margin Calculate

`scripts/topology_margin_calculate.py` is the deterministic PR24 margin calculation stage. PR24 is limited to fuse current margin.

This stage does not calculate regulator margins, connector pin margins, infer ratings, infer current, infer fuse roles from refdes prefixes, create findings, create violations, emit severity, or make pass/fail or compliance judgments.

## Inputs

Required:

- `--project`: project name
- `--current-allocation`: PR20 topology current allocation artifact
- `--rating-models-normalized`: PR23 normalized rating artifact
- `--out`: output path

Optional:

- `--missing-data-manifest`: PR16 blocker/linkage context
- `--role-resolution`: role context for deterministic fuse confirmation
- `--branch-topology-enriched`: branch context for deterministic rating-to-current linkage
- `--rail-relationships`: optional rail relationship context

The output path defaults to:

```text
exports/{project}-topology-margin-calculations.json
```

## Fuse Margin

PR24 calculates only `fuse_margin`. It requires both:

- a usable PR20 `allocation_records[]` row with explicit finite `allocated_current_a` and `branch_id`
- a usable PR23 `normalized_ratings[]` row that applies to `fuse_margin`

The rating and current must link deterministically. Accepted links are:

- rating `branch_id` exactly matches allocation `branch_id`
- rating `refdes` maps to exactly one branch through `branch_topology_enriched`
- `role_resolution` confirms a fuse/pass-through fuse and maps it to exactly one branch/current path
- topology artifacts explicitly associate the rating target with the allocation branch

If the link is absent or ambiguous, PR24 does not calculate and emits a blocked result or `unresolved_margin_inputs[]`.

## Accepted Rating Names

PR24 fuse margin accepts:

- `hold_current`
- `current_max`
- `continuous_current_max`
- `package_current_limit`
- `thermal_current_limit`

`trip_current` is not used as a continuous-current margin basis in PR24. It produces a blocked result or unresolved input with `trip_current_not_continuous_margin_basis`.

## Formula

```text
fuse_margin_a = rating_current_a - allocated_current_a
fuse_utilization_ratio = allocated_current_a / rating_current_a
```

A negative `fuse_margin_a` is a numeric calculation result. PR24 does not turn it into a finding, violation, severity, pass/fail result, or compliance status.

## Output

Top-level fields:

- `project`
- `generated_at_utc`
- `execution_pass`
- `topology_margin_calculation_pass`
- `schema_version`
- `source_artifacts`
- `calculation_results[]`
- `blocked_calculations[]`
- `unresolved_margin_inputs[]`
- `summary`
- `errors[]`
- `warnings[]`

`calculation_results[]` contains only records with `calculation_family: "fuse_margin"` in PR24.

Calculated results preserve:

- allocation ID
- rating ID
- branch ID
- refdes and pin when available
- source artifacts for PR20 current allocation and PR23 ratings
- evidence refs from current and rating sources
- confidence from the weaker explicit source when both are available

## Blocked And Unresolved Inputs

Blocked calculations are first-class outputs. PR24 blocks when:

- allocated current is missing
- fuse rating is missing
- rating exists but is unusable
- rating value is zero or non-positive
- rating target cannot be linked to exactly one branch/current path
- rating name is unsupported for PR24 fuse margin
- rating is `trip_current`
- current allocation records conflict
- target role is unknown where role confirmation is required

`unresolved_margin_inputs[]` is used when there is not enough deterministic linkage to form a target-specific blocked calculation.

When a missing data manifest is supplied, PR24 links blocked and unresolved records to matching `rating_missing`, `current_model_missing`, `branch_current_unknown`, `component_role_unknown`, `source_sink_not_resolved`, or `relationship_direction_unknown` items where possible. Missing rating manifest items are not stage failures.
