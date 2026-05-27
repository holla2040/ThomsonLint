# OpenHands ThomsonLint Review Workflow

## Purpose


## Artifact-Based Phase Completion Rule

A phase may not be marked complete based only on narrative text. If the phase defines a required artifact or validation JSON, that artifact must exist on disk, parse successfully if JSON, and contain the required pass field set to true before the phase can be marked complete. Verbal claims such as "phase complete", "gate passed", or "reviewed" are invalid unless backed by the required artifact.

Universal phase checkpoint artifact: `exports/<project>-phase-checkpoints.jsonl`.
Every phase must append exactly one JSONL checkpoint row before moving to the next phase. Each row must include: `phase_number`, `phase_name`, `started_at_utc`, `completed_at_utc`, `required_artifacts`, `artifacts_verified`, `validation_artifacts`, `validation_passed`, `blockers`, `phase_passed`.
Rules: a phase is not complete unless its checkpoint row exists and `phase_passed=true`; if a phase has no separate artifact, the checkpoint row itself is the required artifact; phases 8 through 17 must each have a distinct checkpoint row; phases 18 and 19 must each have a distinct checkpoint row; the agent must not mark multiple phases complete with one shared checkpoint row; narrative text is not a checkpoint.
`exports/<project>-phase-checkpoints.jsonl` must record the phase-local gate result for each phase. The checkpoint row must include `repair_required=true` when a phase-local gate fails (i.e., when `phase_passed=false`).

Phase-Local Gate Enforcement Rule:
Each phase owns its own gate. A phase must not be marked complete until its required artifacts exist, parse successfully if JSON, and pass that phase’s validation criteria.

If a phase-local gate fails:
1. Stay in the same phase.
2. Repair only the artifact or work product for that phase.
3. Re-run that phase’s validation.
4. Repeat until the phase passes or a blocker is reported.
5. Do not advance to later phases.
6. Do not defer the failure to Phase 17, Phase 22, or a final audit.


This repo contains ThomsonLint and an integrated converter. An OpenHands or other coding agent must follow this order: prepare inputs, run setup/tool preflight, run the converter, inspect the framework, then continue the review workflow exactly as defined by this repository.

Do not invent a new review process, findings schema, ontology, or report format. Follow the existing ThomsonLint framework: `ontology/ontology.json`, `examples/examples.json`, `tests/findings_schema.json`, `tests/sample_findings.json`, `tools/validate_findings.py`, `tools/gen_report.py`, and `docs/REVIEWER_INSTRUCTIONS.md` when present.

## Standard Folder Layout

- `input/` - raw design files to convert.
- `exports/` - generated converter outputs, findings JSON, and final report.
- `datasheets/` - optional local datasheets supplied by the user.
- `tools/` - converter wrapper, validator, report generator, and export tools.
- `ontology/` - ThomsonLint rule ontology.
- `examples/` - worked examples mapped to ontology rules.
- `tests/` - JSON schemas and sample findings.
- `converter/` - integrated converter implementation, if present.

## Accepted Raw Input Files

Place raw review inputs under `input/`:

- IPC-2581 XML.
- PADS/OrCAD/ASCII schematic or netlist export.
- BOM CSV.
- Schematic PDF.
- Layout/Gerber/PCB PDF.
- Optional datasheets under `datasheets/`.
- `input/stackup.csv`.
- `input/stackup.json`.
- Board fabrication drawing PDF containing stackup table.
- ODB++ archive.
- ODB++ folder.
- IPC-2581 export with stackup/cross-section enabled.
- Allegro/OrCAD PCB Editor cross-section or stackup report.
- Altium Layer Stack Manager export or `.stackup` file.
- PADS layer stack/report export.
- KiCad `.kicad_pcb` or stackup report.
- Fab work order or board-build specification (solder alloy and IPC class for AERO_SLD_001).
- Conformal coating specification document (for AERO_TERM_001 masking requirements).
- Environmental or vibration profile document (for AERO_VIB_001 vibration assessment).
- Chassis-mounting drawing (for AERO_GND_001 bonding point identification).
- Assembly work instructions.

## Workflow 1: Prepare Review Inputs

1. Confirm `input/` exists.
2. List all files under `input/`.
3. Verify at least one design input exists: IPC-2581 XML, PADS/OrCAD/ASCII schematic or netlist export, BOM CSV, schematic PDF, or layout/Gerber/PCB PDF.
4. Do not modify git state.
5. Do not delete input files.
6. Use local datasheets from `datasheets/` if present; cite local filenames later in evidence.

## Workflow 2: Setup and Tool Preflight

1. This is a required normal numbered workflow and must complete before converter execution.
2. Check required local tools before running the converter:
   - `python3`
   - `pdftoppm`
   - `pdfinfo`
3. `pdftoppm` and `pdfinfo` are provided by Ubuntu/Debian package `poppler-utils`.
4. Run availability checks:

   ```bash
   which python3
   which pdftoppm
   which pdfinfo
   ```

5. If `pdftoppm` or `pdfinfo` is missing, attempt package install in the sandbox before converter execution:

   ```bash
   apt-get update && apt-get install -y poppler-utils
   ```

6. If `sudo` is required and available, use:

   ```bash
   sudo apt-get update && sudo apt-get install -y poppler-utils
   ```

7. After installation, verify:

   ```bash
   which pdftoppm
   which pdfinfo
   pdftoppm -v
   pdfinfo -v
   ```

8. Required preflight artifact: `exports/tool-preflight-status.json` with fields:
   - `python3_available`
   - `pdftoppm_available`
   - `pdfinfo_available`
   - `install_attempted`
   - `install_command`
   - `install_succeeded`
   - `pdfs_present`
   - `fallback_used`
   - `user_approved_fallback`
   - `approval_source`
   - `json_only_review_approved`
   - `json_only_approval_source`
   - `overall_pass`
9. Image-render fallback means using an alternate renderer (for example PyMuPDF) to produce PNG evidence. JSON-only fallback means proceeding without image evidence.
10. Image-render fallback approval and JSON-only fallback approval are separate. `user_approved_fallback=true` is sufficient only for image-render fallback.
11. JSON-only review requires `json_only_review_approved=true` and explicit user approval in a new message after the blocker is reported, recorded in `json_only_approval_source`.
12. Pass logic when PDFs are present: this workflow passes only if either (a) `pdftoppm_available=true` and `pdfinfo_available=true`, (b) image-render fallback is used and `user_approved_fallback=true`, or (c) JSON-only fallback is explicitly approved with `json_only_review_approved=true`.
13. Do not treat image-render fallback approval as JSON-only approval.
14. If PDFs are present and no approved render path or approved JSON-only fallback exists, stop before converter execution.
15. If `exports/tool-preflight-status.json` is missing or `overall_pass=false`, remain in Setup and Tool Preflight. Do not run the converter. Repair tool installation or stop for explicit user approval.

## Workflow 3: Run Integrated Converter

1. Run the integrated converter first:

   ```bash
   python3 tools/run_converter_pipeline.py input --project-name example --clean
   ```

2. Verify `exports/` exists.
3. Verify generated JSON files load with Python or another JSON parser.
4. Verify rendered PNGs exist when PDFs were provided.
5. Inspect `exports/example-conversion-report.json` and `exports/example-conversion-report.md` if present.
6. Record converter warnings from the report and generated JSON.
7. Record converter warnings as evidence-quality notes, not automatic design findings.

## Workflow 4: Inspect ThomsonLint Framework

Before reviewing evidence, inspect the repo framework files:

1. Load `ontology/ontology.json`.
2. Load `examples/examples.json`.
3. Load `tests/findings_schema.json`.
4. Load `tests/sample_findings.json`.
5. Inspect `tools/validate_findings.py`.
6. Inspect `tools/gen_report.py`.
7. Inspect `docs/REVIEWER_INSTRUCTIONS.md` if present.
8. Inspect `README.md` if present.
9. Determine valid top-level findings JSON structure.
10. Determine required issue fields.
11. Determine valid severity values.
12. Determine valid domains.
13. Determine valid rule IDs.
14. Determine expected `evidence[]` row format.
15. Determine `verified_checks` format if present.
16. Determine `cross_checks` format if present.

## Workflow 5: Full BOM Datasheet Retrieval

