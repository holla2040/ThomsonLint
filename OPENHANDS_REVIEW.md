# OpenHands ThomsonLint Review Workflow

## Purpose

This repo contains ThomsonLint and an integrated converter. An OpenHands or other coding agent must first run the converter, then run the ThomsonLint review workflow exactly as defined by this repository.

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

8. If package installation fails or `pdftoppm`/`pdfinfo` remain unavailable, stop and report a blocker. Do not proceed to converter execution and do not produce JSON-only review unless the user explicitly approves fallback.
9. If PDFs are present in `input/`, the converter must not be run until `pdftoppm` and `pdfinfo` are available.

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
9. Save confirmed retrieved datasheets under `exports/datasheets/`.
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
12. Status definitions:
    - `local`: matching datasheet already existed locally and was reused.
    - `found`: matching datasheet found via approved discovery and saved under `exports/datasheets/`.
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
20. Missing/ambiguous datasheets do not block review unless user explicitly sets datasheets as a hard gate; report them as evidence limitations.
21. Cite only local saved datasheet filenames in findings.
22. Final response must include: total BOM line items, manifest row count, local datasheets reused count, retrieved datasheets count, ambiguous count, missing count, not_applicable_generic count, manifest path, datasheets cited in findings, and candidate URL/download failure summary (if any).
23. Do not print, store, or write secrets/API keys in repo files, findings, reports, manifests, or logs.

## Workflow 6: Review Schematic Evidence FULL

1. Inspect generated schematic JSON.
2. Review components, refdes coverage, net names, power nets, external interfaces, connector nets, single-pin/unusual connections, and schematic-level evidence limitations.
3. Cite schematic JSON file/path/field/value where practical.
4. Use schematic PNGs only for visual/context confirmation, not quantitative claims.
5. Record checked-good items for `verified_checks` when useful.

## Workflow 7: Full Board/Layout JSON Evaluation

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
5. Produce a board evidence inventory file under `exports/`, for example `exports/<project>-board-evidence-inventory.json`.
6. Board evidence inventory should include: source board JSON filename, generated timestamp, inspected sections list, counts by object type, nets count, components count (if available), route count, via/hole count, layer count, route width summary, route length summary, candidate differential/paired nets, candidate power nets, candidate connector/interface nets, candidate test/debug features, missing/unsupported board evidence fields, and evidence paths used for candidate findings.
7. Board evidence review checkpoint requires:
   - board JSON loaded successfully
   - required categories inspected or explicitly marked unavailable
   - board evidence inventory created
   - no findings written before board evidence inventory exists
8. Board JSON is exported geometry/routing evidence, not true DRC.
9. Do not claim exact clearance, net-short proof, annular-ring validation, soldermask validation, impedance verification, or manufacturing signoff unless explicit tool evidence supports it.

## Workflow 8: Review Stackup and Manufacturing Evidence

1. Inspect generated stack JSON.
2. Explicitly inspect candidate stackup sources: generated stack JSON, `input/stackup.csv`, `input/stackup.json`, fabrication drawing PDFs, ODB++ archive/folder if present, IPC-2581 stackup/cross-section content if present, and EDA-specific stackup reports if present.
3. ODB++ may be the preferred board/layout/fabrication source when present, but always inspect what stackup/material fields are actually present before making stackup claims.
4. IPC-2581 and ODB++ are both possible board/layout sources, but neither guarantees complete stackup/material/impedance data unless the export includes it.
5. If no explicit stackup source exists, mark stackup as missing evidence.
6. Layer names, Gerber filenames, ODB++ matrix layer names, IPC-2581 layer names, or PDF/Gerber page names alone are insufficient for dielectric thickness, copper weight, material system, Dk/Df, controlled impedance, finished board thickness, or manufacturing signoff.
7. Without explicit stackup/material/impedance evidence, do not claim impedance verification, stackup verification, manufacturing signoff, return-path quality beyond limited qualitative observations, exact dielectric spacing, exact layer construction, exact copper weight, or material/Dk/Df verification.
8. Report stackup completeness status as one of: `complete_explicit`, `partial_explicit`, `layer_order_only`, `missing`.
9. Status definitions:
   - `complete_explicit`: layer order/type, copper thickness/weight, dielectric thickness, and material/Dk or equivalent facts are available.
   - `partial_explicit`: some explicit stackup facts exist but key fields are missing.
   - `layer_order_only`: only layer names/order/types are available.
   - `missing`: no reliable explicit stackup source is available.
