# Topology Current Allocate

`scripts/topology_current_allocate.py` is the PR20 deterministic current
allocation stage. It consumes PR19 normalized explicit current records plus
topology context and emits branch-level current allocations only where the
mapping is deterministic.

This stage does not infer unknown load currents, treat missing current as zero,
divide rail current across branches, infer ratings, create findings, or make
pass/fail or compliance judgments.

## Inputs

Required:

- `--current-models-normalized`: PR19 normalized current model artifact
- `--branch-topology-enriched`: branch context with rail/source/sink/pass-through data
- `--rail-relationships`: rail relationship context
- `--role-resolution`: component role context
- `--missing-data-manifest`: PR16 missing data manifest
- `--out`: output path

Optional:

- `--calculation-readiness`: recorded as source context when supplied

If `--out` is omitted, the default output is
`exports/{project}-topology-current-allocation.json`.

## Deterministic Allocation Cases

PR20 supports these allocation types:

- `explicit_branch_current`: copies a PR19 `branch_current` record directly to
  the matching branch when it is marked usable for calculation.
- `deterministic_single_path_rail_current`: assigns an explicit rail current
  only when exactly one branch exists for that rail and no source/sink or
  relationship blockers are present.
- `deterministic_branch_sum`: sums explicit component current records that map
  to exactly one sink branch on the same rail.
- `deterministic_passthrough_current`: copies known current through a resolved
  pass-through component only when there is one input branch, one output branch,
  known direction, resolved source/sink context, and known input current.

Rail current is never divided across multiple branches. Component current is not
allocated without a deterministic component-to-branch mapping.

## Unresolved Allocations

Ambiguous or incomplete cases are emitted in `unresolved_allocations[]` instead
of being guessed. Common reason codes include:

- `missing_current_model`
- `ambiguous_branch_path`
- `source_sink_not_resolved`
- `relationship_direction_unknown`
- `shared_plane_current_unknown`
- `component_to_branch_mapping_unknown`
- `rail_to_branch_mapping_unknown`

Unresolved allocations do not fail the stage. The stage fails only for malformed
or missing required inputs, or internal errors.

## Manifest Linkage

When PR16 manifest items match by branch, rail, component, category, or blocker
calculation, PR20 preserves:

- `missing_data_manifest_item_ids`
- `missing_data_group_ids`
- `resolution_path`
- `resolution_queue`
- `blocked_by_categories`
- `blocked_by_calculations`

This preserves blocker context for later calculation readiness and copper
calculation stages.

## Output

The artifact contains:

- `allocation_records[]`
- `unresolved_allocations[]`
- `passthrough_records[]`
- source artifact provenance
- internally consistent summary counts
- `errors[]` and `warnings[]`

The output is valid JSON and is written without `NaN` or `Infinity`.
