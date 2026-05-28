# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ThomsonLint is a knowledge and rule framework for AI-assisted hardware design review. It provides structured, machine-readable resources that enable AI models to analyze and identify potential issues in hardware designs (schematics and PCB layouts). The tested driver is Claude Code; a single-file-upload bundle exists for web AIs (e.g., Gemini, Claude.ai, ChatGPT) but that workflow has not been validated.

The framework is named after J.J. Thomson, discoverer of the electron, reflecting its goal of uncovering fundamental issues in hardware designs.

## Core Components

- **`ontology/ontology.json`** - Machine-readable JSON defining rules, domains, severity levels, and failure modes for hardware design review
- **`examples/examples.json`** - Practical examples (good and bad) that map to ontology rules, used for training/testing AI understanding
- **`docs/AI_Hardware_Design_Review_KnowledgeBase.md`** - Human-readable explanations and context for the ontology rules
- **`docs/Multi_Agent_Reasoning_Spec.md`** - Specification for multi-agent architecture (Power/SMPS, High-Speed SI, Analog, EMC/ESD, Thermal/Mechanical agents)

## Commands

### Validate JSON files
```bash
pip install jsonschema  # if not installed
python validate_json.py
```

### Generate review instructions file
```bash
./gen_context.sh > review_instructions.txt
```

### Merge Cadence TCFX stackup data into stackup JSON
If your stackup JSON has null values for material properties, you can extract the physical parameters from Cadence Allegro/OrCAD Technology Files (.tcfx):

```bash
# Merge TCFX stackup data into stackup JSON
py -3 converter/ipc2581_to_json/parse_tcfx_stackup.py input/<project>.tcfx exports/<project>-thomson-export-stack.json

# With explicit output path
py -3 converter/ipc2581_to_json/parse_tcfx_stackup.py input/<project>.tcfx exports/<project>-thomson-export-stack.json --output exports/<project>-stackup-merged.json

# JSON output mode
py -3 converter/ipc2581_to_json/parse_tcfx_stackup.py input/<project>.tcfx.txt exports/<project>-thomson-export-stack.json --json
```

**Note:** The `thomson_bundle_converter.py` now **automatically** searches for and merges TCFX data during conversion. Manual merging is only needed if you want to update an existing stackup JSON file.

The TCFX parser extracts and merges:
- Layer thicknesses (copper and dielectric)
- Dielectric constants (Dk) and loss tangents (Df)
- Material names (FR4, soldermask, copper types)
- Copper weights (converted from thickness)
- Layer sequence ordering

This enables physical-math verification in the Saturn engine by resolving null stackup values.

### Run Saturn PCB mathematical verification engine
The Saturn engine (`scripts/saturn_engine.py`) provides IPC-standard-based mathematical verification for impedance, thermal, and voltage spacing calculations. It is integrated into `geometry_helpers.py` and can also be used standalone:

```bash
# Standalone testing
py -3 scripts/saturn_engine.py

# Integrated verification through geometry_helpers.py:
# 1. Impedance verification (HS_MAT_001) - requires stackup data
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-impedance --target-ohms 50 --json

# 2. Thermal/current capacity (PWR_TRACE_002) - requires stackup data
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --verify-trace-temp --current-a 3.0 --max-temp-rise 10.0 --json

# 3. IPC-2221B voltage spacing (DFM_TRACE_004) - requires schematic voltage annotations
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-voltage-clearance --json
```

The Saturn engine provides:
- **Impedance Calculations**: Wheeler/Wadell microstrip and stripline formulas
- **IPC-2152 Thermal Analysis**: Trace temperature rise and current capacity
- **IPC-2221B Voltage Spacing**: Electrical clearance lookup tables (B1/B2/B4 categories)
- **Via Parasitics**: DC resistance, inductance, and thermal resistance calculations

Note: Physical-math verification requires stackup metadata (`input/stackup.csv` or stackup fields in board JSON) and voltage annotations from schematic. If unavailable, mark checks as `[STACKUP_DATA_REQUIRED]`.

### Run geometry analysis on board JSON
```bash
# Analyze specific net segments (trace widths)
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --net VCC --json

# Calculate clearance between two nets
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --clearance NET_A NET_B

# Analyze all differential pairs (auto-detected by naming)
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --diff-pairs --json

# Check NPTH copper keepout (4mm radius per Appendix K.6)
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --npth --npth-radius 4.0 --json

# Verify trace ampacity for power nets
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --ampacity VCC 2.0

# Advanced DFM checks
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --check-annular-ring --json     # DFM_VIA_001/003/004
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --detect-acid-traps --json      # DFM_ACID_001
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --board-edge-clearance --json   # DFM_EDGE_001/PANEL_001
py -3 scripts/geometry_helpers.py exports/<project>-thomson-export-brd.json --copper-balance --json         # DFM_COPPER_001
```
The geometry helpers provide quantitative analysis capabilities required during Phase 9 (Full Board/Layout JSON Evaluation) and Phase 11 (DFM Evidence Inventory). Pass/fail criteria are defined in `OPENHANDS_REVIEW.md` Workflow 8 and 10.

