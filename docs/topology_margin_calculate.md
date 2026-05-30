# Topology Margin Calculate

`scripts/topology_margin_calculate.py` is the deterministic topology margin calculation stage. PR24 added fuse current margin, and PR25 adds connector pin current margin.

This stage does not calculate regulator margins, infer ratings, infer current, infer fuse or connector roles from refdes prefixes, create findings, create violations, emit severity, or make pass/fail or compliance judgments.

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

PR24 calculates `fuse_margin`. It requires both:

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

## Connector Pin Current Margin

PR25 adds `connector_pin_current_margin`. It requires both:

- a usable PR20 `allocation_records[]` row with explicit finite `allocated_current_a` and `branch_id`
- a usable PR23 `normalized_ratings[]` row that applies to `connector_pin_current_margin`

Accepted connector rating names are:

- `pin_current_max`
- `current_max`

The rating target must be explicit. A connector-pin rating normally requires `refdes` and `pin`, unless `branch_id` is explicit or the rating explicitly marks itself as connector-wide, global, or per-pin with fields such as:

- `is_per_pin`
- `per_pin`
- `applies_to_all_pins`
- `connector_wide`
- `rating_scope: pin | per_pin | connector | global`

PR25 does not expand one connector rating to all pins. A connector-wide or per-pin rating can calculate only when topology maps the rating to exactly one target branch/current path.

The rating and current must link deterministically. Accepted links are:

- rating `branch_id` exactly matches allocation `branch_id`
- rating `refdes` plus `pin` maps to exactly one branch through `branch_topology_enriched`
- `branch_topology_enriched` explicitly associates connector refdes/pin with the allocation branch
- `role_resolution` confirms connector role and maps the refdes/pin to exactly one branch/current path
- connector-wide/per-pin/global rating maps to exactly one connector branch for the relevant current

The connector formula is:

```text
connector_pin_margin_a = rating_current_a - allocated_current_a
connector_pin_utilization_ratio = allocated_current_a / rating_current_a
```

A negative `connector_pin_margin_a` is a numeric calculation result. PR25 does not turn it into a finding, violation, severity, pass/fail result, or compliance status.

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

`calculation_results[]` may contain:

- `fuse_margin`
- `connector_pin_current_margin`

The stage does not emit `regulator_load_margin` yet.

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

PR25 connector-pin margin also blocks when:

- connector pin rating is missing
- connector pin rating exists but is unusable
- connector rating value is zero or non-positive
- connector rating name is not accepted for PR25
- connector pin is missing and the rating is not explicitly per-pin, global, or connector-wide
- connector role is unknown where role confirmation is required
- current allocation records conflict

`unresolved_margin_inputs[]` is used when there is not enough deterministic linkage to form a target-specific blocked calculation.

When a missing data manifest is supplied, PR24 links blocked and unresolved records to matching `rating_missing`, `current_model_missing`, `branch_current_unknown`, `component_role_unknown`, `source_sink_not_resolved`, or `relationship_direction_unknown` items where possible. Missing rating manifest items are not stage failures.
