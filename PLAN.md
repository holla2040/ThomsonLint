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
Phase 15 — Candidate Finding Development
Phase 16 — Write Findings JSON
Phase 17 — Validate and Repair Findings
Phase 18 — Generate Report
Phase 19 — Final Summary

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

## Phase 15 — Candidate Finding Development
- **Purpose**: Develop candidate findings before writing final JSON.
- **Files/tools to inspect/use**: Phase 8–14 evidence plus `ontology/ontology.json` and `examples/examples.json` (style/rule mapping only).
- **Expected evidence/output**: Evidence-cited candidate set mapped to rule/domain/severity where possible.
- **Validation/checkpoint before moving to next phase**: Unsupported or vague candidates rejected; concrete citations required.
- **Risks or ways the agent could go wrong**: Promoting weak/vague ideas to issues.

## Phase 16 — Write Findings JSON
- **Purpose**: Create findings JSON using schema-allowed fields only.
- **Files/tools to inspect/use**: Findings schema, validator expectations, generated evidence sources.
- **Expected evidence/output**: Findings JSON with `issues`, `evidence`, `recommended_actions`, and `verified_checks`/`cross_checks`/`source_documents` as supported.
- **Validation/checkpoint before moving to next phase**: Findings writing occurs after all evidence-review phases; `issues[]` limited to 15 high-signal items unless user requests otherwise.
- **Risks or ways the agent could go wrong**: Writing findings too early or violating schema.

## Phase 17 — Validate and Repair Findings
- **Purpose**: Validate findings and repair only findings JSON until pass.
- **Files/tools to inspect/use**: `python3 tools/validate_findings.py exports/example-findings.json` (or matching project prefix).
- **Expected evidence/output**: Validation pass output.
- **Validation/checkpoint before moving to next phase**: Validator succeeds with no bypass.
- **Risks or ways the agent could go wrong**: Editing framework files instead of findings JSON.

## Phase 18 — Generate Report
- **Purpose**: Generate report only after validation passes.
- **Files/tools to inspect/use**: `python3 tools/gen_report.py exports/example-findings.json --output exports` (or matching project prefix).
- **Expected evidence/output**: HTML report path under `exports/`.
- **Validation/checkpoint before moving to next phase**: Report generation is strictly post-validation.
- **Risks or ways the agent could go wrong**: Running report generation pre-validation.

## Phase 19 — Final Summary
- **Purpose**: Provide final operational summary and required metrics.
- **Files/tools to inspect/use**: Converter logs/report, framework inspection notes, evidence inspection notes, findings/validation/report outputs.
- **Expected evidence/output**: Final summary including datasheet retrieval totals (BOM line items, manifest rows, local/found/ambiguous/missing/not_applicable_generic counts, manifest path, cited datasheets, candidate URL failure summary) plus stackup source/completeness/limitations and per-evidence-class inspection summaries.
- **Validation/checkpoint before completion**: Final summary includes required metrics and limitations/skipped checks.
- **Risks or ways the agent could go wrong**: Omitting datasheet metrics or evidence-class coverage details.
