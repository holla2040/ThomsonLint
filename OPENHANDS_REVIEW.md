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
7. Do not treat converter warnings as design findings unless they affect evidence quality or make a concrete ThomsonLint rule condition unverifiable.

## Workflow 3: Inspect ThomsonLint Framework

Before reviewing evidence, inspect the repo framework files:

1. Load `ontology/ontology.json`.
2. Load `examples/examples.json`.
3. Load `tests/findings_schema.json`.
4. Load `tests/sample_findings.json`.
5. Inspect `tools/validate_findings.py`.
6. Inspect `tools/gen_report.py`.
7. Inspect `docs/REVIEWER_INSTRUCTIONS.md`, `README.md`, and existing design-review instructions if present.
8. Determine the valid top-level findings JSON structure from `tests/findings_schema.json`.
9. Determine required issue fields from the schema and `tools/validate_findings.py`.
10. Determine valid severity values from `ontology/ontology.json` and `tests/findings_schema.json`.
11. Determine valid domains from `ontology/ontology.json` and the schema.
12. Determine valid rule IDs from `ontology/ontology.json`.
13. Determine expected `evidence[]` row format from `tests/findings_schema.json` and `tests/sample_findings.json`.
14. Determine `verified_checks` format if present.
15. Determine `cross_checks` format if present.

Current framework shape to confirm at runtime:

- Top level includes `project_name`, optional `review_date`, optional `source_documents`, required `issues`, optional `verified_checks`, and optional `cross_checks`.
- Each finding requires `domain` and `summary`.
- `issues[]` must include `severity`, `description`, `evidence[].source`, and `recommended_actions` to pass `tools/validate_findings.py`.
- Evidence rows must cite `source` and include either `label` or `note`.

## Workflow 4: Review Evidence

1. Inspect generated schematic JSON, normally `exports/example-thomson-export-sch.json`.
2. Inspect generated board JSON, normally `exports/example-thomson-export-brd.json`.
3. Inspect generated stack JSON, normally `exports/example-thomson-export-stack.json`.
4. Inspect generated BOM JSON, normally `exports/example-bom.json`.
5. Inspect generated conversion report JSON/MD.
6. Inspect PNG images when useful, especially schematic pages, copper layers, silkscreen, layout pages, and PDF renders.
7. Inspect datasheets when present under `datasheets/` or copied into `exports/`.
8. Use converter JSON as the primary structured evidence.
9. Use PNGs as visual evidence only.
10. Use raw inputs only for provenance or converter-discrepancy checks.
11. Prefer findings cross-checked across schematic, board, BOM, stack, conversion report, datasheets, and images.

## Workflow 5: Create Findings

1. Write `exports/example-findings.json`.
2. Use only fields allowed by `tests/findings_schema.json`.
3. Use valid rule IDs from `ontology/ontology.json` unless the schema and existing framework explicitly allow omission.
4. Use valid severity and domain values from `ontology/ontology.json` and `tests/findings_schema.json`.
5. Include direct evidence references in every finding.
6. Include recommended actions for every issue.
7. Include `kb_references` when the ontology rule supplies them.
8. Include `verified_checks` if the framework supports them.
9. Include `cross_checks` if the framework supports them.
10. Limit `issues[]` to at most 15 high-signal issues unless the user explicitly requests otherwise. Use `verified_checks[]` and `cross_checks[]` for checked-good analyses and broad multi-rule reviews.
11. If the converter is run with a project name other than `example`, use that same project prefix for findings and report artifacts. For example, `--project-name my_board` should produce `exports/my_board-findings.json` and the corresponding generated report.

## Workflow 6: Validate Findings

1. Run:

   ```bash
   python3 tools/validate_findings.py exports/example-findings.json
   ```

2. If validation fails:
   - Read the error.
   - Fix `exports/example-findings.json`.
   - Rerun validation.
   - Repeat until validation passes.
3. Do not bypass `tools/validate_findings.py`.
4. Do not generate the final report until validation passes.

## Workflow 7: Generate Report

1. Run:

   ```bash
   python3 tools/gen_report.py exports/example-findings.json --output exports
   ```

2. Verify the HTML report exists, normally `exports/example-review.html`.
3. Report final paths for `exports/example-findings.json` and the generated HTML report.

## Evidence Rules

- Every finding must have concrete evidence.
- Image evidence must cite image filename and page or locator when available.
- JSON evidence must cite file, path, field, and value where practical.
- Datasheet evidence must cite local datasheet filename and page or section if available.
- Do not create findings from vague impressions.
- Do not create generic "review this" findings without a concrete reason.
- Do not derive distances, trace widths, clearances, or coordinates from PNG pixels; use JSON metrics for quantitative claims.
- Converter warnings are evidence-quality notes, not design issues by themselves.

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
- ThomsonLint framework files inspected.
- Evidence files inspected.
- Image pages inspected.
- Datasheets used or missing.
- Findings count.
- `verified_checks` count if present.
- `cross_checks` count if present.
- Validation command and result.
- Report generation command and result.
- Generated report path.
- Limitations.
