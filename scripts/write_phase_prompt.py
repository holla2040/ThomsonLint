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
    11: "Review DFM and Manufacturing Specifications",
    12: "Review BOM and Component Evidence FULL",
    13: "Review Image Evidence FULL",
    14: "Review Datasheet Evidence FULL",
    15: "Review Aerospace and Process Metadata",
    16: "Cross-Source Consistency Review",
    17: "Pre-Findings Gate Check",
    18: "Candidate Finding Development",
    19: "Write Findings JSON",
    20: "Validate and Repair Findings",
    21: "Generate Report",
    22: "Final Summary",
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
- Do not create findings unless this is Phase 19.
- Do not validate findings unless this is Phase 20.
- Do not generate a report unless this is Phase 21.
- Do not write final summary unless this is Phase 22.
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
- repair_required (set to true when phase_passed=false)

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

    # BEGIN STRICT PHASE 1 INGEST WORKFLOW PROMPT
    if args.phase == 1:
        prompt += f"""

Phase 1 specific instructions:

This phase maps OPENHANDS_REVIEW.md workflows to concrete actions and confirms phase order.

Required actions:
1. Read OPENHANDS_REVIEW.md (or .agents_tmp/OPENHANDS_REVIEW.md if present)
2. Read docs/REVIEWER_INSTRUCTIONS.md (if present)
3. Confirm the workflow-to-phase mapping matches the 1→22 linear sequence
4. Verify no lettered side phases exist

No external artifact is required. The checkpoint row itself is the deliverable.

Required pass criteria:
- Confirmed that workflows 1-22 exist in order
- Confirmed no alternate or side-phase sequences
- phase_passed=true in checkpoint row

Do not produce a separate JSON artifact. The checkpoint row is the artifact.
"""
    # END STRICT PHASE 1 INGEST WORKFLOW PROMPT

    # BEGIN STRICT PHASE 2 INSPECT INPUTS PROMPT
    if args.phase == 2:
        prompt += f"""

Phase 2 specific instructions:

This phase inspects the input/ and datasheets/ directories and records missing evidence.

Required actions:
1. Confirm input/ exists
2. List all files under input/
3. Verify at least one design input exists (IPC-2581 XML, schematic netlist, BOM CSV, PDF)
4. Check datasheets/ for local datasheets
5. Check for stackup inputs: input/stackup.csv, input/stackup.json, *.tcfx files
6. Check for aerospace/process inputs: fab work orders, conformal coating specs, vibration profiles, chassis drawings

No external artifact is required. The checkpoint row itself is the deliverable.

Required pass criteria:
- input/ exists
- At least one design input file exists
- Inventory mentally noted (or can be logged to stdout)
- Explicitly record presence/absence of aerospace/process documentation (for Phase 15)
- phase_passed=true in checkpoint row

Do not produce a separate JSON artifact. The checkpoint row is the artifact.
Do not delete input files.
Do not modify git state.
"""
    # END STRICT PHASE 2 INSPECT INPUTS PROMPT

    # BEGIN STRICT PHASE 3 TOOL PREFLIGHT PROMPT
    if args.phase == 3:
        prompt += f"""

Phase 3 specific instructions:

This phase ensures required local tools are available before converter execution.

Required tool availability checks:
1. which python3
2. which pdftoppm
3. which pdfinfo

If pdftoppm or pdfinfo missing, attempt installation:
```
apt-get update && apt-get install -y poppler-utils
```
Or with sudo if required:
```
sudo apt-get update && sudo apt-get install -y poppler-utils
```

After installation, verify:
```
which pdftoppm
which pdfinfo
pdftoppm -v
pdfinfo -v
```

REQUIRED ARTIFACT: exports/tool-preflight-status.json

Required fields in tool-preflight-status.json:
- python3_available (bool)
- pdftoppm_available (bool)
- pdfinfo_available (bool)
- install_attempted (bool)
- install_command (string or null)
- install_succeeded (bool or null)
- pdfs_present (bool)
- fallback_used (bool)
- user_approved_fallback (bool)
- approval_source (string or null)
- json_only_review_approved (bool)
- json_only_approval_source (string or null)
- overall_pass (bool — TOP LEVEL)

IMPORTANT PASS LOGIC:
When PDFs are present, overall_pass=true ONLY if:
  (pdftoppm_available=true AND pdfinfo_available=true)
  OR (fallback_used=true AND user_approved_fallback=true)
  OR (json_only_review_approved=true)

When no PDFs are present, overall_pass=true if python3_available=true.

Do NOT treat image-render fallback approval as JSON-only approval.
If PDFs are present and tools are missing with no approved fallback, overall_pass=false.

ARTIFACT SCHEMA RULES — IMPORTANT:
- This artifact uses `overall_pass` at the TOP LEVEL (not nested under gate).
- The auditor checks the top-level `overall_pass` field.
"""
    # END STRICT PHASE 3 TOOL PREFLIGHT PROMPT

    # BEGIN STRICT PHASE 4 RUN CONVERTER PROMPT
    if args.phase == 4:
        prompt += f"""

Phase 4 specific instructions:

This phase runs the integrated converter to generate review artifacts.

REQUIRED COMMAND:
```
python3 tools/run_converter_pipeline.py input --project-name {project} --clean
```

After running the converter, verify:
1. exports/ directory exists
2. JSON exports load successfully:
   - exports/{project}-bom.json
   - exports/{project}-thomson-export-sch.json
   - exports/{project}-thomson-export-brd.json
   - exports/{project}-thomson-export-stack.json
3. PNG renders exist (when PDFs were provided)
4. Inspect conversion reports if present:
   - exports/{project}-conversion-report.json
   - exports/{project}-conversion-report.md

Record converter warnings as evidence-quality notes, NOT as automatic design findings.

REQUIRED ARTIFACTS:
- exports/{project}-bom.json
- exports/{project}-thomson-export-sch.json
- exports/{project}-thomson-export-brd.json
- exports/{project}-thomson-export-stack.json

Required pass criteria:
- Converter ran without fatal error
- All four JSON exports exist and parse successfully
- phase_passed=true in checkpoint row

Do not write findings in Phase 4.
Do not modify git state.
"""
    # END STRICT PHASE 4 RUN CONVERTER PROMPT

    # BEGIN STRICT PHASE 5 INSPECT FINDINGS FRAMEWORK PROMPT
    if args.phase == 5:
        prompt += f"""

Phase 5 specific instructions:

This phase inspects the ThomsonLint framework files to understand valid finding structure.

Required files to inspect:
1. tests/findings_schema.json — JSON schema for findings
2. tests/sample_findings.json — worked example of valid findings
3. ontology/ontology.json — rule definitions with id, domain, severity, etc.
4. examples/examples.json — worked examples mapped to ontology rules
5. tools/validate_findings.py — findings validator logic
6. tools/gen_report.py — report generator logic

From inspection, determine:
- Valid top-level findings JSON structure
- Required issue fields
- Valid severity values (from ontology)
- Valid domains (from ontology)
- Valid rule IDs (from ontology)
- Expected evidence[] row format
- verified_checks format
- cross_checks format

No external artifact is required. The checkpoint row itself is the deliverable.

Required pass criteria:
- All framework files listed above have been read/inspected
- Schema constraints are understood
- Allowed ontology values documented (mentally or logged)
- phase_passed=true in checkpoint row

Do not produce a separate JSON artifact. The checkpoint row is the artifact.
Do not modify framework files.
Do not write findings in Phase 5.
"""
    # END STRICT PHASE 5 INSPECT FINDINGS FRAMEWORK PROMPT

    # BEGIN STRICT PHASE 7 IMAGE GATE PROMPT
    if args.phase == 7:
        prompt += f"""

Phase 7 specific instructions:

This phase enforces PNG evidence readiness for deep review runs.

Required checks:
1. Check if schematic PDFs were present — if so, schematic PNGs must exist
2. Check if layout/Gerber/PCB PDFs were present — if so, layout PNGs must exist
3. Read json_only_review_approved from exports/tool-preflight-status.json (do not re-request approval)

REQUIRED ARTIFACT: exports/{project}-image-evidence-inventory.json

Required fields in image-evidence-inventory.json:
- pdf_sources (list of PDF filenames or empty list)
- conversion_tool (string: "pdftoppm", "pymupdf", "none", etc.)
- fallback_used (bool)
- user_approved_fallback (bool)
- total_pages_expected (int)
- total_pages_rendered (int)
- output_files (list of PNG paths)
- schematic_pngs (list)
- layout_pngs (list)
- pages_inspected (int)
- page_roles_or_labels_if_identifiable (list or null)
- visual_context_notes (string or list)
- limitations (list)
- confirmation_no_pixel_quantitative_claims (bool — must be true)
- overall_pass (bool — TOP LEVEL)

ARTIFACT SCHEMA RULES — IMPORTANT:
- This artifact uses `overall_pass` at the TOP LEVEL (not nested under gate).
- The auditor checks the top-level `overall_pass` field.
- There is NO separate -validation.json file for Phase 7.

PASS LOGIC:
If PDFs are present:
  overall_pass=true ONLY when total_pages_rendered == total_pages_expected
  (or an explicit limitation is recorded with approved JSON-only fallback)

If no PDFs are present:
  overall_pass=true (no image gate needed)

If PDFs are present but PNGs cannot be produced:
  overall_pass=true ONLY if json_only_review_approved=true in tool-preflight-status.json

Do not derive measurements from pixels.
Do not write findings in Phase 7.
"""
    # END STRICT PHASE 7 IMAGE GATE PROMPT
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

