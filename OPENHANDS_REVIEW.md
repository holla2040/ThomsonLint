# OpenHands ThomsonLint Review Workflow

## Purpose


## Artifact-Based Phase Completion Rule

A phase may not be marked complete based only on narrative text. If the phase defines a required artifact or validation JSON, that artifact must exist on disk, parse successfully if JSON, and contain the required pass field set to true before the phase can be marked complete. Verbal claims such as "phase complete", "gate passed", or "reviewed" are invalid unless backed by the required artifact.

Universal phase checkpoint artifact: `exports/<project>-phase-checkpoints.jsonl`.
Every phase must append exactly one JSONL checkpoint row before moving to the next phase. Each row must include: `phase_number`, `phase_name`, `started_at_utc`, `completed_at_utc`, `required_artifacts`, `artifacts_verified`, `validation_artifacts`, `validation_passed`, `blockers`, `phase_passed`.
Rules: a phase is not complete unless its checkpoint row exists and `phase_passed=true`; if a phase has no separate artifact, the checkpoint row itself is the required artifact; phases 8 through 14 must each have a distinct checkpoint row; phases 16 and 17 must each have a distinct checkpoint row; the agent must not mark multiple phases complete with one shared checkpoint row; narrative text is not a checkpoint.


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
8. JSON-only review requires `json_only_review_approved=true` in `exports/tool-preflight-status.json` and explicit user approval in a new message after the blocker is reported.
9. Do not treat image-render fallback approval as JSON-only approval.
10. Required artifact: `exports/<project>-image-evidence-inventory.json` with fields `pdf_sources`, `conversion_tool`, `fallback_used`, `user_approved_fallback`, `total_pages_expected`, `total_pages_rendered`, `output_files`, `schematic_pngs`, `layout_pngs`, `pages_inspected`, `page_roles_or_labels_if_identifiable`, `visual_context_notes`, `limitations`, `confirmation_no_pixel_quantitative_claims`, `overall_pass`.
11. File names and file sizes alone are not sufficient image review.
12. If PDFs are present, `total_pages_rendered` must be greater than zero and equal `total_pages_expected` unless an explicit limitation is recorded.
13. If `fallback_used=true`, then `user_approved_fallback` must be true.
14. If PDFs are present and no PNG evidence can be produced, stop unless `json_only_review_approved=true`.
15. If `overall_pass` is not true, do not proceed to evidence review or candidate findings.

## Workflow 7: Review Schematic Evidence FULL

1. Inspect generated schematic JSON.
2. Review components, refdes coverage, net names, power nets, external interfaces, connector nets, single-pin/unusual connections, and schematic-level evidence limitations.
3. Cite schematic JSON file/path/field/value where practical.
4. Use schematic PNGs only for visual/context confirmation, not quantitative claims.
5. Record checked-good items for `verified_checks` when useful.

## Workflow 8: Full Board/Layout JSON Evaluation

1. Inspect the full logical content of `exports/<project>-thomson-export-brd.json`.
2. Full board JSON evaluation is required; summary-only extraction/review is forbidden.
3. If board JSON is too large to open directly, use chunked or targeted programmatic inspection (Python/jq-style traversal). Do not reduce review to top-level summary only.
4. Required inspection categories:
   - top-level keys and export metadata
   - layer list and layer types
   - units and coordinate system
   - board outline if present
   - components/footprints/packages if present
   - pads and pad primitives
   - vias and holes
   - plated vs non-plated holes
   - nets and net classes if present
   - copper routes
   - route width by net
   - route length by net
   - route length by layer
   - polygons/copper areas if present
   - plane or copper pour indicators if present
   - non-copper geometry
   - silkscreen/mechanical features if present
   - test points and debug pads if present
   - connector footprints and external-interface placement context
   - differential/paired-net candidates and routing evidence
   - power-net routing/width evidence
   - conversion limitations and missing fields