1. This is a required normal numbered workflow.
2. Build a datasheet manifest for every BOM line item and attempt full BOM datasheet coverage.
3. Enumerate every unique BOM line item from `exports/<project>-bom.json`; use schematic/component exports as needed for refdes/function context.
4. Every BOM line item must be accounted for in `exports/datasheets/datasheet_manifest.jsonl` with exactly one manifest row (or a clearly grouped row for equivalent BOM entries).
5. Prefer local datasheets under `datasheets/` first; record reused files with status `local`.
6. If local datasheets are missing and SearXNG MCP is available, use SearXNG MCP for datasheet discovery. Do not use browser Google search. Do not use Tavily unless explicitly requested by the user.
7. Do not use search snippets as design evidence.
8. Prefer official manufacturer or major distributor sources.
9. Save confirmed retrieved datasheets under `exports/datasheets/` as downloaded datasheet files (see definitions below).
10. Each manifest row must include:
    - `refdes` or `refdes_group`
    - BOM row index or stable component key
    - quantity
    - manufacturer (if available)
    - MPN (if available)
    - LCSC/distributor part number (if available)
    - description/value/package (if available)
    - search query or local matching method used
    - candidate URLs attempted (if web discovery was used)
    - selected URL (if found)
    - source domain (if found)
    - local saved filename (if found)
    - status
    - reason/status_note
11. Allowed status values are exactly: `local`, `found`, `ambiguous`, `missing`, `not_applicable_generic`.
12. Status definitions and required terms:
    - `local`: matching datasheet already existed locally and was reused.
    - `found`: matching datasheet found via approved discovery and saved under `exports/datasheets/` (must be a downloaded_datasheet).
    - `ambiguous`: multiple plausible datasheets or insufficiently specific part number.
    - `missing`: specific part appears to need a datasheet, but no confident match found after bounded multi-attempt search.
    - `not_applicable_generic`: generic passives/mechanical/commodity entry with no unique manufacturer MPN or distributor part number.
13. For generic resistor/capacitor/inductor/ferrite entries without unique manufacturer MPN or distributor part number, do not invent datasheets; mark `not_applicable_generic` with reason.
14. For specific parts with MPN/LCSC/distributor part number where no confident datasheet is found, mark `missing` or `ambiguous` with reason.
15. For each specific non-generic part, use an honest bounded multi-attempt process before marking missing (for example up to 3–5 candidate URLs) and try multiple query forms, such as:
    - `<MPN> datasheet pdf`
    - `<manufacturer> <MPN> datasheet`
    - `<LCSC part number> datasheet`
    - `<description> <package> <MPN> datasheet`
    - distributor/manufacturer-focused query
16. If the first URL fails, do not give up. Try additional plausible manufacturer/distributor candidates before marking missing.
17. Candidate URL handling:
    - try most authoritative result first
    - if download fails, try next plausible result
    - if PDF URL fails but product page works, inspect product page for datasheet link when tooling supports it
    - record failed candidate URLs in `candidate_urls` or `status_note`
    - do not loop indefinitely; use bounded attempts
18. Mandatory checkpoint A (manifest coverage): every BOM line item has a manifest row or clearly grouped equivalent row. This checkpoint must pass before evidence review continues.
19. Mandatory checkpoint B (retrieved evidence): all `found` datasheets are saved locally under `exports/datasheets/`.
20. A datasheet URL alone does not satisfy status `found`. Status `found` requires a local saved datasheet file under `exports/datasheets/`.
21. Missing/ambiguous datasheets do not block review unless user explicitly sets datasheets as a hard gate; report them as evidence limitations.
22. **Hard definitions**:
    - `discovered_url`: a candidate datasheet URL found by SearXNG MCP or another approved discovery path. This is not evidence and does not count as found.
    - `downloaded_datasheet`: a datasheet file saved locally under `exports/datasheets/`. Only this can satisfy `status=found` or be cited as datasheet evidence.
23. **Hard rule**: A BOM row must not be marked `status=found` unless `local_saved_filename` is populated and that file exists under `exports/datasheets/`.
24. **Hard rule**: If candidate URLs are discovered but no local file is saved, the manifest row status must be `ambiguous` or `missing`, not `found`.
25. **Hard rule**: The agent must not continue past Full BOM Datasheet Retrieval while any `status=found` row points to a missing local file.
26. **Hard rule**: The agent must validate the datasheet manifest before moving to evidence review.
27. Required manifest validation step (before evidence review):
    - load `exports/datasheets/datasheet_manifest.jsonl`
    - count BOM rows from `exports/<project>-bom.json`
    - verify every BOM row has a manifest row or clearly grouped equivalent row
    - verify every status is one of `local`, `found`, `ambiguous`, `missing`, `not_applicable_generic`
    - verify every `status=local` row has a `local_saved_filename` that exists
    - verify every `status=found` row has a `local_saved_filename` that exists under `exports/datasheets/`
    - verify `candidate_urls` are recorded for web-discovered rows
    - verify failed candidate URLs are recorded when a download attempt fails
    - fail the checkpoint if any `status=found` row lacks a local file
28. Define BOM line item: every raw BOM CSV row is a BOM line item, including labels, documents, generic passives, connectors, test points, mechanical rows, rows without MPN, and rows with MPN=`?`.
29. Every raw BOM CSV row must produce exactly one manifest row unless a grouped row explicitly lists all included raw BOM row indexes.
30. Coverage is invalid if manifest row count plus grouped covered row indexes does not cover every raw BOM row index.
31. Rows without an applicable unique datasheet must still be represented, usually as `not_applicable_generic` with a reason.
32. Do not omit document, label, connector, test point, mechanical, or generic rows.
33. Required validation artifact: `exports/datasheets/datasheet_manifest_validation.json` including:
    - `bom_csv_path`
    - `bom_raw_row_count`
    - `manifest_path`
    - `manifest_row_count`
    - `covered_bom_row_indexes`
    - `uncovered_bom_row_indexes`
    - `status_counts`
    - `found_rows_missing_local_files`
    - `local_file_validation_pass`
    - `coverage_pass`
    - `overall_pass`
34. Full BOM Datasheet Retrieval passes only if `coverage_pass=true`, `local_file_validation_pass=true`, `overall_pass=true`, and no `status=found` row lacks an existing `local_saved_filename`.
35. If manifest validation fails, stop and repair the manifest and/or download files before continuing. Do not proceed to Review Datasheet Evidence, Cross-Source Consistency Review, Candidate Finding Development, or Findings JSON.
36. Do not write "datasheets available online" as equivalent to found. Use "discovered_url only" and classify as `ambiguous` or `missing` unless a local file is saved.
37. When a candidate datasheet URL is found, the agent must attempt to save the file locally under `exports/datasheets/`. If direct PDF download fails, try the next bounded candidate URL or inspect the product page for a PDF link if tooling supports it.
38. Keep bounded retries for specific non-generic parts (up to 3–5 plausible candidate URLs); do not loop indefinitely.
39. If the environment cannot download files, do not mark rows found. Mark as `missing` or `ambiguous` and explicitly state "download unavailable in environment" in `status_note`.
40. Full BOM Datasheet Retrieval means every BOM line item is represented in the manifest.
41. The phase is not complete if only critical components were searched, only ICs were searched, only easy-URL rows were included, or generic/test-point/connector/mechanical parts were omitted instead of classified.
42. Even if a part does not need a datasheet, it must still receive a manifest row with `status=not_applicable_generic` or `missing`/`ambiguous` as appropriate.
43. Cite only local saved datasheet filenames in findings.
44. Final response must include: total BOM line items, manifest row count, local datasheets reused count, retrieved datasheets count, ambiguous count, missing count, not_applicable_generic count, manifest path, datasheets cited in findings, and candidate URL/download failure summary (if any).
45. Do not print, store, or write secrets/API keys in repo files, findings, reports, manifests, or logs.
46. If `exports/datasheets/datasheet_manifest_validation.json` is missing or `overall_pass=false`, remain in Full BOM Datasheet Retrieval. Repair the manifest and/or datasheet files, regenerate `datasheet_manifest_validation.json`, and do not proceed to image gate or evidence review until Workflow 5 passes.

## Workflow 6: Enforce Image Review Gate

1. This is a required normal numbered workflow for deep-review runs when PDFs are present.
2. Verify schematic PNGs exist when schematic PDFs are present.
3. Verify layout/Gerber/PCB PNGs exist when layout/Gerber/PCB PDFs are present.
4. If PDFs are present but PNGs are missing, stop and report an image-rendering blocker.
5. Distinguish fallback types:
   - image-render fallback: use an alternate renderer (for example PyMuPDF) to still produce PNG evidence
   - JSON-only fallback: proceed without image evidence
