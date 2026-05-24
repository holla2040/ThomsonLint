1. OBJECTIVE
Create a linear, deep, and checkpointed ThomsonLint execution plan that follows `OPENHANDS_REVIEW.md` as source of truth and prevents shortcutting across evidence classes.

2. CONTEXT SUMMARY
This plan enforces a strict order: inspect inputs first, then setup/tool preflight, then converter execution, then framework inspection, then datasheet retrieval as a normal numbered phase, followed by separate evidence-class reviews (schematic, board/layout, stackup, BOM, images, datasheets), then cross-source consistency, candidate development, findings JSON, validation, report generation, and final summary.

3. APPROACH OVERVIEW
Phase 1 — Ingest ThomsonLint Workflow
Phase 2 — Inspect Inputs and Datasheets
Phase 3 — Setup and Tool Preflight
Phase 4 — Run Integrated Converter
Phase 5 — Inspect Findings Framework
Phase 6 — Full BOM Datasheet Retrieval
Phase 7 — Enforce Image Review Gate
Phase 8 — Review Schematic Evidence FULL
Phase 9 — Full Board/Layout JSON Evaluation
Phase 10 — Review Stackup and Manufacturing Evidence FULL
Phase 11 — Review BOM and Component Evidence FULL
Phase 12 — Review Image Evidence FULL
Phase 13 — Review Datasheet Evidence FULL
Phase 14 — Cross-Source Consistency Review
Phase 15 — Pre-Findings Gate Check
Phase 16 — Candidate Finding Development
Phase 17 — Write Findings JSON
Phase 18 — Validate and Repair Findings
Phase 19 — Generate Report
Phase 20 — Final Summary

4. IMPLEMENTATION STEPS

## Phase 1 — Ingest ThomsonLint Workflow
- **Purpose**: Map `OPENHANDS_REVIEW.md` workflows to concrete actions and confirm phase order matches the numbered workflow order.
- **Files/tools to inspect/use**: `OPENHANDS_REVIEW.md`, `docs/REVIEWER_INSTRUCTIONS.md` (if present), `README.md` (if present).
- **Expected evidence/output**: Workflow-to-phase mapping table and explicit confirmation of the 1→19 linear sequence.
- **Validation/checkpoint before moving to next phase**: Mapping covers all workflows and preserves order without lettered side phases.
- **Risks or ways the agent could go wrong**: Inventing alternate sequence, skipping required workflows, or reintroducing side phases.

## Phase 2 — Inspect Inputs and Datasheets
- **Purpose**: Inspect `input/` and `datasheets/`, and record missing datasheets as evidence gaps rather than guessed values.
- **Files/tools to inspect/use**: `input/`, `datasheets/` (if present), explicit stackup inputs (`input/stackup.csv`, `input/stackup.json`, fab drawing PDFs, ODB++ archive/folder, IPC-2581 with cross-section, EDA stackup reports).
- **Expected evidence/output**: Complete file inventory and datasheet availability status.
- **Validation/checkpoint before moving to next phase**: At least one raw design input exists; datasheet gaps are explicitly recorded as missing evidence.
- **Risks or ways the agent could go wrong**: Guessing datasheet parameters or ignoring missing-evidence tracking.

## Phase 3 — Setup and Tool Preflight
- **Purpose**: Ensure required local tools are available before any converter execution.
- **Files/tools to inspect/use**: `python3`, `pdftoppm`, `pdfinfo`, Ubuntu/Debian package `poppler-utils`.
- **Expected evidence/output**: Tool availability results and installation attempt status.
- **Validation/checkpoint before moving to next phase**:
  - Check `which python3`, `which pdftoppm`, `which pdfinfo`.
  - If `pdftoppm` or `pdfinfo` missing, attempt `apt-get update && apt-get install -y poppler-utils`.
  - If `sudo` is required and available, attempt `sudo apt-get update && sudo apt-get install -y poppler-utils`.
  - Verify post-install with `which pdftoppm`, `which pdfinfo`, `pdftoppm -v`, `pdfinfo -v`.
  - If install fails or tools remain unavailable when PDFs are present, stop and report blocker; no silent JSON-only fallback unless user explicitly approves fallback.
