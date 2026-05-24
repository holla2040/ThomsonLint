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

## Workflow 1: Prepare Review Inputs

1. Confirm `input/` exists.
2. List all files under `input/`.
3. Verify at least one design input exists: IPC-2581 XML, PADS/OrCAD/ASCII schematic or netlist export, BOM CSV, schematic PDF, or layout/Gerber/PCB PDF.
4. Do not modify git state.
5. Do not delete input files.
6. Use local datasheets from `datasheets/` if present; cite local filenames later in evidence.

## Workflow 2: Run Integrated Converter

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

## Workflow 3: Inspect ThomsonLint Framework

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

## Workflow 4: Retrieve Datasheets

1. This is a required normal numbered workflow.
2. Prefer local datasheets under `datasheets/` first.
3. If local datasheets are missing and SearXNG MCP is available, use SearXNG only for targeted datasheet discovery.
4. Perform retrieval after converter execution and framework inspection because BOM/schematic exports identify candidate parts.
5. Search only for critical components needed for concrete checks:
   - regulators
   - power-path ICs
   - protection/ESD/TVS devices
   - transceivers
   - sensors
   - connectors with electrical limits
   - other parts required for a specific rule check
6. Do not search for every passive component unless needed for a concrete finding or verified check.
7. Prefer official manufacturer or major distributor datasheet sources.
8. Do not use SearXNG snippets as evidence.
9. Save confirmed datasheets under `exports/datasheets/`.
10. Create `exports/datasheets/datasheet_manifest.jsonl` recording:
    - component reference or part identifier
    - search query
    - selected URL
    - source domain
    - local saved filename
    - reason selected
    - status: found, ambiguous, or missing
11. Cite only local saved datasheet filenames in findings.
12. If a datasheet cannot be confidently identified, record it as missing evidence rather than guessing.
13. If SearXNG MCP is unavailable, do not use browser Google search; record retrieval as unavailable/missing evidence and continue unless datasheets are a hard gate.
14. Do not print, store, or write secrets/API keys in repo files, findings, reports, manifests, or logs.

## Workflow 5: Review Schematic Evidence

1. Inspect generated schematic JSON.
2. Review components, refdes coverage, net names, power nets, external interfaces, connector nets, single-pin/unusual connections, and schematic-level evidence limitations.
3. Cite schematic JSON file/path/field/value where practical.
4. Use schematic PNGs only for visual/context confirmation, not quantitative claims.
5. Record checked-good items for `verified_checks` when useful.

## Workflow 6: Review Board/Layout Evidence

1. Inspect generated board JSON.
2. Review exported layout geometry, routing evidence, pads, vias/holes, route widths, route lengths, copper/non-copper separation, physical grouping, and board-level evidence limitations.
3. Treat board JSON as exported geometry evidence, not DRC results.
4. Do not claim true DRC, exact clearance, net-short proof, annular-ring validation, soldermask validation, or manufacturing signoff unless explicit tool evidence supports it.
5. Cite board JSON file/path/field/value where practical.
6. Use layout PNGs only for visual/context confirmation, not quantitative claims.

## Workflow 7: Review Stackup and Manufacturing Evidence

1. Inspect generated stack JSON.
2. Review layer order, copper layers, available material/thickness/stackup facts, missing impedance data, manufacturing evidence limits, and converter limitations.
3. Do not claim impedance verification or manufacturing signoff unless explicit evidence supports it.
4. Record missing stackup facts as limitations or `verified_checks`/`cross_checks` where appropriate.

## Workflow 8: Review BOM and Component Evidence

1. Inspect generated BOM JSON.
2. Review component list, refdes coverage, manufacturer/MPN/LCSC fields, quantity consistency, missing metadata, package information, and BOM/schematic/board consistency candidates.
3. Identify components that need datasheet evidence.
4. Do not infer datasheet parameters from vendor names or package names alone.

## Workflow 9: Review Image Evidence

1. This workflow is required for deep-review runs when PDFs are present.
2. Inspect generated schematic PNGs.
3. Inspect generated layout/Gerber/PCB PNGs.
4. Record image pages inspected.
5. Use PNGs for visual/context evidence: schematic labels, connector labels, power/interface labels, page context, physical grouping, and obvious visual concerns.
6. Do not derive distances, clearances, trace widths, or coordinates from PNG pixels.
7. If PDFs are present but PNGs are missing, stop and report an image-rendering blocker unless the user explicitly approves JSON-only fallback.

## Workflow 10: Review Datasheet Evidence

1. Inspect local/retrieved datasheets actually available.
2. Use only local saved datasheet files as evidence.
3. Cite local datasheet filename and page/section when practical.
4. Record missing/ambiguous datasheets from the manifest as evidence limitations.
5. Do not use web snippets or search-result text as evidence.

## Workflow 11: Cross-Source Consistency Review

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

## Workflow 12: Create Candidate Findings

1. Create candidate findings before writing final JSON.
2. Reject unsupported claims.
3. Reject vague "review this" findings.
4. Map candidates to ontology rule IDs, domains, and severities when possible.
5. Require concrete evidence before promoting a candidate to an issue.
6. Use examples/sample findings as style references only, not evidence.

## Workflow 13: Create Findings JSON

1. Write `exports/example-findings.json` or the matching project-prefixed findings file.
2. Use only schema-allowed fields.
3. Include concrete evidence in every finding.
4. Include recommended_actions for every issue.
5. Include `kb_references` when the ontology rule supplies them.
6. Include `verified_checks` and `cross_checks` if supported.
7. Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise.

## Workflow 14: Validate Findings

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

## Workflow 15: Generate Report

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
- Datasheets found count.
- Datasheets missing/ambiguous count.
- Datasheet manifest path if created.
- Datasheets used as evidence.
- Findings count.
- `verified_checks` count if present.
- `cross_checks` count if present.
- Validation command and result.
- Report generation command and result.
- Generated report path.
- Limitations and skipped checks.
