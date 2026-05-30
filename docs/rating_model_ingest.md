# Rating Model Ingest

`scripts/rating_model_ingest.py` is the deterministic PR23 rating normalization stage. It consumes PR19 `current-models-normalized` output and emits a standalone rating artifact for later margin calculations.

This stage does not calculate fuse, regulator, or connector margins. It does not infer ratings, infer current, create findings, or make pass/fail or compliance judgments.

## Inputs

Required:

- `--project`: project name
- `--current-models-normalized`: PR19 normalized current/rating artifact
- `--out`: output path

Optional:

- `--missing-data-manifest`: PR16 missing data manifest for best-effort linkage
- `--role-resolution`: role context for deterministic component role confirmation
- `--rail-relationships`: rail relationship context for future deterministic enrichment
- `--branch-topology-enriched`: branch context for future deterministic enrichment

Only `normalized_currents[]` records with `record_type: "rating"` are normalized. Current records are ignored except for summary context.

If a PR19 rating record omits `rating_name` but its `source_artifacts[]` points to a local explicit current model source record, PR23 may recover the original rating name from that source artifact deterministically. If the source artifact is absent or unavailable, the rating is rejected as missing `rating_name`.

## Supported Targets

Supported rating target types are:

- `fuse`
- `fuse_pin`
- `connector`
- `connector_pin`
- `regulator`
- `regulator_output`
- `regulator_input`
- `load_switch`
- `pass_through_component`
- `component`
- `rail`
- `branch`

The stage does not infer component role from a refdes prefix. A generic `component` rating remains a component rating unless `role_resolution` explicitly confirms a fuse, regulator, connector, load-switch, or pass-through role.

## Supported Rating Names

Canonical rating names are:

- `current_max`
- `pin_current_max`
- `output_current_max`
- `input_current_max`
- `continuous_current_max`
- `hold_current`
- `trip_current`
- `thermal_current_limit`
- `package_current_limit`

Aliases are normalized deterministically:

- `connector_pin_current_max` -> `pin_current_max`
- `fuse_hold_current` -> `hold_current`
- `fuse_trip_current` -> `trip_current`
- `regulator_output_current` -> `output_current_max`
- `regulator_current_limit` -> `current_max`

## Units

Current ratings support `A`, `mA`, `uA`, and `µA`. Values are normalized to:

- `value_a`
- `unit: "A"`

The artifact preserves `original_value`, `original_unit`, and `original_rating_name`.

## Output

The output artifact is:

```text
exports/{project}-rating-models-normalized.json
```

Top-level fields:

- `project`
- `generated_at_utc`
- `execution_pass`
- `rating_model_ingest_pass`
- `schema_version`
- `source_artifacts`
- `normalized_ratings[]`
- `rejected_ratings[]`
- `unresolved_rating_links[]`
- `summary`
- `errors[]`
- `warnings[]`

Each normalized rating records explicit target identity, canonical rating name, normalized value, provenance, evidence refs, source artifacts, manifest linkage, margin-family applicability, and `usable_for_margin_calculation`.

## Rejection Behavior

Ratings are rejected when explicit data is missing or unusable:

- missing target
- missing rating name
- missing value
- missing or unsupported unit
- non-finite value
- negative rating
- ambiguous target
- unsupported rating name
- unsupported record type or target type

Rejected ratings do not fail the stage unless the input artifact itself is malformed.

## Linkage Behavior

When a missing data manifest is supplied, PR23 links ratings to matching `rating_missing`, `current_model_missing`, `component_role_unknown`, `source_sink_not_resolved`, or `relationship_direction_unknown` items. Missing links are represented in `unresolved_rating_links[]` and warnings; they are not stage failures.

Optional topology artifacts are used only for deterministic confirmation. The stage does not expand connector pin ratings to all pins, infer regulator output rails, infer ratings from component names, or compare ratings against load current.