### Run stackup analysis on stackup CSV or JSON
```bash
# Run all stackup validation checks
py -3 scripts/stackup_helpers.py input/stackup.csv --validate-stackup --json

# Run specific checks
py -3 scripts/stackup_helpers.py input/stackup.csv --check-thickness --json        # DFM_STACKUP_001
py -3 scripts/stackup_helpers.py input/stackup.csv --check-symmetry --json         # DFM_STACKUP_002
py -3 scripts/stackup_helpers.py input/stackup.csv --check-reference-planes --json # HS_MAT_001
```
The stackup helpers provide deterministic parsing and validation of PCB stackup metadata. Calculates finished board thickness, verifies dielectric symmetry around the centerline, and checks that signal layers have adjacent reference planes. Used during Phase 10 (Review Stackup and Manufacturing Evidence).

### Run schematic analysis on schematic JSON
```bash
# Run all schematic checks
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --analyze-all --json

# Run specific checks
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --single-pins    # SCH_NET_002
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --uart-check    # SCH_UART_001
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --fet-check     # SCH_FET_001
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --floating-check # SCH_FLOAT_001
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --i2c-check     # MS_I2C_001, SCH_I2C_002
py -3 scripts/schematic_helpers.py exports/<project>-thomson-export-sch.json --opamp-check   # SCH_PULLUP_001
```
The schematic helpers provide deterministic graph-based analysis for rules that require multi-hop connectivity tracing (impossible for LLMs to perform reliably on large netlists). Used during Phase 8 (Review Schematic Evidence FULL). Output is LLM-optimized JSON with precise paths: refdes, pin_number, pin_name, net_name, rule_id.

### Run BOM analysis on BOM JSON
```bash
# Run all BOM component checks
py -3 scripts/bom_helpers.py exports/<project>-bom.json --audit-components --json

# Run specific checks
py -3 scripts/bom_helpers.py exports/<project>-bom.json --heavy-threshold 3.0    # AERO_VIB_001
py -3 scripts/bom_helpers.py exports/<project>-bom.json --check-dielectrics      # COMP_CAP_001
py -3 scripts/bom_helpers.py exports/<project>-bom.json --audit-mpns             # DFM_BOM_001
py -3 scripts/bom_helpers.py exports/<project>-bom.json --check-lead-finish      # AERO_SLD_001
py -3 scripts/bom_helpers.py exports/<project>-bom.json --polarized              # SCH_POL_001
```
The BOM helpers provide deterministic filtering and analysis for component-level rules that require multi-key search, numerical threshold checks, and MPN suffix parsing. Used during Phase 12 (Review BOM and Component Evidence FULL). Output is LLM-optimized JSON with precise paths: refdes, mpn, description, rule_id.

### Run cross-source verification on BOM, Schematic, and Board JSON
```bash
# Run all cross-checks
py -3 scripts/cross_check_helpers.py \
  --bom exports/<project>-bom.json \
  --sch exports/<project>-thomson-export-sch.json \
  --brd exports/<project>-thomson-export-brd.json \
  --json

# Run specific checks
py -3 scripts/cross_check_helpers.py --bom <bom> --sch <sch> --brd <brd> --run-reconciliation  # RefDes tripartite matching
py -3 scripts/cross_check_helpers.py --bom <bom> --brd <brd> --check-packages                  # DFM_LIB_002
py -3 scripts/cross_check_helpers.py --sch <sch> --brd <brd> --verify-netlist                  # SCH_NET_001
py -3 scripts/cross_check_helpers.py --bom <bom> --sch <sch> --verify-derating                 # SCH_POL_001, COMP_CAP_002
```
The cross-check helpers perform deterministic tripartite set operations and topological mapping that LLMs cannot reliably execute on large component lists. Reconciles RefDes across BOM, Schematic, and Board; detects package mismatches; verifies netlist topology; and validates voltage derating margins. Used during Phase 16 (Cross-Source Verification). Output is LLM-optimized JSON with precise paths.

### Validate findings coverage (mandatory before report)
```bash
python tools/validate_findings.py exports/<project_name>-findings.json
```
Mechanical coverage gate. Schema-validates the findings file, lists every PDF / schematic / board export in the findings file's directory that is not cited in any `evidence[].source`, and reports issues missing required fields. Exit code is non-zero if uncited inputs or missing fields are present. **Run this before generating the HTML report.** This is the gate that prevents the agent from silently dropping datasheet analysis (every PDF the agent opens must end up in the findings file).