6. These fallback types require separate approval.
7. `user_approved_fallback=true` in `exports/tool-preflight-status.json` is sufficient only for image-render fallback.
8. JSON-only review requires `json_only_review_approved=true` in `exports/tool-preflight-status.json`. Read `json_only_review_approved` directly from `exports/tool-preflight-status.json` (written by Workflow 2/Phase 3); do not re-request user approval if it is already `true` in that file. Explicit user approval in a new message is required only if the field is absent or `false`.
9. Do not treat image-render fallback approval as JSON-only approval.
10. Required artifact: `exports/<project>-image-evidence-inventory.json` with fields `pdf_sources`, `conversion_tool`, `fallback_used`, `user_approved_fallback`, `total_pages_expected`, `total_pages_rendered`, `output_files`, `schematic_pngs`, `layout_pngs`, `pages_inspected`, `page_roles_or_labels_if_identifiable`, `visual_context_notes`, `limitations`, `confirmation_no_pixel_quantitative_claims`, `overall_pass`.
11. File names and file sizes alone are not sufficient image review.
12. If PDFs are present, `total_pages_rendered` must be greater than zero and equal `total_pages_expected` unless an explicit limitation is recorded.
13. If `fallback_used=true`, then `user_approved_fallback` must be true.
14. If PDFs are present and no PNG evidence can be produced, stop unless `json_only_review_approved=true`.
15. If `overall_pass` is not true, do not proceed to evidence review or candidate findings.
16. If `exports/<project>-image-evidence-inventory.json` is missing or `overall_pass=false` when PDFs/images are required, remain in Enforce Image Review Gate. Repair image rendering or stop for explicit fallback approval. Do not proceed to schematic/board evidence review or candidate findings.

## Workflow 7: Review Schematic Evidence FULL

1. Inspect generated schematic JSON.
2. **REQUIRED: Run schematic analysis tool**:
   Execute `python scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --analyze-all --json` to perform deterministic graph-based analysis for rules requiring multi-hop connectivity tracing.
   
   **What this analyzes:**
   - Single-pin nets (SCH_NET_002)
   - UART TX/RX crossover (SCH_UART_001)
   - FET gate termination (SCH_FET_001)
   - Floating inputs (SCH_FLOAT_001)
   - I2C pull-ups (MS_I2C_001)
   - I2C address conflicts (SCH_I2C_002)
   - Op-amp tie-off (SCH_PULLUP_001)
   
   **Output:** LLM-optimized JSON with precise paths (refdes, pin_number, pin_name, net_name, rule_id).
   
   **Individual check flags (optional):**
   - `--single-pins` - Run only SCH_NET_002
   - `--uart-check` - Run only SCH_UART_001
   - `--fet-check` - Run only SCH_FET_001
   - `--floating-check` - Run only SCH_FLOAT_001
   - `--i2c-check` - Run only MS_I2C_001, SCH_I2C_002
   - `--opamp-check` - Run only SCH_PULLUP_001

3. Review components, refdes coverage, net names, power nets, external interfaces, connector nets, single-pin/unusual connections, and schematic-level evidence limitations.
4. Cite schematic JSON file/path/field/value where practical.
5. Use schematic PNGs only for visual/context confirmation, not quantitative claims.
6. Record checked-good items for `verified_checks` when useful.
7. Assess all KB Appendix H check families and Cluster 1 Rules (all must be addressed or explicitly marked not-applicable/insufficient-evidence):
   - **Net Integrity**: Single-pin nets (SCH_NET_002), cross-sheet label matching (SCH_NET_001), consistent naming (SCH_NET_003), duplicate power net names indicating shorted rails (SCH_NET_004).
   - **Component Application**: UART TX/RX crossover verification (SCH_UART_001), floating/untied digital/ADC inputs (SCH_FLOAT_001), MOSFET gate pull-down (SCH_FET_001), unused op-amp/comparator tie-off (SCH_PULLUP_001), op-amp feedback topology and capacitive load (AN_OPAMP_002, AN_OPAMP_003), ADC filter/protection (AN_ADC_001, AN_ADC_003), SMPS compensation (PWR_COMP_001).
   - **Value, Rating & Metadata**: Polar capacitor polarity and voltage marking (SCH_POL_001), DNP flags (SCH_DNP_001). Flag [UNVERIFIABLE] subjective rules (SCH_OPT_001, SCH_IC_001).
   - **Protection and Safety**: Relay coil flyback diodes (PWR_RELAY_001), fuse sizing (PWR_FUSE_001), TVS placement (AERO_TVS_001), reverse-polarity topology (AERO_RPP_001).
   - **I2C & Mixed Signal**: Address annotation (SCH_I2C_001), address conflict detection (SCH_I2C_002), bus pull-ups (MS_I2C_001), defined reset states (MS_RST_001), isolated power (MX_PWR_001).
   - **Test & Debug**: Test points for JTAG (DFT_JTAG_001) and SWD (DFT_SWD_001).
8. Required artifact: `exports/<project>-schematic-evidence-inventory.json` with fields: `schematic_json_loaded`, `inspected_components`, `power_nets_identified`, `connector_nets_identified`, `interface_nets_identified`, `single_pin_nets_found`, `i2c_buses_identified`, `uart_interfaces_identified`, `relay_coil_count`, `protection_components_identified`, `schematic_check_families_covered`, `conversion_limitations`, `evidence_paths_used`.
9. Required validation artifact: `exports/<project>-schematic-evidence-inventory-validation.json` with fields: `inventory_exists`, `required_fields_present`, `schematic_json_loaded`, `check_families_assessed_or_marked_na`, `overall_pass`.
10. Workflow 7 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 7 and repair before proceeding.

## Workflow 8: Full Board/Layout JSON Evaluation

1. Inspect the full logical content of `exports/<project>-thomson-export-brd.json`.
2. Full board JSON evaluation is required; summary-only extraction/review is forbidden.
3. If board JSON is too large to open directly, use chunked or targeted programmatic inspection (Python/jq-style traversal). Do not reduce review to top-level summary only.

4. **REQUIRED: Use `scripts/geometry_helpers.py` for quantitative geometry analysis**:
   
   **DFM Checks (REQUIRED):**
   ```bash
   # Via annular ring check (DFM_VIA_001, DFM_VIA_003, DFM_VIA_004)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-annular-ring --json
   
   # Acid trap detection (DFM_ACID_001)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --detect-acid-traps --json
   
   # Board edge clearance (DFM_EDGE_001, net-type-aware: GND=25mil, PWR/SIG=50mil)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --board-edge-clearance --json
   
   # Copper balance check (DFM_COPPER_001)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --copper-balance --json
   
   # NPTH keepout check (Appendix K.6)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --npth --npth-radius 4.0 --json
   ```
   
   **Physical-Math Verification (REQUIRED if stackup available):**
   ```bash
   # Impedance verification (HS_MAT_001) - Wheeler/Wadell formulas
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-impedance --target-ohms 100 --json
   
   # Trace temperature/ampacity (PWR_TRACE_002) - IPC-2152 formulas
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-trace-temp --current-a 3.0 --max-temp-rise 10.0 --json
   
   # Voltage clearance (DFM_TRACE_004) - IPC-2221B tables
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-voltage-clearance --json
   ```
   
   **Utility Checks (as needed):**
   ```bash
   # Extract all net segment statistics
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --net <NET_NAME> --json
   
   # Calculate clearance between two nets
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --clearance NET_A NET_B
   
   # Analyze all differential pairs (auto-detected)
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --diff-pairs --json
   
   # Verify trace ampacity for power nets
   python scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --ampacity VCC 2.0
   ```
   
   **Rule-to-Tool Mapping:**
   - PWR_TRACE_002 (thermal): `--verify-trace-temp`
   - HS_MAT_001 (impedance): `--verify-impedance`
   - DFM_TRACE_004 (voltage spacing): `--check-voltage-clearance`
   - DFM_VIA_001/003/004 (annular rings): `--check-annular-ring`
   - DFM_ACID_001 (acid traps): `--detect-acid-traps`
   - DFM_EDGE_001/PANEL_001 (edge clearance): `--board-edge-clearance`
   - DFM_COPPER_001 (copper balance): `--copper-balance`
   - Appendix K.6 (NPTH keepout): `--npth --npth-radius 4.0`
   - HS_DIFF_001-006 (diff pairs): `--diff-pairs`
   
   **If stackup unavailable:** Mark impedance/thermal checks as `[STACKUP_DATA_REQUIRED]` in findings but STILL run all DFM checks.