REQUIRED TOOL: scripts/schematic_helpers.py

Run the following command FIRST before any manual JSON inspection:
```
python3 scripts/schematic_helpers.py exports/{project}-thomson-export-sch.json --analyze-all --json
```

This performs deterministic graph-based analysis for rules that require multi-hop connectivity
tracing (impossible for an LLM to perform reliably on large netlists). It produces LLM-optimized
JSON with precise paths: refdes, pin_number, pin_name, net_name, rule_id.

Rules covered by this command:
- SCH_NET_002: Single-pin nets
- SCH_UART_001: UART TX/RX crossover
- SCH_FET_001: FET gate termination
- SCH_FLOAT_001: Floating inputs
- MS_I2C_001: I2C pull-ups
- SCH_I2C_002: I2C address conflicts
- SCH_PULLUP_001: Op-amp tie-off

Individual check flags (optional when targeted inspection is needed):
- --single-pins (SCH_NET_002 only)
- --uart-check (SCH_UART_001 only)
- --fet-check (SCH_FET_001 only)
- --floating-check (SCH_FLOAT_001 only)
- --i2c-check (MS_I2C_001, SCH_I2C_002)
- --opamp-check (SCH_PULLUP_001 only)

Record the schematic_helpers.py output in the schematic evidence inventory.

Critical schema rule:
- The schematic JSON stores net connectivity in nets[].nodes, not nets[].members.
- Each node entry may contain refdes, pin_number, and pin_name.
- Use node_count and len(net["nodes"]) for connectivity counts.
- Do not conclude that schematic nets lack connectivity merely because nets[].members is absent.
- If members is absent but nodes is populated, connectivity is present.
- If both nodes and members are absent/empty, then record a connectivity extraction limitation.