### Generate HTML review report
```bash
python tools/gen_report.py exports/<project_name>-findings.json [--output exports/]
```
Takes a findings JSON file (see `tests/findings_schema.json` for the schema; `tests/sample_findings.json` for a worked example) and generates a self-contained HTML report at `exports/<project_name>-review.html`. The report renders three sections: `issues` (interactive Open/Accept/Ignore triage with localStorage persistence), `verified_checks` (read-only — analyses confirmed OK), and `cross_checks` (read-only — design-wide multi-rule analyses).

## Reviewer Paths

Claude Code is the tested reviewer driver. A second path exists for single-file-upload web AIs but has not been validated. Both paths consume one source of truth: `docs/REVIEWER_INSTRUCTIONS.md`.

- **Claude Code (CLI, in this repo) — tested.** The user prompts the agent to read `docs/REVIEWER_INSTRUCTIONS.md` and follow it. Step 1 of that file then directs the agent to load the framework knowledge base from:
  - `ontology/ontology.json`
  - `examples/examples.json`
  - `docs/AI_Hardware_Design_Review_KnowledgeBase.md`

  The project ships a `/design-review` skill at `.claude/commands/design-review.md` — type `/design-review` at the Claude Code prompt instead of pasting the full prompt manually.

  Do **not** read `review_instructions.txt` from Claude Code. The bundle (~260KB / 5700 lines) is intended for single-file upload to a web AI and exceeds Claude Code's per-file `Read` limit. The source files are the truth; the bundle is a concatenation of them.

- **Web AI with single-file upload (Gemini, Claude.ai, ChatGPT, etc.) — untested.** The `review_instructions.txt` bundle is produced by `gen_context.sh`, which concatenates `docs/REVIEWER_INSTRUCTIONS.md` with the three knowledge base files. The maintainers have not validated this path; treat as experimental.

The reviewer-facing flow (inputs, outputs, prompts) is documented in README.md §5 "Running a Review".

## Pre-Commit Requirement

**Before every commit**, regenerate the `review_instructions.txt` file:
```bash
./gen_context.sh > review_instructions.txt
```

This ensures `review_instructions.txt` is always up-to-date in the repository, allowing users to immediately use it with their design files without needing to run any scripts.

## File Modification Guidelines (from TODO.md)

When modifying files in this repo:

1. **JSON files must contain pure JSON only** - no Markdown headings, commentary, or code fences
2. **Output full file contents** when updating, not diffs
3. **Preserve valid syntax** - ontology.json and examples.json must remain valid JSON
4. **Be explicit** about which file you are updating
5. **Stay conservative about deleting** - prefer appending/expanding over removing unless explicitly told to refactor

## Extending the Framework

When adding new rules or examples:
1. Add entries to `ontology/ontology.json` or `examples/examples.json` following existing structure
2. Update `docs/AI_Hardware_Design_Review_KnowledgeBase.md` if context is needed for new rules
3. Run `python validate_json.py` to validate changes

### Ontology Rule Structure
Each rule includes: `id`, `name`, `domain`, `description`, `applies_to`, `conditions`, `default_severity`, `failure_modes`, `recommended_actions`, `kb_references`

### Example Structure
Each example includes: `id`, `title`, `description`, `triggered_rules`, `expected_issue`

### Findings File Structure (output of a review)
Top-level fields: `project_name`, `review_date`, `source_documents`, `issues`, `verified_checks`, `cross_checks`. The three findings arrays share one entry shape — see `tests/findings_schema.json` and `tests/sample_findings.json`.

- **`issues[]`** — problems requiring designer triage. Severity, description, recommended_actions all required.
- **`verified_checks[]`** — analyses the agent performed where the result was OK. Read-only in the report. Crucial: do NOT omit a verification because nothing was wrong; the verification itself is a deliverable.
- **`cross_checks[]`** — design-wide analyses spanning multiple ontology rules (e.g., MT3608 layout cross-check covering PWR_BUCK_001/002/003/004 plus thermal). `rule_id` may be an array.
- **Per-entry `evidence[]`** — typed rows. Either parameter comparisons (`label/datasheet/design/margin/verdict/source`) or free-form notes (`note/source`). Every row must cite a `source`. The validator cross-references these against design inputs in the findings directory.

## JSON Schemas

- `tests/ontology_schema.json` - Schema for validating ontology.json
- `tests/examples_schema.json` - Schema for validating examples.json
- `tests/findings_schema.json` - Schema for validating findings JSON files
- `tests/sample_findings.json` - Worked example showing all three sections plus evidence rows

## Hardware Domain Coverage

The ontology covers these domains:
- **Power/SMPS** - Decoupling, buck converter layout, component ratings, compensation networks
- **High-Speed Digital (SI)** - DDR rules, differential pairs, impedance control, clock nets
- **Analog/Mixed-Signal** - Op-amp stability, ADC drivers, sensor front-ends
- **EMC/ESD** - External connector protection, EMI filtering, return paths, ground stitching
- **Thermal/Mechanical** - Power density, thermal vias, connector reinforcement
- **DFT/DFM** - Test points, silkscreen, fiducials
