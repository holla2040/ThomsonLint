# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ThomsonLint is a knowledge and rule framework for AI-assisted hardware design review. It provides structured, machine-readable resources that enable AI models (primarily Gemini) to analyze and identify potential issues in hardware designs (schematics and PCB layouts).

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

### Generate context file for Gemini
```bash
./gen_context.sh > gemini_context.txt
```

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

## JSON Schemas

- `tests/ontology_schema.json` - Schema for validating ontology.json
- `tests/examples_schema.json` - Schema for validating examples.json

## Hardware Domain Coverage

The ontology covers these domains:
- **Power/SMPS** - Decoupling, buck converter layout, component ratings, compensation networks
- **High-Speed Digital (SI)** - DDR rules, differential pairs, impedance control, clock nets
- **Analog/Mixed-Signal** - Op-amp stability, ADC drivers, sensor front-ends
- **EMC/ESD** - External connector protection, EMI filtering, return paths, ground stitching
- **Thermal/Mechanical** - Power density, thermal vias, connector reinforcement
- **DFT/DFM** - Test points, silkscreen, fiducials