Required Phase 8 artifacts:
- exports/{project}-schematic-evidence-inventory.json
- exports/{project}-schematic-evidence-inventory-validation.json

The schematic evidence inventory must include:
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
- schematic_helpers_analysis (REQUIRED — record output from schematic_helpers.py)
- limitations
- evidence_citations
- gate (object with gate.overall_pass — this is the pass field INSIDE the inventory artifact)

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

ARTIFACT SCHEMA RULES — IMPORTANT:
- The inventory artifact (exports/{project}-schematic-evidence-inventory.json) contains a nested
  `gate` object. Set gate.overall_pass=true in the inventory when inventory checks pass.
- The validation artifact (exports/{project}-schematic-evidence-inventory-validation.json) must
  have `overall_pass` at the TOP LEVEL (NOT nested under gate). The auditor checks
  the top-level `overall_pass` field in the validation artifact, not gate.overall_pass.

Validation artifact (schematic-evidence-inventory-validation.json) required fields:
- schematic_json_loaded (bool)
- component_count (int > 0)
- net_count (int > 0)
- schematic_helpers_executed (bool)
- overall_pass (bool — TOP LEVEL, not nested; true only when all above checks pass)
"""
    # END STRICT PHASE 8 SCHEMATIC PROMPT

    # BEGIN STRICT PHASE 9 BOARD EVALUATION PROMPT
    if args.phase == 9:
        prompt += f"""

Phase 9 specific instructions:

Perform full board/layout JSON evaluation of:
- exports/{project}-thomson-export-brd.json

Full logical content evaluation is REQUIRED. Summary-only extraction is FORBIDDEN.
If the board JSON is too large to open directly, use chunked or targeted programmatic inspection.

REQUIRED TOOL: scripts/geometry_helpers.py

Run ALL of the following DFM checks (REQUIRED, regardless of stackup availability):

```
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --check-annular-ring --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --detect-acid-traps --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --board-edge-clearance --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --copper-balance --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --npth --npth-radius 4.0 --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --diff-pairs --json
```

Run ALL of the following physical-math verification commands (REQUIRED if stackup data is available):

```
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --verify-impedance --target-ohms 100 --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --verify-trace-temp --current-a 3.0 --max-temp-rise 10.0 --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --check-voltage-clearance --json
```

If stackup data is unavailable, mark impedance/thermal checks as [STACKUP_DATA_REQUIRED] in the
board evidence inventory, but STILL run all DFM checks above.

Utility commands (run as needed for specific nets):
```
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --net <NET_NAME> --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --clearance NET_A NET_B
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --ampacity VCC 2.0
```

Rule-to-tool mapping (which check covers which rule):
- DFM_VIA_001/003/004 (annular rings): --check-annular-ring
- DFM_ACID_001 (acid traps): --detect-acid-traps
- DFM_EDGE_001/PANEL_001 (edge clearance, GND=25mil, PWR/SIG=50mil): --board-edge-clearance
- DFM_COPPER_001 (copper balance): --copper-balance
- Appendix K.6 (NPTH keepout): --npth --npth-radius 4.0
- HS_DIFF_001 to HS_DIFF_006 (diff pairs): --diff-pairs
- HS_MAT_001 (impedance): --verify-impedance (stackup required)
- PWR_TRACE_002 (thermal/ampacity): --verify-trace-temp (stackup required)
- DFM_TRACE_004 (voltage spacing): --check-voltage-clearance (schematic voltages required)

Record all geometry_helpers.py output in the geometry_helper_analysis section of the board
evidence inventory. This section is REQUIRED in the artifact.

Required Phase 9 artifacts:
- exports/{project}-board-evidence-inventory.json
- exports/{project}-board-evidence-inventory-validation.json

The board evidence inventory must include the REQUIRED field:
geometry_helper_analysis (containing: differential_pairs, npth_clearance, trace_widths,
annular_ring, acid_traps, board_edge_clearance, copper_balance, and physical_math_verification).

Validation requirements:
- Both artifacts exist and parse.
- board_json_loaded=true.
- geometry_helpers_executed=true.
- dfm_geometry_checks_executed=true.
- physical_math_checks_attempted_or_marked_unavailable=true.
- overall_pass=true.

Do not write findings in Phase 9.
Board JSON is geometry/routing evidence, not true DRC. Do not claim impedance or thermal
verification without physical-math tool evidence and stackup data.
"""
    # END STRICT PHASE 9 BOARD EVALUATION PROMPT

    # BEGIN STRICT PHASE 10 STACKUP PROMPT
    if args.phase == 10:
        prompt += f"""

Phase 10 specific instructions:

Review stackup facts and manufacturing evidence. This phase focuses on stackup material data,
impedance evidence, and layer structure. DFM geometry checks are covered in Phase 9 and Phase 11.