5. **REQUIRED: Physical-Math and Electrical Verification (when stackup data available)**:
   To prevent qualitative hallucination of trace margins, the agent must run physical-math verification using `scripts/saturn_engine.py` (integrated into `scripts/geometry_helpers.py`) to verify electrical constraints against the Board JSON, Schematic JSON, and Stackup files.
   
   Required Verification Runs:
   
   a. **Controlled Impedance Verification (Rule HS_MAT_001)**
      Run Wheeler transmission line models to verify target differential and single-ended impedance:
      ```bash
      py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-impedance --target-ohms 50 --json
      ```
      *Pass Criteria:* Calculated impedance must fall within ±10% of the target class definition.
   
   b. **IPC-2152 Trace Current and Temperature Rise (Rule PWR_TRACE_002)**
      Compute current density capacity for all power nets:
      ```bash
      py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-trace-temp --current-a 3.0 --max-temp-rise 10.0 --json
      ```
      *Pass Criteria:* Peak temperature rise (ΔT) must not exceed 10°C on any power path segment.
   
   c. **IPC-2221B High-Voltage Clearance Check (Rule DFM_TRACE_004)**
      Determine electrical clearances based on net peak voltages parsed from schematic net lists:
      ```bash
      py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-voltage-clearance --json
      ```
      *Pass Criteria:* Minimum net-to-net clearances must equal or exceed IPC-2221B Table 6-1 spacing boundaries.
   
   Note: Physical-math verification requires stackup data (`input/stackup.csv` or stackup metadata in board JSON) and voltage annotations from schematic. If stackup unavailable, mark these checks as `[STACKUP_DATA_REQUIRED]` in the evidence inventory.

7. **Geometry Analysis Pass/Fail Criteria** (record in board evidence inventory):
   - **Differential pair uncoupled length**: PASS if < 5mm; WARNING if 5-10mm; FAIL if > 10mm
   - **Differential pair length mismatch**: PASS if < 1%; WARNING if 1-3%; FAIL if > 3%
   - **Differential pair coupling quality**: PASS if "good" (≥90% coupled); WARNING if "marginal" (70-90%); FAIL if "poor" (<70%)
   - **NPTH copper keepout**: PASS if violation_count = 0; FAIL if any copper within 4mm of NPTH
   - **Trace width vs ampacity**: PASS if min_capacity_a ≥ required_current_a; FAIL otherwise
   - **Critical net clearance**: PASS if min_clearance ≥ 0.15mm (6mil standard); FAIL if below design rule
   - **Via annular ring**: PASS if min_ring ≥ 0.127mm (5 mil); WARNING if < 0.127mm; FAIL if critical
   - **Acid traps**: PASS if trap_count = 0; WARNING if angle > 60°; FAIL if angle ≤ 60°
   - **Board edge clearance**: PASS if min_clearance ≥ 0.5mm (20 mil); FAIL otherwise
   - **Copper balance**: PASS if layer mismatch < 25%; WARNING if 25-40%; FAIL if > 40%
   - **Impedance verification** (when stackup available): PASS if within ±10% of target; FAIL otherwise
   - **Temperature rise** (when stackup available): PASS if ΔT ≤ 10°C; WARNING if 10-20°C; FAIL if > 20°C
   - **Voltage clearance**: PASS if actual ≥ IPC-2221B required; FAIL otherwise
8. Required inspection categories (Assess all Cluster 2 rules or mark insufficient-evidence):
   - **Trace & Polygon Geometry**: Trace width vs ampacity (PWR_TRACE_002, DFM_TRACE_005), DC resistance (PWR_RES_001), 90-degree crossings (MX_ROUTE_001), serpentine lengths (HS_ROUTE_001).
   - **Differential Pairs & High-Speed**: Uncoupled length, symmetry, and mismatches (HS_DIFF_001, HS_DIFF_002, HS_DIFF_003, HS_DIFF_004, HS_DIFF_005, HS_DIFF_006, HS_SER_001, HS_SER_002), DDR length matching (HS_DDR_001, HS_DDR_002), inner-layer routing preference (HS_STACK_001, HS_STACK_002).
   - **Clocks & Crystals**: Trace length, 90-degree bends, routing keepouts under crystals, and proximity (HS_CLK_001, HS_CLK_002, HS_XTAL_001 to HS_XTAL_006).
   - **Power & SMPS Hot Loops**: Cap placement, SW node size, layer alignment, and inductor keepouts (PWR_DECPL_001 to PWR_DECPL_005, PWR_BUCK_001 to PWR_BUCK_006).
   - **EMC & Signal Integrity**: Ground slots/walls, stitching via grids, return paths, and TVS/Filter placement (EMC_ESD_001 to EMC_ESD_006, EMC_PATH_001, EMC_PLANE_002, EMC_AGG_001, EMC_STITCH_001, EMC_STITCH_002, EMC_VIA_003). 
   - **Analog Isolation**: ADC partitioning, single-point AGND/DGND, and high-Z guards (AN_ADC_004 to AN_ADC_007, AN_SENSOR_001).
   - **Thermal Area Math**: Copper dissipation area, thermal via arrays (THM_PWR_001, THM_PWR_002, THM_VIA_001, THM_VIA_004, THM_VIA_005), component heat spread (THM_SPREAD_001).
   - **Aerospace Limits**: NPTH copper keepouts for chassis ground (AERO_GND_001).
   - **DFM Geometry**: Via annular rings (DFM_VIA_001/003/004), acid traps (DFM_ACID_001), edge clearance (DFM_EDGE_001/PANEL_001), copper balance (DFM_COPPER_001).
   - **Physical-Math Verification** (when stackup available): Impedance calculations (HS_MAT_001), thermal/current capacity (PWR_TRACE_002), voltage spacing (DFM_TRACE_004).
   - **Unverifiable/Subjective Constraints**: Flag rules requiring human judgment (HS_CRIT_001, HS_CROSS_001, HS_SENS_001, HS_SHORT_001) as partially verifiable.
9. Produce a board evidence inventory file under `exports/`: `exports/<project>-board-evidence-inventory.json` (required, exact path must be recorded).
10. Board evidence inventory must include: `source_board_json`, `generated_timestamp`, `board_json_loaded`, `inspected_sections`, `unavailable_sections`, `object_counts`, `layer_count`, `net_count`, `route_count`, `via_count`, `hole_count`, `component_count_if_available`, `route_width_summary`, `route_length_summary`, `candidate_differential_or_paired_nets`, `candidate_power_nets`, `candidate_connector_or_interface_nets`, `candidate_test_or_debug_features`, `npth_holes_with_copper_keepout`, `thermal_pad_components`, `smps_candidates`, `ground_plane_slot_indicators`, `conversion_limitations`, `missing_or_unsupported_fields`, `evidence_paths_used`, and **`geometry_helper_analysis`** (REQUIRED FIELD containing results from differential_pairs, npth_clearance, trace_widths, annular_ring, acid_traps, board_edge_clearance, copper_balance, and physical_math_verification when stackup available).
11. Board evidence review checkpoint requires:
   - board JSON loaded successfully
   - required categories inspected or explicitly marked unavailable
   - **geometry_helpers.py executed and results recorded** (mandatory, including DFM checks and physical-math when stackup available)
   - board evidence inventory created and file existence verified
   - board evidence inventory validation artifact exists: `exports/<project>-board-evidence-inventory-validation.json` with `inventory_exists`, `required_fields_present`, `board_json_loaded`, `required_categories_inspected_or_marked_unavailable`, `geometry_helpers_executed`, `dfm_geometry_checks_executed`, `physical_math_checks_attempted_or_marked_unavailable`, `overall_pass`
   - no findings written before board evidence inventory exists
   - if board evidence inventory validation fails, stop and repair before Candidate Finding Development or Findings JSON
   - if `exports/<project>-board-evidence-inventory.json` is not created, the agent must stop before candidate finding development
   - A printed summary table is not sufficient evidence of full board JSON evaluation. The required inventory JSON artifact must exist and pass validation.
12. Board JSON is exported geometry/routing evidence, not true DRC.
13. Do not claim impedance verification, thermal capacity verification, or manufacturing signoff without explicit physical-math tool evidence and stackup data. Mark as `[STACKUP_DATA_REQUIRED]` if unavailable.
14. If `exports/<project>-board-evidence-inventory.json` or `exports/<project>-board-evidence-inventory-validation.json` is missing, invalid, or `overall_pass=false`, remain in Full Board/Layout JSON Evaluation. Repair the inventory and validation artifacts. Do not proceed to stackup review, cross-source review, or candidate findings.