- **Risks or ways the agent could go wrong**: Running converter before tool preflight, skipping install attempt, or proceeding after failed preflight.

## Phase 4 — Run Integrated Converter
- **Purpose**: Generate review artifacts before evidence analysis.
- **Files/tools to inspect/use**: `python3 tools/run_converter_pipeline.py input --project-name example --clean`, `exports/` outputs.
- **Expected evidence/output**: `exports/` created, JSON exports loadable, PNG renders present when PDFs exist, conversion report files inspected.
- **Validation/checkpoint before moving to next phase**: JSON parsing succeeds; report artifacts reviewed; converter warnings captured as evidence-quality notes.
- **Risks or ways the agent could go wrong**: Reviewing before conversion, stale exports, or treating converter warnings as automatic findings.

## Phase 5 — Inspect Findings Framework
- **Purpose**: Determine valid finding structure, issue fields, evidence row format, `verified_checks`, `cross_checks`, severity, domains, and rule IDs.
- **Files/tools to inspect/use**: `tests/findings_schema.json`, `tests/sample_findings.json`, `ontology/ontology.json`, `examples/examples.json`, `tools/validate_findings.py`, `tools/gen_report.py`.
- **Expected evidence/output**: Definitive schema/validator constraints and allowed ontology values.
- **Validation/checkpoint before moving to next phase**: Required/optional fields and accepted enumerations documented and consistent across schema + validator + ontology.
- **Risks or ways the agent could go wrong**: Using invalid severities/domains/rule IDs, missing required fields, or inventing schema fields.

## Phase 6 — Full BOM Datasheet Retrieval
- **Purpose**: Build a datasheet manifest for every BOM line item and attempt full BOM datasheet coverage.
- **Files/tools to inspect/use**: `exports/<project>-bom.json`, schematic/component exports for context, local `datasheets/`, SearXNG MCP (if available), `exports/datasheets/`.
- **Expected evidence/output**: `exports/datasheets/datasheet_manifest.jsonl` with one manifest row for every BOM line item (or clearly grouped equivalent row), plus locally saved datasheets for `local`/`found` items.
- **Validation/checkpoint before moving to next phase**:
  - Manifest coverage checkpoint: every BOM line item is represented.
  - Retrieved evidence checkpoint: all `found` datasheets are saved under `exports/datasheets/`.
  - Status values limited to `local`, `found`, `ambiguous`, `missing`, `not_applicable_generic`.
  - No browser Google search; no Tavily unless user explicitly requests it.
  - Search snippets are not evidence.
  - If first URL fails, do not give up; attempt additional candidate URLs with bounded multi-attempt logic (for example up to 3–5 candidates).
- **Risks or ways the agent could go wrong**: Incomplete BOM accounting, premature `missing` labels, untrusted source selection, or unbounded URL retry loops.


- **Hard definitions**:
  - `discovered_url`: A candidate datasheet URL found by SearXNG MCP or another approved discovery path. This is not evidence and does not count as found.
  - `downloaded_datasheet`: A datasheet file saved locally under `exports/datasheets/`. Only this can satisfy `status=found` or be cited as datasheet evidence.
- **Hard rules**:
  - A BOM row must not be marked status=found unless local_saved_filename is populated and that file exists under exports/datasheets/.
  - If candidate URLs are discovered but no local file is saved, the manifest row status must be ambiguous or missing, not found.
  - Do not write "datasheets available online" as equivalent to found; this is discovered_url only.
  - If environment download is unavailable, set status to ambiguous/missing and include status_note: "download unavailable in environment".
  - The agent must not continue past Full BOM Datasheet Retrieval while any status=found row points to a missing local file.
- **Required manifest validation** (must run before evidence review):
  - load `exports/datasheets/datasheet_manifest.jsonl`
  - count BOM rows from `exports/<project>-bom.json`
  - verify every BOM row has a manifest row or clearly grouped equivalent row
  - verify every status is one of `local`, `found`, `ambiguous`, `missing`, `not_applicable_generic`
  - verify every status=local row has an existing local_saved_filename
  - verify every status=found row has an existing local_saved_filename under `exports/datasheets/`
  - verify candidate_urls are recorded for web-discovered rows
  - verify failed candidate URLs are recorded when download attempts fail
  - fail if any status=found row lacks a local file
