# Topology Calculation Schemas

PR 17 defines stable JSON contracts for the future deterministic topology calculation engine. It does not execute calculations, infer current, create findings, or make pass/fail engineering judgments.

## Purpose

The schemas describe two artifact types:

- `schemas/calculation_input_schema.json`: one prepared calculation input for a target branch, rail, component, pin, relationship, net, or project.
- `schemas/calculation_result_schema.json`: one calculation result, including valid `blocked` results when required inputs are missing.

These contracts connect the topology artifacts from earlier stages to later calculation execution while preserving explicit missing-data semantics.

## Calculation Families

The schemas currently cover:

- `trace_cross_section`
- `trace_resistance`
- `voltage_drop`
- `current_density`
- `via_current_density`
- `fuse_margin`
- `regulator_load_margin`
- `connector_pin_current_margin`

Each calculation references target identity, source artifacts, evidence refs, units, assumptions, confidence, and missing inputs. The schemas intentionally do not encode engineering acceptance thresholds.

## Artifact Flow

PR 18 should consume:

- topology role resolution
- rail relationships
- branch topology enrichment
- calculation readiness inventory
- missing data manifest
- topology geometry review
- part info and stackup evidence where applicable

PR 18 can then emit calculation inputs and results that conform to the PR 17 schemas. When required values are missing, the result should be `status: "blocked"` with `missing_inputs[]` and `blocked_by_manifest_items[]`.

## Blocked Calculations

Blocked calculations are first-class valid results. Examples:

- `voltage_drop`, `current_density`, and `via_current_density` are blocked when `branch_current_a` is missing.
- `fuse_margin` is blocked when fuse current rating is missing.
- `regulator_load_margin` is blocked when load current is missing.
- `connector_pin_current_margin` is blocked when per-pin current rating is missing.

Unknown values must remain missing. They must not be guessed, silently defaulted, or treated as zero.

## Examples

Representative examples live in `examples/calculation_examples/`:

- ready inputs for trace cross-section and trace resistance
- calculated results for trace cross-section and trace resistance
- blocked voltage-drop/current-density/via-current-density results for missing current
- blocked fuse/regulator/connector margin results for missing ratings or load current

These examples are intentionally small and evidence-backed. They demonstrate contracts only; they are not findings and do not imply pass/fail conclusions.

## PR 18 Guidance

PR 18 should use these schemas to build a deterministic calculation preparation/execution stage. It should:

- validate inputs/results against these schemas
- emit `blocked` results when missing data from the manifest prevents execution
- only calculate when all required inputs are explicit and evidence-backed
- avoid inferring current, ratings, or thermal assumptions from missing data