5. Produce a board evidence inventory file under `exports/`: `exports/<project>-board-evidence-inventory.json` (required, exact path must be recorded).
6. Board evidence inventory must include: `source_board_json`, `generated_timestamp`, `board_json_loaded`, `inspected_sections`, `unavailable_sections`, `object_counts`, `layer_count`, `net_count`, `route_count`, `via_count`, `hole_count`, `component_count_if_available`, `route_width_summary`, `route_length_summary`, `candidate_differential_or_paired_nets`, `candidate_power_nets`, `candidate_connector_or_interface_nets`, `candidate_test_or_debug_features`, `conversion_limitations`, `missing_or_unsupported_fields`, and `evidence_paths_used`.
7. Board evidence review checkpoint requires:
   - board JSON loaded successfully
   - required categories inspected or explicitly marked unavailable
   - board evidence inventory created and file existence verified
   - board evidence inventory validation artifact exists: `exports/<project>-board-evidence-inventory-validation.json` with `inventory_exists`, `required_fields_present`, `board_json_loaded`, `required_categories_inspected_or_marked_unavailable`, `overall_pass`
   - no findings written before board evidence inventory exists
   - if board evidence inventory validation fails, stop and repair before Candidate Finding Development or Findings JSON
   - if `exports/<project>-board-evidence-inventory.json` is not created, the agent must stop before candidate finding development
   - A printed summary table is not sufficient evidence of full board JSON evaluation. The required inventory JSON artifact must exist and pass validation.
8. Board JSON is exported geometry/routing evidence, not true DRC.
9. Do not claim exact clearance, net-short proof, annular-ring validation, soldermask validation, impedance verification, or manufacturing signoff unless explicit tool evidence supports it.

## Workflow 9: Review Stackup and Manufacturing Evidence

1. Inspect generated stack JSON.
2. Explicitly inspect candidate stackup sources: generated stack JSON, `input/stackup.csv`, `input/stackup.json`, fabrication drawing PDFs, ODB++ archive/folder if present, IPC-2581 stackup/cross-section content if present, and EDA-specific stackup reports if present.
3. ODB++ may be the preferred board/layout/fabrication source when present, but always inspect what stackup/material fields are actually present before making stackup claims.
4. IPC-2581 and ODB++ are both possible board/layout sources, but neither guarantees complete stackup/material/impedance data unless the export includes it.
5. If no explicit stackup source exists, mark stackup as missing evidence.
6. Layer names, Gerber filenames, ODB++ matrix layer names, IPC-2581 layer names, or PDF/Gerber page names alone are insufficient for dielectric thickness, copper weight, material system, Dk/Df, controlled impedance, finished board thickness, or manufacturing signoff.
7. Without explicit stackup/material/impedance evidence, do not claim impedance verification, stackup verification, manufacturing signoff, return-path quality beyond limited qualitative observations, exact dielectric spacing, exact layer construction, exact copper weight, or material/Dk/Df verification.
8. Report stackup completeness status as one of: `complete_explicit`, `partial_explicit`, `layer_order_only`, `missing`.
9. Status definitions and required terms:
   - `complete_explicit`: layer order/type, copper thickness/weight, dielectric thickness, and material/Dk or equivalent facts are available.
   - `partial_explicit`: some explicit stackup facts exist but key fields are missing.
   - `layer_order_only`: only layer names/order/types are available.
   - `missing`: no reliable explicit stackup source is available.
10. Recommended manual `stackup.csv` schema: `layer_index`, `layer_name`, `layer_type`, `material`, `thickness_mil`, `copper_oz`, `dielectric_dk`, `dielectric_df`, `notes`.
11. Optional `impedance_rules.csv` schema: `rule_name`, `net_class`, `target_ohms`, `tolerance_ohms`, `layer`, `width_mil`, `spacing_mil`, `reference_plane`, `notes`.
12. Final response must include: stackup source used, stackup completeness status, missing stackup fields, whether impedance evidence was available, and stackup limitations.

## Workflow 10: Review BOM and Component Evidence FULL

1. Inspect generated BOM JSON.
2. Review component list, refdes coverage, manufacturer/MPN/LCSC fields, quantity consistency, missing metadata, package information, and BOM/schematic/board consistency candidates.
3. Identify components that need datasheet evidence.
4. Do not infer datasheet parameters from vendor names or package names alone.

## Workflow 11: Review Image Evidence FULL