- **Required artifact**: `exports/datasheets/datasheet_manifest_validation.json` with:
  `total_bom_line_items`, `manifest_rows`, `local_count`, `found_count`, `ambiguous_count`, `missing_count`, `not_applicable_generic_count`, `status_found_missing_local_file_count`, `missing_local_files`, `coverage_pass`, `local_file_validation_pass`, `overall_pass`.
- **Pass criteria**: Full BOM Datasheet Retrieval passes only if `coverage_pass=true`, `local_file_validation_pass=true`, and `overall_pass=true`.
- **Blocker**: If manifest validation fails, stop and repair manifest and/or downloads before Review Datasheet Evidence, Cross-Source Consistency Review, Candidate Finding Development, or Findings JSON.
- **Coverage strictness**: Full BOM retrieval means every BOM line item is represented. It is not complete if only ICs/easy URLs are covered, if generic parts are omitted instead of `not_applicable_generic`, or if test points/connectors/mechanical parts are omitted instead of classified.

## Phase 7 — Enforce Image Review Gate
- **Purpose**: Enforce PNG evidence readiness for deep review runs.
- **Files/tools to inspect/use**: `exports/` PNG artifacts; `pdftoppm`/`pdfinfo` when relevant.
- **Expected evidence/output**: Verified schematic and layout/Gerber/PCB PNG presence when PDFs are present.
- **Validation/checkpoint before moving to next phase**: If PDFs exist but PNGs are missing, stop unless user explicitly approves JSON-only fallback.
- **Risks or ways the agent could go wrong**: Quietly skipping image gate or claiming image review without real renders.

## Phase 8 — Review Schematic Evidence FULL
- **Purpose**: Perform schematic evidence review.
- **Files/tools to inspect/use**: Generated schematic JSON, schematic PNG context if relevant.
- **Expected evidence/output**: Coverage of components, nets, power nets, external interfaces, connector nets, unusual connections, and limitations.
- **Validation/checkpoint before moving to next phase**: Findings/checks/limitations include schematic citations with file/path/field/value where practical.
- **Risks or ways the agent could go wrong**: Vague schematic claims or quantitative claims from PNG-only evidence.

## Phase 9 — Full Board/Layout JSON Evaluation
- **Purpose**: Perform full board/layout JSON evaluation using complete logical content, not summary-only extraction.
- **Files/tools to inspect/use**: `exports/<project>-thomson-export-brd.json`, targeted Python/jq-style traversal for large files, layout PNG context if relevant.
- **Expected evidence/output**: `exports/<project>-board-evidence-inventory.json` plus full-category inspection coverage.
- **Validation/checkpoint before moving to next phase**:
  - Full Board/Layout JSON Evaluation is not complete unless `exports/<project>-board-evidence-inventory.json` exists.
  - Record the exact board evidence inventory path.
  - A printed summary table is not sufficient evidence of full board JSON evaluation. The required inventory JSON artifact must exist and pass validation.
  - Board evidence inventory must contain required fields: `source_board_json`, `generated_timestamp`, `board_json_loaded`, `inspected_sections`, `unavailable_sections`, `object_counts`, `layer_count`, `net_count`, `route_count`, `via_count`, `hole_count`, `component_count_if_available`, `route_width_summary`, `route_length_summary`, `candidate_differential_or_paired_nets`, `candidate_power_nets`, `candidate_connector_or_interface_nets`, `candidate_test_or_debug_features`, `conversion_limitations`, `missing_or_unsupported_fields`, `evidence_paths_used`.
  - Required validation artifact: `exports/<project>-board-evidence-inventory-validation.json` with `inventory_exists`, `required_fields_present`, `board_json_loaded`, `required_categories_inspected_or_marked_unavailable`, `overall_pass`.
  - If board evidence inventory validation fails, stop and repair before Candidate Finding Development or Findings JSON.
  - Board JSON loaded successfully.
  - Required categories inspected or explicitly marked unavailable: metadata, layers, units/coords, outline, components/footprints/packages, pads, vias/holes, plated vs non-plated, nets/net classes, routes, route width by net, route length by net/layer, polygons/copper areas, pour indicators, non-copper geometry, silkscreen/mechanical, test/debug features, connector/interface context, differential/paired candidates, power-net routing evidence, conversion limitations/missing fields.
  - Board evidence inventory created with counts/summaries/candidate groups/missing fields/evidence paths.
  - No findings written before board evidence inventory exists.
  - Board JSON is geometry/routing evidence, not true DRC; do not claim exact clearance, net-short proof, annular-ring, soldermask, impedance verification, or manufacturing signoff without explicit tool evidence.