10. Recommended manual `stackup.csv` schema: `layer_index`, `layer_name`, `layer_type`, `material`, `thickness_mil`, `copper_oz`, `dielectric_dk`, `dielectric_df`, `notes`.
11. Optional `impedance_rules.csv` schema: `rule_name`, `net_class`, `target_ohms`, `tolerance_ohms`, `layer`, `width_mil`, `spacing_mil`, `reference_plane`, `notes`.
12. Final response must include: stackup source used, stackup completeness status, missing stackup fields, whether impedance evidence was available, and stackup limitations.

## Workflow 9: Review BOM and Component Evidence FULL

1. Inspect generated BOM JSON.
2. Review component list, refdes coverage, manufacturer/MPN/LCSC fields, quantity consistency, missing metadata, package information, and BOM/schematic/board consistency candidates.
3. Identify components that need datasheet evidence.
4. Do not infer datasheet parameters from vendor names or package names alone.

## Workflow 10: Review Image Evidence FULL

1. This workflow is required for deep-review runs when PDFs are present.
2. Inspect generated schematic PNGs.
3. Inspect generated layout/Gerber/PCB PNGs.
4. Record image pages inspected.
5. Use PNGs for visual/context evidence: schematic labels, connector labels, power/interface labels, page context, physical grouping, and obvious visual concerns.
6. Do not derive distances, clearances, trace widths, or coordinates from PNG pixels.
7. If PDFs are present but PNGs are missing after converter execution, stop and report an image-rendering blocker unless the user explicitly approves JSON-only fallback.
8. Image gate is mandatory:
   - schematic PDFs present require schematic PNGs
   - layout/Gerber/PCB PDFs present require layout/Gerber/PCB PNGs
   - no silent JSON-only fallback

## Workflow 11: Review Datasheet Evidence FULL

1. Inspect local/retrieved datasheets actually available.
2. Use only local saved datasheet files as evidence.
3. Cite local datasheet filename and page/section when practical.
4. Record missing/ambiguous datasheets from the manifest as evidence limitations.
5. Do not use web snippets or search-result text as evidence.

## Workflow 12: Cross-Source Consistency Review

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

## Workflow 13: Create Candidate Findings

1. Create candidate findings before writing final JSON.
2. Reject unsupported claims.
3. Reject vague "review this" findings.
4. Map candidates to ontology rule IDs, domains, and severities when possible.
5. Require concrete evidence before promoting a candidate to an issue.
6. Use examples/sample findings as style references only, not evidence.

## Workflow 14: Create Findings JSON

1. Write `exports/example-findings.json` or the matching project-prefixed findings file.
2. Use only schema-allowed fields.
3. Include concrete evidence in every finding.
4. Include recommended_actions for every issue.
5. Include `kb_references` when the ontology rule supplies them.
6. Include `verified_checks` and `cross_checks` if supported.
7. Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise.

## Workflow 15: Validate Findings

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

## Workflow 16: Generate Report

1. Run:

   ```bash
   python3 tools/gen_report.py exports/example-findings.json --output exports
   ```

2. Verify the HTML report exists.
3. Report final paths.

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
- Datasheets found count.
- Datasheets missing/ambiguous count.
- Datasheet manifest path if created.
- Total BOM line items.
- Datasheet manifest rows count.
- Local datasheets reused count.
- Retrieved datasheets count.
- Ambiguous count.
- Missing count.
- not_applicable_generic count.
- Datasheets used as evidence.
- Candidate URL/download failures summary if any.
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