1. This workflow is required for deep-review runs when PDFs are present.
2. Inspect generated schematic PNGs.
3. Inspect generated layout/Gerber/PCB PNGs.
4. Record image pages inspected.
5. Image review must inspect actual generated PNGs, not only list filenames/sizes.
6. Required artifact: `exports/<project>-image-evidence-inventory.json`.
7. The image evidence inventory must include:
   - `schematic_pngs`
   - `layout_pngs`
   - `pages_inspected`
   - `page_roles_or_labels_if_identifiable`
   - `visual_context_notes`
   - `limitations`
   - `confirmation_no_pixel_quantitative_claims`
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
15. If image review is required and `exports/<project>-image-evidence-inventory.json` is not created, do not proceed to Candidate Finding Development.

## Workflow 12: Review Datasheet Evidence FULL

1. Inspect local/retrieved datasheets actually available.
2. Use only local saved datasheet files as evidence.
3. Cite local datasheet filename and page/section when practical.
4. Record missing/ambiguous datasheets from the manifest as evidence limitations.
5. Do not use web snippets or search-result text as evidence.

## Workflow 13: Cross-Source Consistency Review

1. Cross-check evidence across:
   - schematic JSON
   - board JSON
   - stack JSON
   - BOM JSON
   - conversion reports
   - PNG images
   - datasheets
2. Check consistency areas:
   - BOM vs schematic refdes coverage
   - BOM vs board component/package coverage
   - schematic power nets vs board routing/stack evidence
   - connector/interface nets vs ESD/protection evidence
   - regulator/power path schematic vs layout/context evidence
   - paired/differential candidates vs route length/width evidence
   - conversion warnings vs evidence reliability
3. Use `verified_checks` and `cross_checks` for checked-good or broad analyses.

## Workflow 14: Pre-Findings Gate Check

Required artifact: `exports/<project>-pre-findings-gate.json`. Findings JSON must not be created until this file exists and `overall_gate_pass=true`. This gate must not require findings validation or report generation artifacts.

1. Verify converter completed.
2. Verify JSON exports load.
3. Verify PNG image gate passed.
4. Verify datasheet manifest exists.
5. Verify datasheet manifest validation `overall_pass=true`.
6. Verify board evidence inventory exists.
7. Verify board evidence inventory validation `overall_pass=true`.
8. Verify image evidence inventory exists when images are required.
9. Verify stackup completeness status recorded.
10. Verify framework inspection completed.
11. Verify no hard blocker remains.
12. Blocker rule: If any item fails, stop before Candidate Finding Development.

## Workflow 15: Create Candidate Findings

1. Create candidate findings before writing final JSON.
2. Reject unsupported claims.
3. Reject vague "review this" findings.
4. Map candidates to ontology rule IDs, domains, and severities when possible.
5. Require concrete evidence before promoting a candidate to an issue.
6. Use examples/sample findings as style references only, not evidence.

## Workflow 16: Create Findings JSON

1. Write `exports/example-findings.json` or the matching project-prefixed findings file.
2. Use only schema-allowed fields.
3. Include concrete evidence in every finding.
4. Include recommended_actions for every issue.
5. Include `kb_references` when the ontology rule supplies them.
6. Include `verified_checks` and `cross_checks` if supported.
7. Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise.

## Workflow 17: Validate Findings

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

## Workflow 18: Generate Report

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

Final summary may only be produced if these are true: `exports/<project>-phase-checkpoints.jsonl` exists; all required phase rows exist; all phase rows have `phase_passed=true`; `exports/tool-preflight-status.json overall_pass=true`; `exports/datasheets/datasheet_manifest_validation.json overall_pass=true`; `exports/<project>-board-evidence-inventory-validation.json overall_pass=true`; `exports/<project>-image-evidence-inventory.json overall_pass=true` when PDFs/images are required; `exports/<project>-pre-findings-gate.json overall_gate_pass=true`; findings JSON exists and validator passed; `exports/<project>-report-generation-validation.json overall_pass=true`; and `exports/<project>-review.html` exists. If any item fails, do not write a completion summary and write `INVALID RUN SUMMARY` instead.

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

Board:
- board evidence inventory validation path
- board evidence inventory validation overall_pass

Images:
- image evidence inventory path
- image evidence inventory created: yes/no
- image pages actually inspected count

Pre-findings gate:
- pre-findings gate passed: yes/no
- any blockers remaining before findings: yes/no

Report:
- report generation validation path
- report generation validation overall_pass
- HTML report path
- HTML report exists: yes/no
- markdown-only report detected: yes/no