Candidate stackup sources to inspect (use all that are available):
- exports/{project}-thomson-export-stack.json (auto-generated by converter)
- input/stackup.csv
- input/stackup.json
- input/*.tcfx (Cadence Allegro/OrCAD technology files, auto-merged by converter)
- fabrication drawing PDFs

TCFX Auto-Merge Note:
The thomson_bundle_converter.py automatically searches for .tcfx files and merges stackup data
during conversion. Check exports/*-thomson-export-stack.json for tcfx_merge metadata.

Manual TCFX merge (only needed to update an existing stackup JSON):
```
python3 converter/ipc2581_to_json/parse_tcfx_stackup.py input/<project>.tcfx exports/{project}-thomson-export-stack.json
```

REQUIRED TOOL: scripts/stackup_helpers.py (when input stackup CSV or JSON exists)

Run ALL validation checks:
```
python3 scripts/stackup_helpers.py input/stackup.csv --validate-stackup --json
```

Or for JSON input:
```
python3 scripts/stackup_helpers.py input/stackup.json --validate-stackup --json
```

Individual check flags (optional when targeted inspection is needed):
```
python3 scripts/stackup_helpers.py input/stackup.csv --check-thickness --json         # DFM_STACKUP_001
python3 scripts/stackup_helpers.py input/stackup.csv --check-symmetry --json          # DFM_STACKUP_002
python3 scripts/stackup_helpers.py input/stackup.csv --check-reference-planes --json  # HS_MAT_001
```

Rule-to-tool mapping:
- DFM_STACKUP_001 (board thickness): --check-thickness
- DFM_STACKUP_002 (dielectric symmetry): --check-symmetry
- HS_MAT_001 (reference planes): --check-reference-planes

If no input stackup file exists:
- Mark stackup as missing evidence.
- Report stackup completeness status as one of: complete_explicit, partial_explicit, layer_order_only, missing.
- Do not claim impedance verification, stackup verification, or manufacturing signoff without
  explicit stackup/material/impedance evidence.

Required Phase 10 artifacts:
- exports/{project}-stackup-evidence-review.json
- exports/{project}-stackup-evidence-review-validation.json

Validation requirements:
- Both artifacts exist and parse.
- stackup source explicitly identified.
- stackup_helpers.py executed and results recorded (when input exists).
- overall_pass=true.

Do not write findings in Phase 10.
"""
    # END STRICT PHASE 10 STACKUP PROMPT

    # BEGIN STRICT PHASE 11 DFM PROMPT
    if args.phase == 11:
        prompt += f"""

Phase 11 specific instructions:

Review design-for-manufacturing compliance. DFM geometry checks should have already been run in
Phase 9. If they were NOT run in Phase 9, run ALL of them now.

Verify Phase 9 geometry checks are complete. If any are missing, run:
```
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --check-annular-ring --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --detect-acid-traps --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --board-edge-clearance --json
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --copper-balance --json
```

Physical-math check (REQUIRED when stackup data is available):
```
python3 scripts/geometry_helpers.py exports/{project}-thomson-export-brd.json --check-voltage-clearance --json
```
This verifies IPC-2221B electrical clearance for high-voltage and power nets.

Rule-to-tool mapping:
- DFM_VIA_001/003/004 (annular rings): --check-annular-ring
- DFM_ACID_001 (acid traps): --detect-acid-traps
- DFM_EDGE_001/PANEL_001 (edge clearance): --board-edge-clearance
- DFM_COPPER_001 (copper balance): --copper-balance
- DFM_TRACE_004 (voltage spacing): --check-voltage-clearance

Required Phase 11 artifacts:
- exports/{project}-dfm-evidence-inventory.json
- exports/{project}-dfm-evidence-inventory-validation.json

The DFM evidence inventory must include:
geometry_helpers_dfm_results (containing: annular_ring, acid_traps, board_edge_clearance,
copper_balance check outputs).

Validation requirements:
- Both artifacts exist and parse.
- geometry_helpers_dfm_executed=true.
- overall_pass=true.

Do not write findings in Phase 11.
"""
    # END STRICT PHASE 11 DFM PROMPT

    # BEGIN STRICT PHASE 12 BOM PROMPT
    if args.phase == 12:
        prompt += f"""

Phase 12 specific instructions:

Review BOM quality, component metadata completeness, and identify components requiring datasheet
verification.

REQUIRED TOOL: scripts/bom_helpers.py

Run ALL component checks:
```
python3 scripts/bom_helpers.py exports/{project}-bom.json --audit-components --json
```

This performs deterministic component-level analysis. Output is LLM-optimized JSON with precise
paths: refdes, mpn, description, rule_id.

Checks performed by --audit-components:
- Heavy components >3g (AERO_VIB_001)
- Capacitor dielectrics Y5V/Z5U vs X5R/X7R (COMP_CAP_001)
- Incomplete MPNs (DFM_BOM_001)
- Lead finish assessment (AERO_SLD_001)
- Polarized capacitors without polarity markers (SCH_POL_001)

Individual check flags (optional when targeted inspection is needed):
```
python3 scripts/bom_helpers.py exports/{project}-bom.json --heavy-threshold 3.0 --json   # AERO_VIB_001
python3 scripts/bom_helpers.py exports/{project}-bom.json --check-dielectrics --json     # COMP_CAP_001
python3 scripts/bom_helpers.py exports/{project}-bom.json --audit-mpns --json            # DFM_BOM_001
python3 scripts/bom_helpers.py exports/{project}-bom.json --check-lead-finish --json     # AERO_SLD_001
python3 scripts/bom_helpers.py exports/{project}-bom.json --polarized --json             # SCH_POL_001
```

Rule-to-tool mapping:
- AERO_VIB_001 (heavy components): --heavy-threshold
- COMP_CAP_001 (dielectrics): --check-dielectrics
- DFM_BOM_001 (MPN completeness): --audit-mpns
- AERO_SLD_001 (lead finish): --check-lead-finish
- SCH_POL_001 (polarized caps): --polarized

Record bom_helpers.py output in the bom evidence inventory.

Required Phase 12 artifacts:
- exports/{project}-bom-evidence-inventory.json
- exports/{project}-bom-evidence-inventory-validation.json

The BOM evidence inventory must include:
bom_helpers_analysis (containing: heavy_components, capacitor_dielectrics, mpn_audit,
lead_finish, polarized_check results).

Validation requirements:
- Both artifacts exist and parse.
- bom_loaded=true.
- bom_helpers_executed=true.
- overall_pass=true.

Do not write findings in Phase 12.
Do not infer electrical limits from package or vendor names alone.
"""
    # END STRICT PHASE 12 BOM PROMPT

    # BEGIN STRICT PHASE 13 IMAGE VISION PROMPT
    if args.phase == 13:
        prompt += f"""

Phase 13 specific instructions:

This phase has two distinct jobs:
1. Confirm rendered PNGs exist/open and are usable visual context.
2. Run actual multimodal vision review through scripts/vision_image_review.py.

Required image sources:
- exports/{project}-img-sch-p*.png
- exports/{project}-img-layout-p*.png

Required commands:
1. python3 scripts/vision_image_review.py --project {project} --out exports/{project}-image-evidence-review.json
2. Validate exports/{project}-image-evidence-review.json
3. Ensure exports/{project}-image-evidence-inventory.json still exists or recreate basic render inventory if missing.

Required artifacts:
- exports/{project}-image-evidence-inventory.json
- exports/{project}-image-evidence-review.json
- exports/{project}-image-evidence-review-validation.json

ARTIFACT SCHEMA RULES — IMPORTANT:
- exports/{project}-image-evidence-inventory.json was created in Phase 7.
  Ensure it still exists. If missing, recreate a basic render inventory.
- exports/{project}-image-evidence-review.json is the main vision review output.
  It contains the detailed per-page observations. Set overall_pass=true inside
  this artifact when review criteria are met.
- exports/{project}-image-evidence-review-validation.json is a SEPARATE validation
  artifact. It must have `overall_pass` at the TOP LEVEL (not nested). The auditor
  checks top-level overall_pass in the validation artifact.
- Use scripts/vision_image_review.py for actual image-to-model review.
- Do not claim vision review was performed from ls/file/identify/checksum/Pillow metadata alone.
- Do not mark vision_review_performed=true unless the helper successfully sent PNG image content to a multimodal endpoint.
- If the endpoint/model rejects image input, mark Phase 12 blocked.
- Electrical calculations may be suggested from visibly readable schematic values.
- Physical/layout measurements from raster pixels are forbidden unless a calibrated scale/reference exists.
- Do not derive trace width, spacing, clearance, creepage, pad size, hole size, or board dimensions from uncalibrated PNG pixels.

Required pass criteria for image-evidence-review.json:
- vision_review_performed=true
- metadata_only_review=false
- actual_multimodal_endpoint_used=true
- reviewed_image_count == expected_image_count
- per_page_vision_observations has one entry per image
- confirmation_no_pixel_quantitative_claims=true
- overall_pass=true (set inside the review artifact)

Validation artifact (image-evidence-review-validation.json) required fields:
- phase
- overall_pass (bool — TOP LEVEL, not nested; true only when all review pass criteria above are met)

Do not create findings in Phase 13.
Do not execute Phase 14.
"""
    # END STRICT PHASE 13 IMAGE VISION PROMPT

    # BEGIN STRICT PHASE 14 DATASHEET REVIEW PROMPT
    if args.phase == 14:
        prompt += f"""

Phase 14 specific instructions:

This phase is a datasheet evidence review phase only.
It is not a findings phase.

Hard prohibition:
- Do not create findings.
- Do not create candidate findings.
- Do not create issue objects.
- Do not create severity-ranked findings.
- Do not create rule-mapped findings.
- Do not use a top-level key named findings.
- Do not assign severity.
- Do not promote missing/ambiguous datasheets to final issue language.
- Phase 19 is the only phase allowed to write findings JSON.

Required artifact:
- exports/{project}-datasheet-evidence-review.json

The artifact must include these top-level keys:
- phase
- phase_name
- reviewed_at_utc
- manifest_path
- manifest_validation_path
- summary
- local_datasheet_review
- reused_datasheet_records
- ambiguous_datasheet_records
- missing_datasheet_records
- datasheet_evidence_gaps
- limitations
- validation
- gate

Allowed terminology:
- evidence review
- evidence check
- evidence gap
- ambiguous record
- missing record
- limitation
- review note
- follow-up required

Forbidden terminology:
- finding
- issue
- severity
- rule_id
- final finding
- candidate finding

Required summary fields:
- total_bom_rows
- datasheet_applicable_count
- not_applicable_generic_count
- status_found
- status_ambiguous
- status_missing
- status_not_applicable_generic
- found_with_existing_local_file_count
- unique_local_file_count
- reused_datasheet_file_count
- ambiguous_record_count
- missing_record_count

Required evidence rules:
- Only cite local saved PDFs under exports/datasheets/.
- Do not cite SearXNG snippets.
- Do not cite candidate URL text as datasheet evidence.
- Candidate URLs may be recorded only as discovery metadata for ambiguous/missing records.
- Local saved PDFs may be cited by filename/path and manifest row.
- Ambiguous/missing records must be explicit, but must not be written as findings.

Required Phase 14 artifacts:
- exports/{project}-datasheet-evidence-review.json
- exports/{project}-datasheet-evidence-review-validation.json

ARTIFACT SCHEMA RULES — IMPORTANT:
- The review artifact (exports/{project}-datasheet-evidence-review.json) contains a nested `gate`
  object. Set gate.overall_pass=true inside the review artifact when review checks pass.
- The validation artifact (exports/{project}-datasheet-evidence-review-validation.json) must have
  `overall_pass` at the TOP LEVEL (NOT nested under gate). The auditor checks the top-level
  `overall_pass` field in the validation artifact, not gate.overall_pass.

Required validation:
- Review artifact JSON parses.
- Top-level key findings is absent.
- No object uses severity.
- No object uses rule_id.
- No final issue language is present.
- All status=found cited datasheets have local_file_exists=true.
- All cited datasheet paths are under exports/datasheets/.
- Ambiguous and missing records are present and counted.
- gate.overall_pass=true inside the review artifact only when the above checks pass.

Validation artifact (datasheet-evidence-review-validation.json) required fields:
- phase
- overall_pass (bool — TOP LEVEL, not nested; true only when all review checks pass)

Checkpoint validation text must not say "findings documented".
Use "datasheet evidence records documented" instead.

Do not execute Phase 15.
"""
    # END STRICT PHASE 14 DATASHEET REVIEW PROMPT

    # BEGIN STRICT PHASE 15 AEROSPACE PROMPT
    if args.phase == 15:
        prompt += f"""

Phase 15 specific instructions:

This phase inspects aerospace certification and process metadata.
Document absences as missing evidence or [UNVERIFIABLE].

This is NOT a findings phase. Phase 19 is the only phase allowed to write findings JSON.

Accepted aerospace/process inputs (check input/ for these):
- Fab work order or board-build specification (solder alloy, IPC class)
- Conformal coating specification document (masking requirements)
- Environmental or vibration profile document (vibration profile type)
- Chassis-mounting drawing (chassis-bond point identification)
- Assembly work instructions

REQUIRED ARTIFACT: exports/{project}-aerospace-evidence-inventory.json

Required fields in aerospace-evidence-inventory.json:
- phase
- phase_name
- project
- timestamp
- fab_work_order_present (bool)
- solder_alloy_specified (string or null)
- ipc_class_specified (string or null)
- lead_finish_qualifications_reviewed (bool)
- conformal_coating_spec_present (bool)
- masking_requirements_documented (bool)
- environmental_profile_present (bool)
- vibration_profile_type (string or null)
- component_mass_records_reviewed (bool)
- mass_over_threshold_count (int)
- chassis_mounting_drawing_present (bool)
- chassis_bond_point_count (int or null)
- aero_evidence_gaps (list — each gap documented)
- aero_limitations (list)
- unverifiable_rules (list — must include rules that require physical testing)
- gate (object with gate.overall_pass)

Rules to assess (Cluster 5 / KB Appendix K):
- HS_MAT_001: Stackup dielectric definition
- AERO_SLD_001: Solder alloy spec, IPC class, lead finish
- AERO_TERM_001: Conformal coat masking requirements
- AERO_VIB_001: Component mass > 3g vs vibration profile

Rules to flag [UNVERIFIABLE] "Skipped: Requires Physical Prototype/Testing":
- THM_DISS_001, THM_RISE_001, THM_HEAT_001, THM_COOL_001
- DFT_BUILD_001, DFT_MEAS_001, DFT_PROD_001

Logs/DRC verification (if available):
- DFT_DRC_001, DFT_DRC_002, DFT_CONN_001

REQUIRED VALIDATION ARTIFACT: exports/{project}-aerospace-evidence-inventory-validation.json

Required fields in validation artifact:
- phase
- inventory_exists (bool)
- required_fields_present (bool)
- aero_categories_assessed_or_marked_missing (bool)
- overall_pass (bool — TOP LEVEL, not nested)

ARTIFACT SCHEMA RULES — IMPORTANT:
- The main artifact (aerospace-evidence-inventory.json) contains a nested `gate` object.
  Set gate.overall_pass=true when all categories are assessed or marked as missing evidence.
- The validation artifact must have `overall_pass` at the TOP LEVEL. The auditor checks
  the top-level `overall_pass` field in the validation artifact.

PASS LOGIC:
Absence of aerospace documentation is NOT a workflow failure.
overall_pass=true when all categories are assessed (present or explicitly absent).
Record each absence in aero_evidence_gaps.

Do not create findings in Phase 15.
Do not execute Phase 16.
"""
    # END STRICT PHASE 15 AEROSPACE PROMPT

    # BEGIN STRICT PHASE 16 CROSS-SOURCE REVIEW PROMPT
    if args.phase == 16:
        prompt += f"""

Phase 16 specific instructions:

This phase is a cross-source consistency review phase only.
It is not a findings phase.

Hard prohibition:
- Do not create findings.
- Do not create candidate findings.
- Do not create issue objects.
- Do not create severity-ranked findings.
- Do not create rule-mapped findings.
- Do not use keys named findings, finding, issues, issue, severity, or rule_id.
- Do not promote observations into final issue language.
- Phase 19 is the only phase allowed to write findings JSON.

Required artifacts:
- exports/{project}-cross-source-review.json
- exports/{project}-cross-source-review-validation.json

ARTIFACT SCHEMA RULES — IMPORTANT:
- The review artifact (exports/{project}-cross-source-review.json) contains a nested `gate` object.
  Set gate.overall_pass=true inside the review artifact when review checks pass.
- The validation artifact (exports/{project}-cross-source-review-validation.json) must have
  `overall_pass` at the TOP LEVEL (NOT nested under gate). The auditor checks the top-level
  `overall_pass` field in the validation artifact, not gate.overall_pass.

Use these top-level keys in the review artifact:
- phase
- phase_name
- project
- timestamp
- summary
- checks
- cross_source_observations
- evidence_gaps
- limitations
- downstream_constraints
- gate

Validation artifact (cross-source-review-validation.json) required fields:
- phase
- overall_pass (bool — TOP LEVEL, not nested; true only when all review checks pass)

Allowed terminology:
- cross-source check
- consistency observation
- evidence gap
- limitation
- downstream constraint
- review note
- blocked check
- partial check

Forbidden terminology:
- finding
- issue
- severity
- rule_id
- candidate finding
- final finding

REQUIRED TOOL: scripts/cross_check_helpers.py (tripartite set operations and topology mapping)

Run all cross-checks:
```
python3 scripts/cross_check_helpers.py \\
  --bom exports/{project}-bom.json \\
  --sch exports/{project}-thomson-export-sch.json \\
  --brd exports/{project}-thomson-export-brd.json \\
  --json
```

What this analyzes (all checks run by default):
- RefDes reconciliation (tripartite set matching)
- Package mismatches (DFM_LIB_002)
- Netlist topology verification (SCH_NET_001)
- Voltage derating margins (SCH_POL_001, COMP_CAP_002)

Individual check flags (optional):
```
python3 scripts/cross_check_helpers.py --bom <bom> --sch <sch> --brd <brd> --run-reconciliation --json
python3 scripts/cross_check_helpers.py --bom <bom> --brd <brd> --check-packages --json
python3 scripts/cross_check_helpers.py --sch <sch> --brd <brd> --verify-netlist --json
python3 scripts/cross_check_helpers.py --bom <bom> --sch <sch> --verify-derating --json
```

Rule-to-tool mapping:
- RefDes consistency: --run-reconciliation
- DFM_LIB_002 (package mismatch): --check-packages
- SCH_NET_001 (netlist sync): --verify-netlist
- SCH_POL_001, COMP_CAP_002 (derating): --verify-derating

Record cross_check_helpers.py output in the cross-source review artifact.

Required coverage:
- BOM vs schematic
- BOM vs board
- power nets vs board/stack evidence
- connector/interface nets vs protection evidence
- regulator/power path schematic vs layout context
- paired/differential candidates vs routing evidence
- conversion warnings vs evidence reliability

Required validation:
- Artifact JSON parses.
- Top-level key findings is absent.
- No key named finding exists anywhere.
- No key named severity exists anywhere.
- No key named rule_id exists anywhere.
- No key named issue or issues exists anywhere.
- Cross-source conclusions are evidence-backed.
- Limitations are explicit where evidence is incomplete.
- gate.overall_pass=true only when these checks pass.

Do not execute Phase 17.
"""
    # END STRICT PHASE 16 CROSS-SOURCE REVIEW PROMPT

    # BEGIN STRICT PHASE 17 PRE-FINDINGS GATE PROMPT
    if args.phase == 17:
        prompt += f"""

Phase 17 — Pre-Findings Gate Check instructions:

This phase validates that all upstream evidence phases passed before candidate findings can be developed.
It does NOT create findings or candidates.

Required artifact:
- exports/{project}-pre-findings-gate.json

This is the ONLY artifact for Phase 17. There is NO separate -validation.json file.

IMPORTANT: This artifact uses `overall_gate_pass` (NOT `overall_pass`).
The auditor checks `overall_gate_pass` at the TOP LEVEL of this artifact.
Do NOT use `overall_pass`. Do NOT nest it under a `gate` object.

Required top-level fields in pre-findings-gate.json:
- phase
- phase_name
- project
- timestamp
- upstream_phases_checked
- gate_criteria (object summarizing what was checked)
- blockers (list — empty if all pass)
- overall_gate_pass (bool — TOP LEVEL; true only when all upstream validations pass)

Gate criteria to check (read these artifacts and verify overall_pass=true in each):
- exports/{project}-schematic-evidence-inventory-validation.json overall_pass
- exports/{project}-board-evidence-inventory-validation.json overall_pass
- exports/{project}-stackup-evidence-review-validation.json overall_pass
- exports/{project}-dfm-evidence-inventory-validation.json overall_pass
- exports/{project}-bom-evidence-inventory-validation.json overall_pass
- exports/{project}-image-evidence-review-validation.json overall_pass (if images provided)
- exports/{project}-datasheet-evidence-review-validation.json overall_pass
- exports/{project}-aerospace-evidence-inventory-validation.json overall_pass
- exports/{project}-cross-source-review-validation.json overall_pass

overall_gate_pass=true ONLY when ALL applicable upstream validations have overall_pass=true.

If any blocker exists, set overall_gate_pass=false and list each blocker artifact and field.

Do not execute Phase 18 if overall_gate_pass=false.
"""
    # END STRICT PHASE 17 PRE-FINDINGS GATE PROMPT

    # BEGIN STRICT PHASE 18/19 FULL COVERAGE PROMPT
    if args.phase == 18:
        prompt += f"""

Phase 18 full-coverage candidate development instructions:

This phase develops candidate findings only.
Do not write final findings JSON in Phase 18.

Do not apply arbitrary count limits.
Do not cap candidates at 10, 15, 20, or any other number.
Do not select only a small sample when more concrete evidence-backed candidates exist.

Required behavior:
- Review all Phase 8 through Phase 16 evidence.
- Include every concrete, non-duplicative, evidence-supported candidate.
- Reject unsupported, vague, duplicate, or single-source-overclaimed candidates.
- Keep rejected candidates in a rejected_candidates section with the rejection reason.
- Each retained candidate must have concrete citations to generated evidence artifacts.
- Candidate volume is controlled only by evidence quality, duplication, schema compatibility, and validation requirements.

Allowed:
- Many candidates, if each is evidence-backed.
- Grouping duplicates into one broader candidate when they share the same root cause.
- Marking confidence and evidence completeness.

Forbidden:
- Arbitrary candidate count caps.
- Dropping valid candidates solely to stay under a number.
- Promoting weak observations into candidates without evidence.
- Writing exports/{project}-findings.json in Phase 18.

Do not execute Phase 19.
"""

    if args.phase == 19:
        prompt += f"""

Phase 19 full-coverage findings JSON instructions:

This phase writes final findings JSON from the Phase 18 candidate artifact.

Do not apply arbitrary issue-count limits.
Do not cap issues at 10, 15, 20, or any other number.
The final issues list must include every concrete, non-duplicative, evidence-supported candidate that satisfies the findings schema and validation requirements.

Required behavior:
- Read exports/{project}-candidate-findings.json.
- Promote all valid evidence-backed candidates into final issues.
- Merge only true duplicates.
- Preserve evidence citations.
- Preserve rule/domain/severity mapping where supported by ontology and evidence.
- Keep broad evidence limitations worded as limitations, not overstated design defects.
- Include verified_checks and cross_checks as appropriate.
- Validate against the findings schema if a validator is available.

Valid reasons to exclude a candidate:
- It is unsupported by concrete citations.
- It is duplicate of another stronger issue.
- It violates schema.
- It is speculative or overclaims beyond available evidence.
- It belongs in verified_checks/cross_checks rather than issues.

Invalid reasons to exclude a candidate:
- The issue count is above 15.
- The report is getting long.
- The model should be concise.
- Token/cost concerns.

Do not execute Phase 20.
"""
    # END STRICT PHASE 18/19 FULL COVERAGE PROMPT

    # BEGIN STRICT PHASE 20 VALIDATE AND REPAIR PROMPT
    if args.phase == 20:
        prompt += f"""

Phase 20 — Validate and Repair Findings instructions:

This phase validates the findings JSON and repairs it if needed.

REQUIRED TOOL:
  python tools/validate_findings.py exports/{project}-findings.json

Run this command FIRST. Capture the full output.

If validation PASSES (exit code 0):
- No changes needed.
- Set phase_passed=true in the checkpoint row.

If validation FAILS (exit code non-zero):
- Read the full error output carefully.
- Repair exports/{project}-findings.json to fix the reported issues.
- Re-run tools/validate_findings.py after repair.
- Repeat until validation passes.
- Only then set phase_passed=true.

Common validation failures and repairs:
- Missing required fields (project_name, review_date, source_documents): add them
- Evidence rows missing source field: add source citations
- Uncited input files: ensure every PDF/JSON in exports/ is cited in at least one evidence[].source
- Schema violations (wrong field types, extra forbidden keys): fix to match findings schema

The artifact for Phase 20 is the SAME exports/{project}-findings.json from Phase 19.
You are repairing it in-place. Do NOT create a separate output artifact.

After repair and successful validation:
- Set blockers=[] and phase_passed=true in the checkpoint row.

If validation cannot be made to pass after 3 repair attempts, set phase_passed=false and
blockers=["validate_findings.py failed after repair attempts — see logs"].
"""
    # END STRICT PHASE 20 VALIDATE AND REPAIR PROMPT

    if args.phase == 21:
        prompt += f"""

Phase 21 — Generate Report instructions:

This phase generates the HTML review report from the validated findings JSON.

REQUIRED TOOL:
  python tools/gen_report.py exports/{project}-findings.json --output exports/

This produces:
- exports/{project}-review.html  (the final deliverable)

Before running gen_report.py, verify that tools/validate_findings.py passes:
  python tools/validate_findings.py exports/{project}-findings.json

If validate_findings.py fails, do NOT generate the report. Fix findings JSON first.

After running gen_report.py, write the required validation artifact:
  exports/{project}-report-generation-validation.json

Required fields in the validation artifact:
- findings_json_path
- validation_passed_before_report
- report_command
- html_report_path
- html_report_exists
- markdown_report_only_detected
- overall_pass

overall_pass=true ONLY when ALL of:
- validation_passed_before_report=true
- html_report_exists=true
- markdown_report_only_detected=false

Forbidden:
- Generating report before validation passes.
- Treating markdown-only output as satisfying this phase.
- Skipping the report-generation-validation.json artifact.
"""

    if args.phase == 22:
        prompt += f"""

Phase 22 — Final Summary instructions:

This phase validates all prior phase gates and writes the final run summary.

VALIDATION GATES (all must pass before writing a completion summary):
- exports/{project}-phase-checkpoints.jsonl exists; phase rows 1 through 21 all present and phase_passed=true (Phase 22 writes its own row after this summary)
- exports/tool-preflight-status.json overall_pass=true
- exports/datasheets/datasheet_manifest_validation.json overall_pass=true
- exports/{project}-schematic-evidence-inventory-validation.json overall_pass=true
- exports/{project}-board-evidence-inventory-validation.json overall_pass=true
- exports/{project}-dfm-evidence-inventory-validation.json overall_pass=true
- exports/{project}-bom-evidence-inventory-validation.json overall_pass=true
- exports/{project}-image-evidence-inventory.json overall_pass=true (when PDFs/images provided)
- exports/{project}-image-evidence-review-validation.json overall_pass=true (when PDFs/images provided)
- exports/{project}-datasheet-evidence-review-validation.json overall_pass=true
- exports/{project}-aerospace-evidence-inventory-validation.json overall_pass=true
- exports/{project}-cross-source-review-validation.json overall_pass=true
- exports/{project}-pre-findings-gate.json overall_gate_pass=true
- exports/{project}-findings.json exists and validator passed
- exports/{project}-report-generation-validation.json overall_pass=true
- exports/{project}-review.html exists

If ANY gate fails, write INVALID RUN SUMMARY instead of a completion summary.

REQUIRED SUMMARY CONTENT:
Datasheets:
  - manifest path, overall_pass, status=found count, missing local file count
  - discovered URL only count, download unavailable count

Schematic:
  - schematic evidence inventory validation path, overall_pass

Board:
  - board evidence inventory validation path, overall_pass

DFM:
  - DFM evidence inventory validation path, overall_pass

BOM:
  - BOM evidence inventory validation path, overall_pass

Findings:
  - total issue count, total verified_checks count, total cross_checks count
  - validation pass/fail, report HTML path

Do not generate new findings or perform new analysis in Phase 22.
"""

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
