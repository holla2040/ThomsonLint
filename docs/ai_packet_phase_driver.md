# AI Packet Phase Driver

PR26 introduces the deterministic scaffold for packetized AI-assisted data
completion. It does not execute AI, extract real datasheet values, apply
patches, create findings, or mutate core topology artifacts.

## Why Packetization Exists

Topology and margin calculations now expose narrow missing-data blockers:
current models, component roles, power-path direction, and ratings. A single
board-wide AI prompt would mix unrelated components, hide evidence gaps, and
make validation difficult. The packet driver keeps each request small enough to
validate, checkpoint, accept, reject, retry, or send to human review.

## Phase -> Stage -> Packet -> Item

- Phase: one formal workflow phase, `Phase 12: AI Data Completion`.
- Stage: a bounded extraction family inside the phase.
- Packet: one target component/refdes/MPN and a small set of related missing
  data items.
- Item: one missing-data manifest row that explains the blocker and affected
  calculation families.

Supported PR26 stages:

- `12A` - Datasheet Role / Pin Extraction.
- `12B` - Datasheet Current Model Extraction.
- `12C` - Datasheet Rating Extraction.
- `12D` - Passive / Support Component Extraction.

Human-review packets use the same queue/status shape when the missing-data item
is unsupported, explicitly manual, or not appropriate for datasheet AI.

## Building Packets

`scripts/ai_packet_phase_build.py` consumes a missing-data manifest and writes a
packet queue under a phase output directory:

```bash
python scripts/ai_packet_phase_build.py \
  --project TestProject \
  --missing-data-manifest exports/TestProject-missing-data-manifest.json \
  --out-dir exports/TestProject/ai_packets/phase_12 \
  --phase-id 12 \
  --phase-name "AI Data Completion"
```

Optional context artifacts can add bounded BOM rows, schematic snippets, role
resolution rows, rail/branch links, datasheet references, and part-info index
rows. If optional artifacts are absent, packet building still succeeds and
records warnings. The missing-data manifest itself is required.

Routing is deterministic:

- Current-model blockers such as `branch_current_unknown` and
  `current_model_missing` route to `12B`.
- Component role, pin role, relationship direction, and source/sink blockers
  route to `12A` unless the item explicitly needs human review.
- Rating blockers such as `rating_missing`, `connector_pin_rating_unknown`,
  `fuse_rating_unknown`, and `regulator_rating_unknown` route to `12C`.
- Passive/support categories such as `esr_missing` and
  `ripple_current_missing` route to `12D`.
- Copper thickness, via geometry, stackup geometry, and unknown geometry data do
  not route to datasheet AI by default; those are deterministic or human-review
  inputs.
- Unknown future categories become human-review packets or skipped items with a
  warning.

## Evidence Policy

Datasheets are the primary evidence source for component facts: pin functions,
component current consumption, fuse hold/trip current, connector pin current,
regulator current limit, load-switch current rating, ferrite current rating,
and package current rating.

Datasheets should not be used as the source of board-specific facts such as
actual copper thickness, routed trace geometry, via geometry, measured current,
project-specific load allocation, or final voltage-drop/current-density/margin
results. Those values must come from deterministic design artifacts, explicit
engineering input, or later human-reviewed patch data.

## Output Directory Shape

```text
exports/TestProject/ai_packets/phase_12/
  packet_queue.json
  phase_status.json
  phase_12_summary.json
  packets/
    12A-001/
      request.json
      context.json
      prompt.md
      status.json
    12B-001/
      request.json
      context.json
      prompt.md
      status.json
```

Each packet contains:

- `request.json`: deterministic task metadata and required output schema name.
- `context.json`: bounded packet context only.
- `prompt.md`: guardrailed prompt text for a future AI runner.
- `status.json`: lifecycle state, attempts, and paths for future raw response,
  validated result, and patch artifacts.

## Lifecycle

The lifecycle enum is:

- `pending`
- `prompt_ready`
- `running`
- `raw_response_saved`
- `validation_passed`
- `validation_failed`
- `accepted`
- `rejected`
- `human_review_needed`
- `skipped`

PR26 only creates queued prompt-ready packets. It does not implement live
execution or response validation transitions.

## Guardrails

Generated prompts require:

- Do not guess.
- If the value is not present, return unknown.
- Every extracted numeric value must include unit and evidence.
- Do not produce findings.
- Do not produce pass/fail.
- Do not produce compliance judgments.
- Do not perform final calculations.
- Do not mutate topology artifacts.

The phase driver itself does not mutate core topology artifacts. Later PRs may
produce candidate patches, but those patches must pass deterministic validation
before any calculation artifacts are regenerated.

## Future PRs

- AI extraction result schema.
- AI extraction validator.
- AI patch apply.
- Phase driver live execution.
- Rerun readiness and calculations with AI-filled data.
