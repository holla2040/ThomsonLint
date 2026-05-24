1. OBJECTIVE
This plan creates a deep, phased ThomsonLint review workflow that strictly follows the repository's existing framework as defined in OPENHANDS_REVIEW.md and related framework files. The goal is to produce a complete hardware design review including: converter execution, evidence analysis, findings JSON generation, validation, and HTML report generation—without modifying any framework files or inventing a new process.

2. CONTEXT SUMMARY
The ThomsonLint repository contains:

Framework files: OPENHANDS_REVIEW.md (source of truth), ontology/ontology.json (rules), examples/examples.json (worked examples), tests/findings_schema.json and tests/sample_findings.json (findings structure), tools/validate_findings.py and tools/gen_report.py (validation/reporting)
Input files: input/example_ipc.xml, example_schematic.pdf, example_gerbers.pdf, example_bom.csv, example_pads.asc
Converter: converter/ipc2581_to_json/thomson_bundle_converter.py with wrapper run_converter_pipeline.py
Expected outputs: exports/ directory containing JSON exports, PNG images, findings JSON, and HTML report
The workflow requires: (1) converter execution first, (2) framework inspection before review, (3) image-based evidence gate, (4) structured findings generation, (5) validation as hard gate, (6) report generation only after validation passes.

Evidence sources may come from exports/, input/, or datasheets/. The validator cross-references citations against files present; source_documents should declare only inputs actually consumed and required by the validator. Board JSON is layout/routing/exported-geometry evidence—not DRC results.

3. APPROACH OVERVIEW
A phased approach is selected to ensure strict compliance with the repository's workflow:

Phase 1: Ingest and map OPENHANDS_REVIEW.md to executable steps
Phase 2: Inspect all framework files to determine valid findings structure
Phase 3: Inspect input files and handle missing datasheets as evidence gaps
Phase 4: Run converter before any review analysis
Phase 4B: Use Tavily only as a controlled datasheet discovery tool when local datasheets are missing and `TAVILY_API_KEY` is available.
Phase 5: Enforce image PNG generation gate (stop if PDFs present but PNGs missing)
Phase 6: Deep evidence review across JSON, images, and datasheets
Phase 7: Develop evidence-backed candidate findings before writing JSON
Phase 8: Write findings JSON following schema exactly
Phase 9: Validate and repair in a loop until validation passes
Phase 10: Generate HTML report only after validation passes
Phase 11: Final summary with all required metrics
This approach prevents common agent errors: bypassing the converter, ignoring image evidence, inventing new schemas, or generating reports without validation.

4. IMPLEMENTATION STEPS
Phase 1 — Ingest ThomsonLint Workflow
Purpose: Read OPENHANDS_REVIEW.md as source of truth and map it to executable steps.

Files to inspect/use:

OPENHANDS_REVIEW.md (entire document)
docs/REVIEWER_INSTRUCTIONS.md
README.md
Expected evidence/output:

A step-by-step mapping of OPENHANDS_REVIEW.md workflows to concrete actions
Identification of all framework files referenced (ontology, examples, schema, sample findings, validator, report generator)
Validation/checkpoint before moving to next phase:

All 11 workflow sections from OPENHANDS_REVIEW.md are mapped to phases in this plan
Framework file list matches files named in OPENHANDS_REVIEW.md
Risks or ways the agent could go wrong:

Inventing a new review process instead of following OPENHANDS_REVIEW.md exactly
Skipping converter execution (Workflow 2) before review analysis
Not treating OPENHANDS_REVIEW.md as the single source of truth
Phase 2 — Inspect Findings Framework
Purpose: Determine the exact JSON structure for findings, including required fields, valid values, and evidence formats.

Files to inspect/use:

tests/findings_schema.json (JSON schema)
tests/sample_findings.json (worked example)
ontology/ontology.json (rules, domains, severity levels)
examples/examples.json (example mappings)
tools/validate_findings.py (validation logic)
Expected evidence/output:

Top-level structure: project_name (required), review_date (optional), source_documents (optional), issues (required), verified_checks (optional), cross_checks (optional)
Issue fields required: domain, summary, severity, description, evidence[], recommended_actions
Evidence row fields: source (required), label OR note (one required), datasheet/design/margin/verdict for parametric rows, note for free-form
Valid severity values: Critical, Major, Minor, Advisory, Informational
Valid domains from ontology: Power, HighSpeed, Analog, MixedSignal, EMC, Thermal, DFT, Mechanical, Schematic, Component, Aerospace
Valid rule_ids from ontology.json rules array
Validation/checkpoint before moving to next phase:

Schema validation test: sample_findings.json passes tests/findings_schema.json
Field completeness list matches tools/validate_findings.py checks (severity, description, recommended_actions for issues; source for all evidence rows)
Risks or ways the agent could go wrong:

Adding fields not in schema (additionalProperties: false)
Using invalid severity values (e.g., "High" instead of "Critical")
Omitting required fields (e.g., no evidence[] in issues)
Misinterpreting sample_findings.json as evidence rather than style reference
Phase 3 — Inspect Inputs and Datasheets
Purpose: List all raw design input files and handle missing datasheets as evidence gaps, not guessed information.

Files to inspect/use:

input/ directory
Optional: datasheets/ directory (if present)
converter/ipc2581_to_json/thomson_bundle_converter.py
Expected evidence/output:

List of all input files: example_ipc.xml, example_schematic.pdf, example_gerbers.pdf, example_bom.csv, example_pads.asc
Record that no datasheets/ directory exists (or list its contents if present)
Note that local datasheet absence means "no datasheet evidence available" for component checks
Validation/checkpoint before moving to next phase:

All input files are documented with filenames and types
Missing datasheets are recorded as "datasheet missing" in notes, not assumed values
Risks or ways the agent could go wrong:

Assuming datasheet values without evidence (e.g., guessing a capacitor's voltage rating)
Creating findings from vague impressions instead of concrete input file content
Not distinguishing between raw input files and generated exports
Phase 4 — Run Integrated Converter
Purpose: Execute converter to generate JSON exports, PNG images, and conversion report before any review analysis.

Files to inspect/use:

tools/run_converter_pipeline.py (wrapper script)
converter/ipc2581_to_json/thomson_bundle_converter.py (main converter)
Expected evidence/output:

Command: python3 tools/run_converter_pipeline.py input --project-name example --clean
exports/ directory created with generated files
JSON exports: <project>-thomson-export-sch.json, <project>-thomson-export-brd.json, <project>-thomson-export-stack.json, <project>-bom.json (actual naming from converter)
PNG images if PDFs provided: list actual filenames using patterns such as *-img-sch-p*.png and *-img-layout-p*.png
Conversion report: <project>-conversion-report.json and/or <project>-conversion-report.md
Validation/checkpoint before moving to next phase:

exports/ exists
All JSON files load with Python json.load() (no syntax errors)
PNGs exist when PDFs were provided in input/
Converter warnings recorded from report (not treated as design findings)
Risks or ways the agent could go wrong:

Running review analysis before converter execution. OPENHANDS_REVIEW.md Workflow 2 runs the converter first; Workflow 4 reviews generated evidence.
Skipping --clean flag causing stale exports
Treating converter warnings as design issues rather than evidence-quality notes

Phase 4B — Tavily Datasheet Discovery
Purpose: Use Tavily only as a controlled datasheet discovery tool when local datasheets are missing and `TAVILY_API_KEY` is available.

Files/tools to inspect/use:

- exports/<project>-bom.json
- exports/<project>-thomson-export-sch.json
- datasheets/ if present
- exports/datasheets/ for downloaded datasheets
- Tavily Search API through environment variable `TAVILY_API_KEY`

Expected evidence/output:

- Identify candidate critical components from BOM/schematic:
  - regulators
  - power-path ICs
  - ESD/protection devices
  - transceivers
  - sensors
  - connectors with electrical limits
  - other parts needed for concrete rule checks
- Search only targeted component queries using exact MPN, manufacturer, LCSC number, package, and function where available.
- Prefer official manufacturer or major distributor datasheet sources.
- Save confirmed datasheets under exports/datasheets/.
- Write exports/datasheets/datasheet_manifest.jsonl.
- Record unfound or ambiguous datasheets as missing evidence.

Validation/checkpoint before moving to next phase:

- `TAVILY_API_KEY` is present, or the phase is skipped with a clear note.
- Local datasheets are preferred over web results.
- Downloaded datasheets exist as local files before being used as evidence.
- Tavily snippets are not used as evidence.
- No API key is printed, committed, stored in findings, stored in reports, or written to the manifest.

Risks or ways the agent could go wrong:

- Treating Tavily search snippets as facts.
- Downloading the wrong datasheet for an ambiguous part number.
- Searching for every passive component and wasting time.
- Citing a web result instead of a local saved datasheet.
- Leaking `TAVILY_API_KEY`.

Phase 5 — Enforce Image Review Gate
Purpose: Ensure PNG images exist for visual evidence before proceeding; stop if PDFs present but PNGs missing.

Files to inspect/use:

exports/ directory (generated outputs)
System tools: pdftoppm, pdfinfo (if available)
Expected evidence/output:

Check that pdftoppm exists (for PNG generation from PDFs)
Check that pdfinfo exists (for PDF page count)
List actual PNG filenames in exports/ using patterns -img-sch-p.png and -img-layout-p.png
If PDFs present in input/ but no matching PNGs in exports/, report blocker and stop
Validation/checkpoint before moving to next phase:

All PNG files referenced in evidence must exist
Blocker if schematic PDF or Gerber/PCB PDF present without corresponding PNGs
No silent fallback to JSON-only review. OPENHANDS_REVIEW.md requires verifying rendered PNGs when PDFs are provided, and this deep-review run requires image evidence as a hard gate.
Risks or ways the agent could go wrong:

Proceeding with JSON-only review when PDFs are available but PNGs missing
Not citing PNG filenames in evidence[].source (validator cross-references citations against files)
Assuming visual inspection without actual PNG evidence
Phase 6 — Deep Evidence Review
Purpose: Perform comprehensive review across all evidence sources, not a schema-valid pass.

Files to inspect/use:

exports/<project>-thomson-export-sch.json (actual filename from converter)
exports/<project>-thomson-export-brd.json (actual filename from converter)
exports/<project>-thomson-export-stack.json (actual filename from converter)
exports/<project>-bom.json (actual filename from converter)
exports/<project>-conversion-report.json/MD
PNG images from exports/ (list actual filenames)
Any datasheets in exports/, input/, or datasheets/
Expected evidence/output:

Specific review areas with evidence citations from exports/, input/, or datasheets/:
Power integrity and decoupling: check PWR_DECPL_001, cite sch/brd JSON paths + PNGs if visual verification needed
Regulator/power path checks: PWR_BUCK_001-004, cite stackup JSON copper_stack[] + PNG pour integrity (no DRC wording)
Ground and return path concerns: EMC_PATH_001, cite stackup adjacent plane + PNG keepout visualization (no DRC wording)
Connector/interface protection: EMC_ESD_001, cite component proximity from brd JSON + PNG placement (brd JSON = layout evidence, not DRC results)
ESD/protection evidence: PWR_TVS_001, AERO_TVS_001, cite datasheet clamp voltage + design values
Differential or paired interface candidates: HS_DIFF_001, HS_SER_001-002, cite net classification from sch JSON + PNG routing (no DRC wording)
Routing width/length evidence: HS_DDR_001, HS_SER_001, cite trace length metrics from brd JSON (brd JSON = exported geometry, not DRC results)
Via/hole/drill evidence: DFM_VIA_001, cite hole dimensions from brd JSON + PNG via placement (no DRC wording)
Test/debug access: DFT_TP_001, cite test point presence/absence from brd JSON + PNG pads (no DRC wording)
BOM/schematic/board consistency: component count match across files + package info verification
Stackup and manufacturing evidence limits: cite stackup JSON copper_layer_count + PNG layer visibility
Image-confirmed schematic/layout context: cross-reference sch PNG sheets with brd PNG layers
Validation/checkpoint before moving to next phase:

Every finding candidate has at least one concrete evidence citation (datasheet, JSON path, or PNG filename)
Unsupported claims rejected; vague "review this" findings rejected
Candidates mapped to specific rule_ids when possible from ontology
Risks or ways the agent could go wrong:

Writing findings without concrete evidence citations (validator will fail)
Deriving metrics from PNG pixels instead of JSON values (OPENHANDS_REVIEW.md explicitly forbids this)
Omitting verified_checks[] for analyses that passed (designer needs to see what was checked)
Not cross-checking across multiple sources (e.g., sch JSON + brd JSON + stackup JSON)
Phase 7 — Candidate Finding Development
Purpose: Develop evidence-backed candidate findings before writing final JSON.

Files to inspect/use:

ontology/ontology.json rules array
examples/examples.json examples array
Schema and sample findings as style references (not evidence)
Evidence sources from Phase 6
Expected evidence/output:

Candidate findings must include:
rule_id when applicable (from ontology rules)
severity (Critical/Major/Minor/Advisory for issues; Informational or omit for verified_checks/cross_checks)
domain (from ontology domains list)
summary (one-line concise statement)
description (detailed prose, no parameter tables embedded)
evidence[] with typed rows (parametric: label/datasheet/design/margin/verdict; free-form: note/source)
recommended_actions for issues only
kb_references when ontology rule supplies them
component_id and net_id arrays when applicable
Validation/checkpoint before moving to next phase:

Each candidate maps to at least one evidence source (datasheet filename, JSON file+path, PNG filename)
Unsupported claims rejected; vague findings rejected
Examples/examples.json used as style reference only (not evidence for this board)
Risks or ways the agent could go wrong:

Copying example findings as evidence (sample_findings.json is style reference only)
Including unsupported claims without evidence citations
Omitting recommended_actions for issues (validator will fail)
Using invalid severity values
Phase 8 — Write Findings JSON
Purpose: Write exports/<project>-findings.json following schema exactly.

Files to inspect/use:

tests/findings_schema.json (schema validation)
tests/sample_findings.json (style reference only)
examples/examples.json (rule ID and domain references)
Expected evidence/output:

File: exports/<project>-findings.json (actual project name from converter)
Top-level structure: project_name, review_date, source_documents[], issues[], verified_checks[], cross_checks[]
At most 15 high-signal issues unless user requests otherwise
source_documents[] follows schema and validator expectations; declare only inputs actually consumed and required by the validator
Each finding has all required fields per schema
Validation/checkpoint before moving to next phase:

Schema validation test: findings pass jsonschema.validate against tests/findings_schema.json
All evidence[].source strings match files in exports/, input/, or datasheets/ (validator cross-references citations against all present files)
Risks or ways the agent could go wrong:

Adding additionalProperties (schema forbids them)
Omitting required fields (issues must have severity, description, recommended_actions; evidence rows must have source)
Including more than 15 issues without explicit user request
Phase 9 — Validate and Repair Findings
Purpose: Run validation in a loop until it passes; fix only exports/<project>-findings.json.

Files to inspect/use:

tools/validate_findings.py (validator script)
Expected evidence/output:

Command: python3 tools/validate_findings.py exports/<project>-findings.json (actual project name from converter)
Validation output showing cited/uncited inputs, field completeness checks, ontology rule coverage
If validation fails: read error, fix only exports/<project>-findings.json, rerun validation, repeat until pass
Validation/checkpoint before moving to next phase:

Validator exits with code 0 (PASS)
All design inputs in exports/, input/, or datasheets/ are cited in evidence[].source where applicable
No hard errors in validator output
Risks or ways the agent could go wrong:

Modifying schema/validator/ontology to force a pass (OPENHANDS_REVIEW.md forbids this)
Not fixing only exports/<project>-findings.json (not framework files)
Proceeding to report generation without validation passing (OPENHANDS_REVIEW.md Workflow 7 requires validation first)
Phase 10 — Generate Report
Purpose: Generate HTML report only after validation passes.

Files to inspect/use:

tools/gen_report.py (report generator script)
Expected evidence/output:

Command: python3 tools/gen_report.py exports/<project>-findings.json --output exports
Generated file: exports/<project>-review.html
HTML report includes interactive triage (Open/Accept/Ignore) for issues, read-only verified_checks and cross_checks
Validation/checkpoint before moving to next phase:

exports/<project>-review.html exists and was generated by tools/gen_report.py (browser opening is optional)
Report contains all findings from exports/<project>-findings.json
Risks or ways the agent could go wrong:

Running report generation before validation passes (OPENHANDS_REVIEW.md forbids this)
Not verifying HTML report exists
Phase 11 — Final Summary
Purpose: Present final review summary with all required metrics.

Expected evidence/output:

Phases completed count
Converter command run: python3 tools/run_converter_pipeline.py input --project-name example --clean
Converter output summary (JSON files, PNGs, warnings)
Framework files inspected list
Evidence files inspected list (sch/brd/stack JSON, PNGs, datasheets)
Image pages inspected count
Datasheets used or missing record
Findings count: X issues, Y verified_checks, Z cross_checks
Validation command/result: python3 tools/validate_findings.py exports/<project>-findings.json — PASS
Report generation command/result: python3 tools/gen_report.py exports/<project>-findings.json --output exports — HTML generated
Generated report path: exports/<project>-review.html
Limitations and skipped checks (e.g., "No datasheet for IC1, so PWR_RATING_001 unverified")
5. TESTING AND VALIDATION
Validation methods:

Schema validation: tests/findings_schema.json must pass jsonschema.validate on exports/<project>-findings.json
Coverage validation: tools/validate_findings.py must exit with code 0 (all inputs cited, all required fields present)
Report generation: exports/<project>-review.html must exist and be valid HTML
Success criteria:

OPENHANDS_REVIEW.md workflow followed exactly (converter first, then review, then validation, then report)
No framework files modified (schema, validator, ontology, examples unchanged)
All evidence citations match actual files in exports/
At most 15 high-signal issues unless user requests otherwise
HTML report exists with triage interface for issues and read-only sections for verified_checks/cross_checks
Failure criteria:

Validator exits non-zero (uncited inputs, missing required fields)
Report generated without validation passing
Framework files modified to force a pass
Findings without concrete evidence citations