- **Risks or ways the agent could go wrong**: Summary-only review, missing large-file sections, or over-claiming DRC/manufacturing conclusions.

## Phase 10 — Review Stackup and Manufacturing Evidence FULL
- **Purpose**: Review stackup facts and manufacturing evidence limits with explicit source and fallback reporting.
- **Files/tools to inspect/use**: Generated stack JSON, `input/stackup.csv`, `input/stackup.json`, fabrication drawing PDFs with stackup tables, ODB++ archive/folder when present, IPC-2581 stackup/cross-section content when present, and EDA/fab stackup reports (Allegro/OrCAD, Altium, PADS, KiCad) when present.
- **Expected evidence/output**: Reported stackup source used, whether generated stack JSON exists, whether explicit `stackup.csv` or `stackup.json` exists, whether ODB++ exists, whether EDA/fab stackup report exists, stackup completeness status, missing stackup fields, impedance-evidence availability, and stackup limitations.
- **Validation/checkpoint before moving to next phase**:
  - Stackup completeness status must be one of `complete_explicit`, `partial_explicit`, `layer_order_only`, `missing`.
  - If no explicit stackup source exists, mark stackup as missing evidence.
  - Do not claim impedance verification, stackup verification, or manufacturing signoff without explicit stackup/material/impedance evidence.
  - Layer names/order/files alone are insufficient for dielectric thickness, copper weight, Dk/Df, controlled impedance, finished thickness, or manufacturing signoff.
- **Risks or ways the agent could go wrong**: Inferring stackup from naming conventions, overstating impedance/manufacturing confidence, or omitting limitations.

## Phase 11 — Review BOM and Component Evidence FULL
- **Purpose**: Review BOM quality and component metadata completeness.
- **Files/tools to inspect/use**: Generated BOM JSON.
- **Expected evidence/output**: Refdes coverage, MPN/LCSC/manufacturer fields, quantity consistency, package metadata, and datasheet-needed component candidates.
- **Validation/checkpoint before moving to next phase**: BOM inconsistencies and metadata gaps documented with citations.
- **Risks or ways the agent could go wrong**: Inferring electrical limits from package/vendor text alone.

## Phase 12 — Review Image Evidence FULL

Image review requirements:
- Image gate verifies files exist.
- Image review must inspect actual generated PNGs, not only list filenames/sizes.
- Required artifact: `exports/<project>-image-evidence-inventory.json` containing `schematic_pngs`, `layout_pngs`, `pages_inspected`, `page_roles_or_labels_if_identifiable`, `visual_context_notes`, `limitations`, `confirmation_no_pixel_quantitative_claims`.
- If image review is required and `image-evidence-inventory.json` is not created, do not proceed to Candidate Finding Development.

- **Purpose**: Review PNG evidence as visual/context support.
- **Files/tools to inspect/use**: Generated schematic and layout/Gerber/PCB PNG files.
- **Expected evidence/output**: Recorded image pages inspected plus visual/context observations.
- **Validation/checkpoint before moving to next phase**: Only qualitative/context conclusions from PNGs; no quantitative pixel-derived metrics.
- **Risks or ways the agent could go wrong**: Deriving dimensions/clearance/width from pixel measurements.

## Phase 13 — Review Datasheet Evidence FULL
- **Purpose**: Review available local datasheet evidence.
- **Files/tools to inspect/use**: Local datasheets under `datasheets/` or `exports/datasheets/`, plus manifest.
- **Expected evidence/output**: Datasheet-backed checks/findings with filename/page/section citations and explicit missing/ambiguous records.
- **Validation/checkpoint before moving to next phase**: Only local saved datasheets are cited; snippets/search-result text excluded.
- **Risks or ways the agent could go wrong**: Citing web snippets or unverified part matches.

