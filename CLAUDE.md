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

Claude Code is the tested reviewer driver. A second path exists for single-file-upload web AIs but has not been validated.

- **Claude Code (CLI, in this repo) — tested.** Read the source files directly:
  - `ontology/ontology.json`
  - `examples/examples.json`
  - `docs/AI_Hardware_Design_Review_KnowledgeBase.md`

  Do **not** read `review_instructions.txt` from Claude Code. The bundle (~260KB / 5700 lines) is intended for single-file upload to a web AI and exceeds Claude Code's per-file `Read` limit. The source files are the truth; the bundle is a concatenation of them.

- **Web AI with single-file upload (Gemini, Claude.ai, ChatGPT, etc.) — untested.** The `review_instructions.txt` bundle is produced by `gen_context.sh` from the same three source files. The maintainers have not validated this path; treat as experimental.

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