## Workflow 9: Review Stackup and Manufacturing Evidence

1. Inspect generated stack JSON.
2. Explicitly inspect candidate stackup sources: generated stack JSON, `input/stackup.csv`, `input/stackup.json`, `input/*.tcfx` (Cadence Allegro/OrCAD technology files), fabrication drawing PDFs, ODB++ archive/folder if present, IPC-2581 stackup/cross-section content if present, and EDA-specific stackup reports if present.
3. **Note on TCFX Auto-Merge**: The `thomson_bundle_converter.py` now automatically searches for `.tcfx` files and merges stackup data during conversion. Check `exports/*-thomson-export-stack.json` for `tcfx_merge` metadata to verify if TCFX data was merged automatically.
   
   **Manual TCFX merge** (only needed to update existing stackup JSON):
   ```bash
   # Merge Cadence TCFX stackup data to resolve null material properties
   py -3 converter/ipc2581_to_json/parse_tcfx_stackup.py input/<project>.tcfx exports/<project>-thomson-export-stack.json
   ```
   This extracts and merges:
   - Layer thicknesses (copper and dielectric)
   - Dielectric constants (Dk) and loss tangents (Df)
   - Material names
   - Copper weights
   
   After merging, the stackup JSON will have complete material data enabling physical-math verification.

4. **REQUIRED: If `input/stackup.csv` or `input/stackup.json` exists, run `scripts/stackup_helpers.py`**:
   ```bash
   # Validate stackup and check all criteria
   py -3 scripts/stackup_helpers.py input/stackup.csv --validate-stackup --json
   
   # Or for JSON input
   py -3 scripts/stackup_helpers.py input/stackup.json --validate-stackup --json
   
   # Individual checks available:
   py -3 scripts/stackup_helpers.py input/stackup.csv --check-thickness --json        # DFM_STACKUP_001
   py -3 scripts/stackup_helpers.py input/stackup.csv --check-symmetry --json         # DFM_STACKUP_002
   py -3 scripts/stackup_helpers.py input/stackup.csv --check-reference-planes --json # HS_MAT_001
   ```
5. Stackup helper analysis provides deterministic validation of:
   - Finished board thickness calculation and tolerance check (nominal 1.6mm ± 10%)
   - Dielectric symmetry verification around stackup centerline
   - Signal layer adjacent reference plane check (flags signal-on-signal sandwiches)
6. ODB++ may be the preferred board/layout/fabrication source when present, but always inspect what stackup/material fields are actually present before making stackup claims.
7. IPC-2581 and ODB++ are both possible board/layout sources, but neither guarantees complete stackup/material/impedance data unless the export includes it.
8. If no explicit stackup source exists, mark stackup as missing evidence.
9. Layer names, Gerber filenames, ODB++ matrix layer names, IPC-2581 layer names, or PDF/Gerber page names alone are insufficient for dielectric thickness, copper weight, material system, Dk/Df, controlled impedance, finished board thickness, or manufacturing signoff.
10. Without explicit stackup/material/impedance evidence, do not claim impedance verification, stackup verification, manufacturing signoff, return-path quality beyond limited qualitative observations, exact dielectric spacing, exact layer construction, exact copper weight, or material/Dk/Df verification.
11. Report stackup completeness status as one of: `complete_explicit`, `partial_explicit`, `layer_order_only`, `missing`.
12. Status definitions and required terms:
   - `complete_explicit`: layer order/type, copper thickness/weight, dielectric thickness, and material/Dk or equivalent facts are available.
   - `partial_explicit`: some explicit stackup facts exist but key fields are missing.
   - `layer_order_only`: only layer names/order/types are available.
   - `missing`: no reliable explicit stackup source is available.
13. Recommended manual `stackup.csv` schema: `layer_index`, `layer_name`, `layer_type`, `material`, `thickness_mil`, `copper_oz`, `dielectric_dk`, `dielectric_df`, `notes`.
14. Optional `impedance_rules.csv` schema: `rule_name`, `net_class`, `target_ohms`, `tolerance_ohms`, `layer`, `width_mil`, `spacing_mil`, `reference_plane`, `notes`.
15. Final response must include: stackup source used, stackup completeness status, missing stackup fields, whether impedance evidence was available, whether TCFX merge was performed, stackup_helpers.py results (if applicable), and stackup limitations.
16. Note: DFM manufacturing rule compliance (trace width, via annular ring, solder mask, panelization, fiducials, edge clearances) is covered separately in Workflow 10. This workflow focuses on stackup material data, impedance evidence, and layer structure only.

## Workflow 10: Review DFM and Manufacturing Specifications

1. Review design-for-manufacturing compliance against KB Appendix G requirements using board geometry data from Workflow 8.
2. **REQUIRED: Verify DFM geometry checks have been executed. If not, run them now**:
   ```bash
   py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-annular-ring --json
   py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --detect-acid-traps --json
   py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --board-edge-clearance --json
   py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --copper-balance --json
   ```
3. Source evidence from `exports/<project>-board-evidence-inventory.json` (Workflow 8 output). Perform targeted re-queries against `exports/<project>-thomson-export-brd.json` if needed.
4. Assess all DFM check targets and Cluster 3 Rules (or explicitly mark not-applicable/insufficient-evidence):
   - **Manufacturing Minimums**: Trace width/spacing (DFM_TRACE_001, DFM_TRACE_004), Via drill/annular ring (DFM_VIA_001, DFM_VIA_003, DFM_VIA_004), Slivers (DFM_SLIVER_001), Acid traps (DFM_ACID_001), Thermal via size/spacing (THM_VIA_002, THM_VIA_003).
   - **Mask & Paste**: Mask web and clearances (DFM_MASK_001), Stencil matching (DFM_PASTE_001).
   - **Silkscreen & Labeling**: Pad clearance/legibility (DFM_SILK_001), Sharpie box (DFT_SILK_001), Header text (DFT_SILK_002, DFM_LABEL_001), Connector/Polarity labels (DFT_POL_001, DFT_CONN_LABEL_001), Test point labels (DFT_TP_004). Layer markers (DFM_LAYER_001).
   - **Panelization & Clearances**: Edge clearance (DFM_EDGE_001, DFM_PANEL_001), Component edge clearance (DFM_COMP_EDGE_001), Courtyard overlaps (DFM_COURT_001).
   - **Assembly & DFT**: Fiducial placement (DFM_FID_001, DFM_FID_002, DFT_FID_001), Copper balance (DFM_COPPER_001), Test points (DFT_TP_001, DFT_TP_002, DFT_TP_003, DFT_GND_003).
   - **Mechanical (Requires 3D/STEP)**: If Enclosure/STEP data is absent, flag [UNVERIFIABLE] for Connector reinforcement (MEC_CONN_001), Mounts (MEC_MOUNT_001), Heatsink fits (MEC_HEATSINK_001), UI alignment (MEC_UI_001), and Height limits (MEC_HEIGHT_001).
5. Required artifact: `exports/<project>-dfm-evidence-inventory.json` with fields: `trace_width_minimum_checked`, `min_trace_width_found_mil`, `trace_spacing_minimum_checked`, `min_trace_spacing_found_mil`, `via_annular_ring_checked`, `min_annular_ring_found_mil`, `acid_trap_assessment`, `solder_mask_web_checked`, `silkscreen_clearance_checked`, `fiducial_count`, `fiducial_placement_assessed`, `board_edge_clearance_checked`, `min_copper_to_edge_found_mil`, `component_to_edge_clearance_checked`, `min_component_to_edge_found_mm`, `copper_sliver_assessment`, `courtyard_overlap_checked`, `panelization_applicable`, `copper_balance_checked`, `dfm_limitations`, `dfm_evidence_sources`, **`geometry_helpers_dfm_results`** (REQUIRED: annular_ring, acid_traps, board_edge_clearance, copper_balance check outputs).
6. Required validation artifact: `exports/<project>-dfm-evidence-inventory-validation.json` with fields: `inventory_exists`, `required_fields_present`, `dfm_categories_assessed_or_marked_na`, `geometry_helpers_dfm_executed`, `overall_pass`.
7. Workflow 10 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 10 and repair before proceeding.
8. Do not claim DFM compliance without board geometry evidence. Do not confuse stackup material data with DFM geometry data.

