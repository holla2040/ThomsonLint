#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


PHASES = {
    1: "Ingest ThomsonLint Workflow",
    2: "Inspect Inputs and Datasheets",
    3: "Setup and Tool Preflight",
    4: "Run Integrated Converter",
    5: "Inspect Findings Framework",
    6: "Full BOM Datasheet Retrieval",


    7: "Enforce Image Review Gate",
    8: "Review Schematic Evidence FULL",
    9: "Full Board/Layout JSON Evaluation",
    10: "Review Stackup and Manufacturing Evidence FULL",
    11: "Review BOM and Component Evidence FULL",
    12: "Review Image Evidence FULL",
    13: "Review Datasheet Evidence FULL",
    14: "Cross-Source Consistency Review",
    15: "Pre-Findings Gate Check",
    16: "Candidate Finding Development",
    17: "Write Findings JSON",
    18: "Validate and Repair Findings",
    19: "Generate Report",
    20: "Final Summary",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--project", default="example")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.phase not in PHASES:
        raise SystemExit(f"Invalid phase: {args.phase}")

    phase_name = PHASES[args.phase]
    project = args.project

    prompt = f"""You are working in the ThomsonLint repository.

Execute exactly one phase only.

Active execution plan:
./.agents_tmp/PLAN.md

Current phase:
Phase {args.phase} — {phase_name}

Rules:
- Execute only Phase {args.phase}.
- Do not execute earlier phases.
- Do not execute later phases.
- Do not prepare future phases.
- Do not create findings unless this is Phase 17.
- Do not validate findings unless this is Phase 18.
- Do not generate a report unless this is Phase 19.
- Do not write final summary unless this is Phase 20.
- Do not change PLAN.md.
- Do not change .agents_tmp/PLAN.md.
- Do not modify git state.
- Do not commit.
- Do not push.

Required:
1. Read only the Phase {args.phase} section from .agents_tmp/PLAN.md plus any referenced gate language needed for this phase.
2. Perform only the tasks required by Phase {args.phase}.
3. Produce Phase {args.phase}'s required artifact(s).
4. Validate Phase {args.phase}'s required artifact(s).
5. Append exactly one row for phase_number={args.phase} to exports/{project}-phase-checkpoints.jsonl.
6. Set phase_passed=true only if the phase-local gate passed.
7. Stop after Phase {args.phase}. Do not continue.

Checkpoint row requirements:
- phase_number
- phase_name
- started_at_utc
- completed_at_utc
- required_artifacts
- artifacts_verified
- validation_artifacts
- validation_passed
- blockers
- phase_passed
- failed_phase_number
- repair_required

If the phase-local gate fails:
- repair only this phase's artifact/work product, or report BLOCKED
- do not advance to the next phase
- do not defer the failure to a later phase
- checkpoint phase_passed=false and repair_required=true if blocked

Project prefix:
{project}

Important:
The driver script, not you, decides whether to proceed to the next phase.

Phase 6 SearXNG rule:
If this is Phase 6, use the configured searxng MCP server for datasheet discovery when available.
SearXNG search results and URLs are discovery only.
A BOM row may be marked status=found only when the datasheet PDF is downloaded and saved locally under exports/datasheets/.
If SearXNG returns candidate URLs but no local file is saved, status must be ambiguous or missing, not found.
Record candidate_urls and failed_candidate_urls in the datasheet manifest.
"""


    # BEGIN STRICT PHASE 6 DATASHEET PROMPT
    if args.phase == 6:
        prompt += f"""

Phase 6 specific instructions:

Use scripts/datasheet_helper.py for all Phase 6 BOM datasheet retrieval mechanics.

Required commands:
1. python3 scripts/datasheet_helper.py bom-parse
2. python3 scripts/datasheet_helper.py check-existing
3. python3 scripts/datasheet_helper.py run-phase6
4. python3 scripts/datasheet_helper.py validate-manifest
5. python3 scripts/audit_phase6_datasheets.py
6. python3 scripts/audit_phase.py --project {project} --phase 6 --exports exports

Important checkpoint override for Phase 6:
- scripts/datasheet_helper.py run-phase6 writes the Phase 6 checkpoint.
- Do not append a second Phase 6 checkpoint row manually.
- After run-phase6, validate the existing checkpoint only.
- There must be exactly one phase_number=6 row in exports/{project}-phase-checkpoints.jsonl.

Phase 6 pass policy:
- Phase 6 does not require every datasheet to be found.
- Phase 6 passes when every raw BOM row is represented exactly once in the manifest.
- Every concrete MPN row must be processed by the helper.
- found/local rows must point to real local PDF files and pass PDF validation.
- ambiguous/missing rows are allowed as report-only unresolved datasheet limitations after bounded helper discovery.
- status=error rows remain blocking.
- URL-only evidence is not found.
- SearXNG results, snippets, distributor metadata, and candidate URLs are discovery only.

Required artifacts:
- exports/datasheets/datasheet_manifest.jsonl
- exports/datasheets/datasheet_manifest_validation.json
- .agents_tmp/datasheet_manual_downloads.json

Allowed statuses:
- local
- found
- ambiguous
- missing
- error
- not_applicable_generic

Never use:
- found/url_only
- download_unavailable
- missing_generic

Stop after Phase 6.
Do not execute Phase 7.
Do not create findings.
Do not generate a report.
Do not modify PLAN.md.
Do not modify .agents_tmp/PLAN.md.
Do not modify git state.
Do not commit.
Do not push.
"""
    # END STRICT PHASE 6 DATASHEET PROMPT

    # BEGIN STRICT PHASE 8 SCHEMATIC PROMPT
    if args.phase == 8:
        prompt += f"""

Phase 8 specific instructions:

Review schematic evidence using:
- exports/{project}-thomson-export-sch.json
- schematic PNG images only as qualitative visual context if needed

Critical schema rule:
- The schematic JSON stores net connectivity in nets[].nodes, not nets[].members.
- Each node entry may contain refdes, pin_number, and pin_name.
- Use node_count and len(net["nodes"]) for connectivity counts.
- Do not conclude that schematic nets lack connectivity merely because nets[].members is absent.
- If members is absent but nodes is populated, connectivity is present.
- If both nodes and members are absent/empty, then record a connectivity extraction limitation.

Required Phase 8 artifact:
- exports/{project}-schematic-evidence-review.json

The artifact must include:
- source_schematic_json
- schematic_json_loaded
- component_count
- net_count
- total_node_count
- nets_with_nodes_count
- nets_without_nodes_count
- power_nets
- ground_nets
- clock_nets
- connector_components
- connector_nets_or_interface_nets
- differential_or_paired_net_candidates
- unusual_connection_notes
- limitations
- evidence_citations
- gate.overall_pass

Required review coverage:
- components
- nets
- power nets
- external interfaces
- connector nets
- unusual connections
- limitations

Evidence requirements:
- Cite file/path/field/value where practical.
- For net connectivity, cite nets[].name, nets[].node_count, and nets[].nodes[].
- Do not make quantitative claims from PNG-only evidence.
- Do not write findings in Phase 8.

Validation requirements:
- JSON artifact exists and parses.
- schematic_json_loaded=true.
- component_count > 0.
- net_count > 0.
- total_node_count must be computed from nets[].nodes.
- gate.overall_pass=true only if required sections exist and citations/limitations are populated.
"""
    # END STRICT PHASE 8 SCHEMATIC PROMPT

    # BEGIN STRICT PHASE 12 IMAGE VISION PROMPT
    if args.phase == 12:
        prompt += f"""

Phase 12 specific instructions:

This phase has two distinct jobs:
1. Confirm rendered PNGs exist/open and are usable visual context.
2. Run actual multimodal vision review through scripts/vision_image_review.py.

Required image sources:
- exports/{project}-img-sch-p*.png
- exports/{project}-img-layout-p*.png

Required commands:
1. python3 scripts/vision_image_review.py --project {project} --out exports/{project}-image-vision-review.json
2. Validate exports/{project}-image-vision-review.json
3. Ensure exports/{project}-image-evidence-inventory.json still exists or recreate basic render inventory if missing.

Required artifacts:
- exports/{project}-image-evidence-inventory.json
- exports/{project}-image-vision-review.json

Vision review rules:
- Use scripts/vision_image_review.py for actual image-to-model review.
- Do not claim vision review was performed from ls/file/identify/checksum/Pillow metadata alone.
- Do not mark vision_review_performed=true unless the helper successfully sent PNG image content to a multimodal endpoint.
- If the endpoint/model rejects image input, mark Phase 12 blocked.
- Electrical calculations may be suggested from visibly readable schematic values.
- Physical/layout measurements from raster pixels are forbidden unless a calibrated scale/reference exists.
- Do not derive trace width, spacing, clearance, creepage, pad size, hole size, or board dimensions from uncalibrated PNG pixels.

Required pass criteria:
- exports/{project}-image-vision-review.json exists and parses.
- vision_review_performed=true.
- metadata_only_review=false.
- actual_multimodal_endpoint_used=true.
- reviewed_image_count == expected_image_count.
- per_page_vision_observations has one entry per image.
- confirmation_no_pixel_quantitative_claims=true.
- overall_pass=true.

Do not create findings in Phase 12.
Do not execute Phase 13.
"""
    # END STRICT PHASE 12 IMAGE VISION PROMPT



    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