## Phase 14 — Cross-Source Consistency Review
- **Purpose**: Cross-check schematic, board, stack, BOM, conversion reports, PNGs, and datasheets.
- **Files/tools to inspect/use**: All generated JSON artifacts, conversion reports, image artifacts, local datasheets.
- **Expected evidence/output**: Cross-check coverage for:
  - BOM vs schematic
  - BOM vs board
  - power nets vs board/stack evidence
  - connector/interface nets vs protection evidence
  - regulator/power path schematic vs layout context
  - paired/differential candidates vs routing evidence
  - conversion warnings vs evidence reliability
- **Validation/checkpoint before moving to next phase**: Cross-source conclusions are evidence-backed and limitations are explicit where evidence is incomplete.
- **Risks or ways the agent could go wrong**: Single-source conclusions presented as cross-source facts.

## Phase 15 — Pre-Findings Gate Check
- **Purpose**: Block findings work until all required artifacts and hard gates pass.
- **Validation/checkpoint before moving to next phase**:
  - converter completed
  - JSON exports load
  - PNG image gate passed
  - datasheet manifest exists
  - datasheet manifest validation `overall_pass=true`
  - board evidence inventory exists
  - board evidence inventory validation `overall_pass=true`
  - image evidence inventory exists when images are required
  - stackup completeness status recorded
  - framework inspection completed
  - no hard blocker remains
- **Blocker rule**: If any item fails, stop before Candidate Finding Development. The agent must not proceed to candidate findings without board evidence inventory, and must not proceed without image evidence inventory when images are required.

## Phase 16 — Candidate Finding Development
- **Purpose**: Develop candidate findings before writing final JSON.
- **Files/tools to inspect/use**: Phase 8–14 evidence plus `ontology/ontology.json` and `examples/examples.json` (style/rule mapping only).
- **Expected evidence/output**: Evidence-cited candidate set mapped to rule/domain/severity where possible.
- **Validation/checkpoint before moving to next phase**: Unsupported or vague candidates rejected; concrete citations required.
- **Risks or ways the agent could go wrong**: Promoting weak/vague ideas to issues.

## Phase 17 — Write Findings JSON
- **Purpose**: Create findings JSON using schema-allowed fields only.
- **Files/tools to inspect/use**: Findings schema, validator expectations, generated evidence sources.
- **Expected evidence/output**: Findings JSON with `issues`, `evidence`, `recommended_actions`, and `verified_checks`/`cross_checks`/`source_documents` as supported.
- **Validation/checkpoint before moving to next phase**: Findings writing occurs after all evidence-review phases; `issues[]` limited to 15 high-signal items unless user requests otherwise.
- **Risks or ways the agent could go wrong**: Writing findings too early or violating schema.

## Phase 18 — Validate and Repair Findings
- **Purpose**: Validate findings and repair only findings JSON until pass.
- **Files/tools to inspect/use**: `python3 tools/validate_findings.py exports/example-findings.json` (or matching project prefix).
- **Expected evidence/output**: Validation pass output.
- **Validation/checkpoint before moving to next phase**: Validator succeeds with no bypass.
- **Risks or ways the agent could go wrong**: Editing framework files instead of findings JSON.

## Phase 19 — Generate Report
- **Purpose**: Generate report only after validation passes.
- **Files/tools to inspect/use**: `python3 tools/gen_report.py exports/example-findings.json --output exports` (or matching project prefix).
- **Expected evidence/output**: HTML report path under `exports/`.
- **Validation/checkpoint before moving to next phase**: Report generation is strictly post-validation.
- **Risks or ways the agent could go wrong**: Running report generation pre-validation.

## Phase 20 — Final Summary
- **Purpose**: Provide final operational summary and required metrics.
- **Files/tools to inspect/use**: Converter logs/report, framework inspection notes, evidence inspection notes, findings/validation/report outputs.
- **Expected evidence/output**: Final summary including datasheet retrieval totals (BOM line items, manifest rows, local/found/ambiguous/missing/not_applicable_generic counts, manifest path, cited datasheets, candidate URL failure summary) plus stackup source/completeness/limitations and per-evidence-class inspection summaries.
- **Validation/checkpoint before completion**: Final summary includes required metrics and limitations/skipped checks.
- **Risks or ways the agent could go wrong**: Omitting datasheet metrics or evidence-class coverage details.


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