## Workflow 11: Review BOM and Component Evidence FULL

1. Inspect generated BOM JSON.
2. **REQUIRED: Run BOM analysis tool**:
   Execute `python scripts/bom_helpers.py exports/<project>-bom.json --audit-components --json` to perform deterministic component-level analysis.
   
   **What this analyzes:**
   - Heavy components >3g (AERO_VIB_001)
   - Capacitor dielectrics (COMP_CAP_001)
   - Incomplete MPNs (DFM_BOM_001)
   - Lead finish assessment (AERO_SLD_001)
   - Polarized capacitors (SCH_POL_001)
   
   **Individual check flags (optional):**
   ```bash
   # Heavy component check (adjustable threshold)
   python scripts/bom_helpers.py exports/<project>-bom.json --heavy-threshold 3.0 --json
   
   # Capacitor dielectric check (X5R, X7R vs Y5V, Z5U)
   python scripts/bom_helpers.py exports/<project>-bom.json --check-dielectrics --json
   
   # MPN completeness audit
   python scripts/bom_helpers.py exports/<project>-bom.json --audit-mpns --json
   
   # Lead finish check (Sn vs SnPb)
   python scripts/bom_helpers.py exports/<project>-bom.json --check-lead-finish --json
   
   # Polarized component check
   python scripts/bom_helpers.py exports/<project>-bom.json --polarized --json
   ```
   
   **Output:** LLM-optimized JSON with precise paths (refdes, mpn, description, rule_id).
   
   **Rule-to-Tool Mapping:**
   - AERO_VIB_001 (heavy components): `--heavy-threshold`
   - COMP_CAP_001 (dielectrics): `--check-dielectrics`
   - DFM_BOM_001 (MPN completeness): `--audit-mpns`
   - AERO_SLD_001 (lead finish): `--check-lead-finish`
   - SCH_POL_001 (polarized): `--polarized`

3. Review component list, refdes coverage, manufacturer/MPN/LCSC fields, quantity consistency, missing metadata, package information, and BOM/schematic/board consistency candidates.
4. Identify components that need datasheet evidence.
5. Do not infer datasheet parameters from vendor names or package names alone.
6. Flag aerospace-relevant BOM fields: component mass candidates > 1 g, lead-finish designator fields (JESD201 class 1A, -E3/-M3 suffixes), IPC class from BOM notes, and solder alloy from BOM notes or fab fields.
7. Required artifact: `exports/<project>-bom-evidence-inventory.json` with fields: `bom_row_count`, `refdes_coverage`, `mpn_present_count`, `mpn_missing_count`, `lcsc_present_count`, `manufacturer_present_count`, `quantity_consistency_checked`, `package_metadata_coverage`, `dnp_components_flagged`, `missing_metadata_rows`, `aero_lead_finish_candidates`, `component_mass_candidates`, `datasheet_needed_components`, `bom_schematic_consistency_candidates`, `evidence_paths_used`.
8. Required validation artifact: `exports/<project>-bom-evidence-inventory-validation.json` with fields: `inventory_exists`, `required_fields_present`, `bom_loaded`, `overall_pass`.
9. Workflow 11 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 11 and repair before proceeding.

## Workflow 12: Review Image Evidence FULL

1. This workflow is required for deep-review runs when PDFs are present.
2. Inspect generated schematic PNGs.
3. Inspect generated layout/Gerber/PCB PNGs.
4. Record image pages actually opened and inspected.
5. Image review must open and inspect actual generated PNGs, not only list filenames/sizes. The Workflow 6 image-evidence-inventory confirms files exist; this workflow must produce a separate artifact proving inspection occurred.
6. Required artifact (distinct from Workflow 6 image-evidence-inventory): `exports/<project>-image-evidence-review.json` with fields: `pages_actually_opened`, `schematic_page_observations`, `layout_page_observations`, `visual_concerns`, `schematic_labels_identified`, `power_interface_labels_identified`, `connector_labels_identified`, `limitations`, `phase_13_completed`.
7. Required validation artifact: `exports/<project>-image-evidence-review-validation.json` with fields: `inventory_exists`, `required_fields_present`, `pages_actually_opened_count`, `phase_13_completed`, `overall_pass`.
8. A file-size or filename listing alone is not sufficient evidence of image review.
9. Use PNGs for visual/context evidence: schematic labels, connector labels, power/interface labels, page context, physical grouping, and obvious visual concerns.
10. Do not derive distances, clearances, trace widths, or coordinates from PNG pixels.
11. Image-render fallback means using an alternate renderer (for example PyMuPDF) to produce PNG evidence; JSON-only fallback means proceeding without image evidence.
12. These require separate approval; `user_approved_fallback=true` is only for image-render fallback and does not imply JSON-only approval.
13. If PDFs are present but PNGs are missing after converter execution, stop and report an image-rendering blocker. Proceed without PNG evidence only if `json_only_review_approved=true` and the user provided explicit approval in a new message after the blocker was reported.
14. Image gate is mandatory:
   - schematic PDFs present require schematic PNGs
   - layout/Gerber/PCB PDFs present require layout/Gerber/PCB PNGs
   - no silent JSON-only fallback
