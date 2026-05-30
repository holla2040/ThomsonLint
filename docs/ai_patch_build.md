# AI Patch Build

PR28 builds deterministic patch candidate bundles from PR27 AI extraction
validation output. It does not call AI, execute packet prompts, validate raw AI
responses again, apply patches to core artifacts, rerun calculations, create
findings, create violations, emit severity, or make pass/fail/compliance
judgments.

## Inputs and Outputs

Input:

```text
exports/TestProject-ai-extraction-validation.json
```

Output:

```text
exports/TestProject-ai-patch-bundle.json
```

The patch bundle is a reviewable intermediate artifact and is not directly applied.
Accepted PR27 validation items are still candidate data; they are not
deterministic source data until a later patch apply step validates and
materializes them into explicit candidate input files.

## Patch Classes

Patch classes map accepted validation items to future ingestion stages:

- `current_model_patch`: candidate current fields for future current-model
  candidate input.
- `rating_model_patch`: candidate current-rating fields for future rating-model
  candidate input.
- `role_resolution_addendum`: candidate component/pass-through role data.
- `pin_role_addendum`: candidate pin role/direction data.
- `rail_relationship_hint`: candidate rail relationship hints.
- `passive_support_data_patch`: candidate capacitor/ferrite support data.
- `human_review_patch_candidate`: emitted only with `--include-human-review`.

Only `add_candidate` operations are supported in PR28. Destructive operations
such as update, delete, replace, merge, overwrite, or direct artifact mutation
are intentionally not implemented.

## Filtering

By default, the builder uses `accepted_items[]` only. It does not use
`rejected_items[]`, and it does not use `human_review_items[]` unless
`--include-human-review` is explicitly passed.

Items are skipped when they are unsupported, not usable for patching, missing
target identity, missing normalized numeric values or units, or missing source
evidence. Skipped items are recorded with stable reason codes.

## Provenance

Every patch preserves source linkage:

- packet ID
- source item ID
- accepted item ID or human-review item ID
- missing-data item IDs
- source file
- source page when present
- evidence quote or evidence reference
- confidence
- condition when present
- basis

This provenance is required so future patch apply can remain auditable and can
be reversed or rejected without guessing.

## Conflicts and Duplicates

Identical duplicate candidates are deduplicated and their source IDs are merged
onto one patch. Conflicting values, units, or conditions for the same target and
field are not resolved automatically. The affected patches are marked not usable
for ingestion and require human review.

Duplicate and conflicting values require human review because the builder must
not choose a winner among AI-derived candidates. That decision belongs in a
future human approval or deterministic apply stage.

## Future PRs

- AI patch apply into candidate current/rating input files.
- Human approval queue.
- Rerun current/rating ingestion with AI-filled candidate inputs.
- Rerun readiness and calculations after accepted patch application.