15. `phase_13_completed=true` must be set by actual image inspection; it must not be carried over from the Workflow 6 artifact.
16. Workflow 12 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false` when PDFs/images are required, remain in Workflow 12. Repair image inspection or stop for explicit fallback approval. Do not proceed to datasheet review or candidate findings.

## Workflow 13: Review Datasheet Evidence FULL

1. Inspect local/retrieved datasheets actually available.
2. Use only local saved datasheet files as evidence.
3. Cite local datasheet filename and page/section when practical.
4. Record missing/ambiguous datasheets from the manifest as evidence limitations.
5. Do not use web snippets or search-result text as evidence.
6. Extract the following parameters for Cluster 4 Rules where datasheets are available (all must be assessed or explicitly noted as not-found):
   - **Capacitors**: Dielectric type (Y5V/X5R/C0G) and DC bias derating (COMP_CAP_001, COMP_CAP_002), leakage (COMP_CAP_003), voltage rating margin (COMP_CAP_004, SCH_POL_001), Ripple current (COMP_CAP_005), ESR/ESL (COMP_CAP_006).
   - **Inductors**: Tolerance (COMP_IND_001), Saturation current vs calculated peak (COMP_IND_002, PWR_RATING_001), SRF (COMP_IND_003), Q-factor (COMP_IND_004).
   - **Resistors**: Film type / 1/f noise (COMP_RES_001, COMP_RES_002), Power rating margin (COMP_RES_003), High-frequency inductance (COMP_RES_004).
   - **Semiconductors**: FET/Diode voltage margin (PWR_RATING_002), Op-Amp common-mode (AN_OPAMP_001), ADC driver bandwidth (AN_ADC_002).
   - **Metadata & Math**: Sanity check text values (SCH_VAL_001), verify MPNs/Order codes exist (DFM_BOM_001).
7. Required artifact: `exports/<project>-datasheet-evidence-review.json` with fields: `datasheets_reviewed`, `components_with_voltage_rating_verified`, `components_with_saturation_current_verified`, `components_with_capacitor_dielectric_verified`, `components_with_dc_bias_derating_verified`, `components_with_thermal_data_extracted`, `aero_lead_finish_designators_found`, `component_mass_records`, `evidence_gaps`.
8. Required validation artifact: `exports/<project>-datasheet-evidence-review-validation.json` with fields: `inventory_exists`, `required_fields_present`, `datasheets_reviewed_count`, `overall_pass`.
9. Workflow 13 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 13 and repair before proceeding.

## Workflow 14: Review Aerospace and Process Metadata

1. This workflow is required for all designs. When aerospace/process inputs are absent, explicitly document each absence as missing evidence for all AERO_* rules.
2. Inspect aerospace certification documentation and process metadata against KB Appendix K requirements.
3. Accepted aerospace/process inputs (use what is available under `input/`):
   - Fab work order or board-build specification (solder alloy, IPC class)
   - Conformal coating specification document (masking requirements)
   - Environmental or vibration profile document (vibration profile type)
   - Chassis-mounting drawing (chassis-bond point identification)
   - Assembly work instructions
4. Assess all KB Appendix K / Cluster 5 check targets or explicitly mark each missing-evidence/[UNVERIFIABLE]:
   - **Board Materials**: Stackup dielectric definition (HS_MAT_001).
   - **Aerospace Process**: Solder alloy spec & IPC Class (AERO_SLD_001), Conformal coat masks (AERO_TERM_001), Lead-finish qualification (AERO_SLD_001).
   - **Vibration & Mass**: Component mass > 3g vs vibration profile (AERO_VIB_001). *Note: [UNVERIFIABLE] if mass is missing from BOM.*
   - **Logs & Project Mgmt**: Verify native DRC/ERC runs (DFT_DRC_001, DFT_DRC_002, DFT_CONN_001).
   - **Physical Testing Constraints**: Instantly flag the following rules as [UNVERIFIABLE] "Skipped: Requires Physical Prototype / Testing": Thermal dissipation logic (THM_DISS_001, THM_RISE_001, THM_HEAT_001, THM_COOL_001), and Build/Measure validations (DFT_BUILD_001, DFT_MEAS_001, DFT_PROD_001).
5. Required artifact: `exports/<project>-aerospace-evidence-inventory.json` with fields: `fab_work_order_present`, `solder_alloy_specified`, `ipc_class_specified`, `lead_finish_qualifications_reviewed`, `conformal_coating_spec_present`, `masking_requirements_documented`, `environmental_profile_present`, `vibration_profile_type`, `component_mass_records_reviewed`, `mass_over_threshold_count`, `chassis_mounting_drawing_present`, `chassis_bond_point_count`, `aero_evidence_gaps`, `aero_limitations`.
6. Required validation artifact: `exports/<project>-aerospace-evidence-inventory-validation.json` with fields: `inventory_exists`, `required_fields_present`, `aero_categories_assessed_or_marked_missing`, `overall_pass`.
7. Absence of aerospace documentation is not a workflow failure; record absence as missing evidence in `aero_evidence_gaps`.
8. Workflow 14 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 14 and create the inventory with explicit missing-evidence records.

## Workflow 15: Cross-Source Consistency Review

1. Cross-check evidence across:
   - schematic JSON
   - board JSON
   - stack JSON
   - BOM JSON
   - conversion reports
   - PNG images
   - datasheets

2. **REQUIRED: Run cross-check analysis tool**:
   Execute `python scripts/cross_check_helpers.py --bom exports/<project>-bom.json --sch exports/<project>-thomson-export-sch.json --brd exports/<project>-thomson-export-brd.json --json` to perform deterministic cross-source verification.
   
   **What this analyzes (all checks run by default):**
   - RefDes reconciliation (tripartite set matching)
   - Package mismatches (DFM_LIB_002)
   - Netlist topology verification (SCH_NET_001)
   - Voltage derating margins (SCH_POL_001, COMP_CAP_002)
   
   **Individual check flags (optional):**
   ```bash
   # RefDes tripartite matching (BOM ∩ SCH ∩ BRD)
   python scripts/cross_check_helpers.py --bom <bom> --sch <sch> --brd <brd> --run-reconciliation --json
   
   # Package mismatch detection (DFM_LIB_002)
   python scripts/cross_check_helpers.py --bom <bom> --brd <brd> --check-packages --json
   
   # Netlist topology verification (SCH_NET_001)
   python scripts/cross_check_helpers.py --sch <sch> --brd <brd> --verify-netlist --json
   
   # Voltage derating validation (SCH_POL_001, COMP_CAP_002)
   python scripts/cross_check_helpers.py --bom <bom> --sch <sch> --verify-derating --json
   ```
   
   **Output:** LLM-optimized JSON with precise discrepancy reporting:
   - RefDes in BOM but not in SCH/BRD (and vice versa)
   - Package name mismatches (BOM vs BRD footprint)
   - Net connectivity differences (SCH pins vs BRD pads)
   - Insufficient voltage margins (rated vs applied voltage)
   
   **Rule-to-Tool Mapping:**
   - RefDes consistency: `--run-reconciliation`
   - DFM_LIB_002 (package mismatch): `--check-packages`
   - SCH_NET_001 (netlist sync): `--verify-netlist`
   - SCH_POL_001, COMP_CAP_002 (derating): `--verify-derating`

3. Check consistency areas for Cluster 6 Rules:
   - **Pin & Pad Mapping**: Schematic symbol pins vs Datasheet PDF (SCH_SYMBOL_001). Layout footprint pad numbers vs Datasheet mechanical drawing (DFM_LIB_002).
   - **Orientation**: Connector pinout (Pin 1) vs cable harness specs (DFM_LIB_003).
   - **BOM vs Layout**: BOM vs schematic refdes coverage; BOM vs board package coverage.
   - **Physical Print ([UNVERIFIABLE])**: Instantly flag Print 1:1 scale (DFM_LIB_001) as "Skipped: Impossible for AI".
   - **Routing vs Ratings**: Inductor Isat (Datasheet) vs calculated peak (Schematic) (PWR_RATING_001). Capacitor bias derating (Datasheet) vs supply voltage (Schematic) (COMP_CAP_001). Material (Stackup) vs high-speed signal presence (Board) (HS_MAT_001).
   - conversion warnings vs evidence reliability
4. Use `verified_checks` and `cross_checks` for checked-good or broad analyses.
5. Required artifact: `exports/<project>-cross-source-review.json` with fields: `bom_schematic_consistency`, `bom_board_consistency`, `power_net_routing_consistency`, `protection_evidence_consistency`, `regulator_layout_consistency`, `differential_routing_consistency`, `datasheet_rating_cross_checks`, `material_signal_cross_check`, `conversion_warning_assessment`, `cross_source_limitations`, `evidence_paths_used`.
6. Required validation artifact: `exports/<project>-cross-source-review-validation.json` with fields: `inventory_exists`, `required_fields_present`, `cross_check_categories_assessed`, `overall_pass`.
7. Workflow 15 passes only when both artifacts exist, parse successfully, and `overall_pass=true`. If either artifact is missing or `overall_pass=false`, remain in Workflow 15 and repair before proceeding.

## Workflow 16: Pre-Findings Gate Check

Required artifact: `exports/<project>-pre-findings-gate.json`. Findings JSON must not be created until this file exists and `overall_gate_pass=true`. This gate must not require findings validation or report generation artifacts.

1. Verify converter completed.
2. Verify JSON exports load.
3. Verify PNG image gate passed.
4. Verify datasheet manifest exists and datasheet manifest validation `overall_pass=true`. Read `overall_pass` directly from `exports/datasheets/datasheet_manifest_validation.json` to set `datasheet_manifest_validation_pass`; do not invent or infer this value from any other source.
5. Verify schematic evidence inventory exists and `exports/<project>-schematic-evidence-inventory-validation.json overall_pass=true`.
6. Verify board evidence inventory exists and `exports/<project>-board-evidence-inventory-validation.json overall_pass=true`.
7. Verify DFM evidence inventory exists and `exports/<project>-dfm-evidence-inventory-validation.json overall_pass=true`.
8. Verify BOM evidence inventory exists and `exports/<project>-bom-evidence-inventory-validation.json overall_pass=true`.
9. Verify image evidence inventory exists when images are required (Workflow 6 artifact).
10. Verify image evidence review exists and `exports/<project>-image-evidence-review-validation.json overall_pass=true` when images are required (Workflow 12 artifact).
11. Verify image evidence review `phase_13_completed=true` when images are required.
12. Verify datasheet evidence review exists and `exports/<project>-datasheet-evidence-review-validation.json overall_pass=true`.
13. Verify aerospace evidence inventory exists and `exports/<project>-aerospace-evidence-inventory-validation.json overall_pass=true`.
14. Verify cross-source review exists and `exports/<project>-cross-source-review-validation.json overall_pass=true`.
15. Verify stackup completeness status recorded.
16. Verify framework inspection completed.
17. Verify no hard blocker remains.
18. Blocker rule: If any item fails, stop before Candidate Finding Development.
19. If `exports/<project>-pre-findings-gate.json` is missing or `overall_gate_pass=false`, remain in Pre-Findings Gate Check. Do not create candidate findings or findings JSON. The gate must identify which earlier workflow failed and list the workflow number that must be repaired.

## Workflow 17: Create Candidate Findings

1. Create candidate findings before writing final JSON.
2. Reject unsupported claims.
3. Reject vague "review this" findings.
4. Map candidates to ontology rule IDs, domains, and severities when possible.
5. Require concrete evidence before promoting a candidate to an issue.
6. Use examples/sample findings as style references only, not evidence.

## Workflow 18: Create Findings JSON

1. Write `exports/example-findings.json` or the matching project-prefixed findings file.
2. Use only schema-allowed fields.
3. Include concrete evidence in every finding.
4. Include recommended_actions for every issue.
5. Include `kb_references` when the ontology rule supplies them.
6. Include `verified_checks` and `cross_checks` if supported.
7. Do not apply an arbitrary count cap on issues. Include every concrete, non-duplicative, evidence-supported issue that satisfies schema and validation requirements.

## Workflow 19: Validate Findings

1. Run:

   ```bash
   python3 tools/validate_findings.py exports/example-findings.json
   ```

2. If validation fails:
   - read the error
   - fix only the findings JSON
   - rerun validation
   - repeat until validation passes
3. Do not bypass the validator.
4. Do not generate the report until validation passes.
5. If findings validation fails, remain in Validate Findings. Repair only the findings JSON. Do not modify schema, validator, ontology, examples, source evidence, or generated converter outputs.

## Workflow 20: Generate Report

Required command: `python3 tools/gen_report.py exports/example-findings.json --output exports` (or matching validated findings JSON project prefix while still using `tools/gen_report.py`). Required artifacts: `exports/<project>-review.html` and `exports/<project>-report-generation-validation.json`. Markdown-only report output is explicitly invalid.

1. Run report generation after findings validation passes using the repository report generator:

   ```bash
   python3 tools/gen_report.py <validated-findings-json> --output exports
   ```

2. The report phase is not complete unless an HTML report file exists under `exports/`.
3. A markdown report alone is not sufficient.
4. A text or markdown summary is allowed only as supplemental output, not as the final ThomsonLint report artifact.
5. The agent must verify the generated HTML report path exists before final summary.
6. Required report validation artifact: `exports/<project>-report-generation-validation.json` with:
   - `findings_json_path`
   - `validation_passed_before_report`
   - `report_command`
   - `html_report_path`
   - `html_report_exists`
   - `markdown_report_only_detected`
   - `overall_pass`
7. Report generation passes only if:
   - `validation_passed_before_report=true`
   - `html_report_exists=true`
   - `markdown_report_only_detected=false`
   - `overall_pass=true`
8. If the HTML report is missing, stop and repair report generation before final summary.
9. Do not mark the review complete if only `exports/review_report.md` exists.
10. Do not substitute markdown output for the required HTML report.
11. If `exports/<project>-review.html` is missing or `exports/<project>-report-generation-validation.json` is missing or `overall_pass=false`, remain in Generate Report. Re-run `tools/gen_report.py` or repair the report-generation step. Do not proceed to Final Summary.

## Evidence Rules

- Every finding must have concrete evidence.
- Image evidence must cite image filename and page or locator when available.
- JSON evidence must cite file, path, field, and value where practical.
- Datasheet evidence must cite local datasheet filename and page or section if available.
- Do not create findings from vague impressions.
- Do not create generic "review this" findings without a concrete reason.
- Do not derive distances, trace widths, clearances, or coordinates from PNG pixels; use JSON metrics for quantitative claims.
- Converter warnings are evidence-quality notes, not design issues by themselves.
- Each evidence review workflow must produce either candidate findings, `verified_checks`, `cross_checks`, or an explicit limitation/evidence-gap note.

**UNVERIFIABLE RULES DIRECTIVE**: 
Rules flagged as [UNVERIFIABLE] or [PARTIALLY VERIFIABLE] due to lack of 3D thermal simulation, physical printing requirements, subjective intent, or missing manual metadata (e.g., DFM_LIB_001, DFT_BUILD_001, DFT_MEAS_001, DFT_PROD_001, SCH_IC_001, SCH_OPT_001, THM_RISE_001, THM_HEAT_001, THM_COOL_001, AERO_VIB_001) must not be guessed or hallucinated. The agent must immediately output them as "Skipped: Unverifiable by AI / Requires Physical Testing / Requires 3D CAD" (or similar explicit limitation) in the final findings JSON or evidence inventory rather than attempting to forge a pass/fail condition.

## Non-Goals / Limits

Do not claim any of the following unless repository tools and concrete evidence explicitly support the conclusion:

- True clearance DRC.
- Exact spacing verification.
- Net-short proof.
- Impedance verification.
- Skew/timing verification.
- Polygon boolean connectivity.
- Annular-ring validation.
- Soldermask validation.
- Manufacturing signoff.
- Electrical signoff.

## Agent Safety Rules

- Do not modify git state.
- Do not commit.
- Do not push.
- Do not install packages unless required local tooling cannot run and no fallback exists.
- Do not delete input files.
- Do not delete source code.
- Do not rewrite the validator or schema to make invalid findings pass.
- Do not bypass `tools/validate_findings.py`.
- Keep generated files under `exports/`.

## Final Agent Response Format

Final summary may only be produced if these are true: `exports/<project>-phase-checkpoints.jsonl` exists; all required phase rows exist; all phase rows have `phase_passed=true`; `exports/tool-preflight-status.json overall_pass=true`; `exports/datasheets/datasheet_manifest_validation.json overall_pass=true`; `exports/<project>-schematic-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-board-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-dfm-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-bom-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-image-evidence-inventory.json overall_pass=true` when PDFs/images are required; `exports/<project>-image-evidence-review-validation.json overall_pass=true` when PDFs/images are required; `exports/<project>-datasheet-evidence-review-validation.json overall_pass=true`; `exports/<project>-aerospace-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-cross-source-review-validation.json overall_pass=true`; `exports/<project>-pre-findings-gate.json overall_gate_pass=true`; findings JSON exists and validator passed; `exports/<project>-report-generation-validation.json overall_pass=true`; and `exports/<project>-review.html` exists. If any item fails, do not write a completion summary and write `INVALID RUN SUMMARY` instead.

When finished, report:

- Converter command run.
- Converter output summary.
- Framework files inspected.
- Schematic evidence files inspected.
- Board/layout evidence files inspected.
- Stackup evidence files inspected.
- BOM evidence files inspected.
- Conversion report files inspected.
- Image pages inspected.
- Datasheet retrieval method: local, SearXNG MCP, unavailable, or skipped.
- poppler-utils install attempted: yes/no.
- pdftoppm available: yes/no.
- pdfinfo available: yes/no.
- Image rendering status.
- Image fallback approved by user: yes/no.
- Board JSON full evaluation performed: yes/no.
- Board evidence inventory path.
- Board JSON sections inspected.
- Board JSON sections unavailable or unsupported.
- Whether any board findings were limited by missing data.
- Total BOM line items.
- Datasheet manifest rows count.
- Local datasheets reused count.
- Retrieved datasheets count.
- Ambiguous datasheet count.
- Missing datasheet count.
- not_applicable_generic count.
- Datasheet manifest path.
- Datasheets cited in findings.
- Candidate URL/download failure summary.
- Stackup source used.
- Stackup completeness status.
- Missing stackup fields.
- Whether impedance evidence was available.
- Stackup limitations.
- Findings count.
- `verified_checks` count if present.
- `cross_checks` count if present.
- Validation command and result.
- Report generation command and result.
- Generated report path.
- Limitations and skipped checks.


## Required Final Response Format Additions

Datasheets:
- datasheet manifest validation path
- datasheet manifest validation overall_pass
- status=found rows with existing local file count
- status=found rows missing local file count
- discovered URL only count
- download unavailable count

Schematic:
- schematic evidence inventory validation path
- schematic evidence inventory validation overall_pass

Board:
- board evidence inventory validation path
- board evidence inventory validation overall_pass

DFM:
- DFM evidence inventory validation path
- DFM evidence inventory validation overall_pass

BOM:
- BOM evidence inventory validation path
- BOM evidence inventory validation overall_pass

Images:
- image evidence inventory path
- image evidence inventory created: yes/no
- image evidence review path
- image evidence review phase_13_completed: yes/no
- image pages actually inspected count

Datasheet Evidence Review:
- datasheet evidence review validation path
- datasheet evidence review validation overall_pass

Aerospace:
- aerospace evidence inventory validation path
- aerospace evidence inventory validation overall_pass
- aerospace documentation present: yes/no
- aerospace evidence gaps documented: yes/no

Cross-Source:
- cross-source review validation path
- cross-source review validation overall_pass

Pre-findings gate:
- pre-findings gate passed: yes/no
- any blockers remaining before findings: yes/no

Report:
- report generation validation path
- report generation validation overall_pass
- HTML report path
- HTML report exists: yes/no
- markdown-only report detected: yes/no
