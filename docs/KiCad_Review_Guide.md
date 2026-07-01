# KiCad Design Review with ThomsonLint

## Prerequisites

- Python 3.6+ (no external dependencies)
- KiCad 9.0 or KiCad 10.0 project files (`.kicad_pro`, `.kicad_sch`, `.kicad_pcb`)

## Quick Start

### 1. Export project data

```bash
python tools/kicad-export.py path/to/MyProject.kicad_pro
```

This generates two JSON files in `exports/` at the repository root:
- `MyProject-thomson-export-sch.json` — schematic data (components, nets, classifications)
- `MyProject-thomson-export-brd.json` — board data (placement, traces, zones, analysis)

Use `--output <dir>` to specify a different output directory.

### 2. Run AI-assisted review

Provide the AI model with:
1. `review_instructions.txt` (generated via `./gen_context.sh > review_instructions.txt`)
2. Both exported JSON files
3. Schematic PDFs / board screenshots for visual cross-reference

The AI will analyze the data against ThomsonLint's ontology rules and produce a findings JSON file.

### 3. Generate HTML report

```bash
python tools/gen_report.py exports/MyProject-findings.json --output exports/
```

Opens an interactive HTML report at `exports/MyProject-review.html` with triage capability (Open/Accept/Ignore per finding).

## What Gets Exported

### Schematic JSON

| Section | Contents |
|---------|----------|
| `components` | Reference, value, package, type classification, populate flag, custom attributes (Manufacturer, Partnumber, etc.) |
| `nets` | Net name, class (from project net classes), power/ground/clock/differential flags, voltage guess, pin list with directions |
| `analysis` | Power nets, ground nets, differential pairs, clock nets, floating inputs, single-pin nets |

### Board JSON

| Section | Contents |
|---------|----------|
| `components` | Reference, package, position (mm), rotation, side (top/bottom), pad coordinates |
| `board` | Outline dimensions, copper layers, zone fills |
| `signals` | Per-net trace length, width range, via count, segment count. Full trace segments for clock/differential/high-speed nets |
| `analysis` | Decoupling proximity (IC power pin to nearest cap, pad-to-pad), component-to-edge distances, ground plane layers |

### Signal Classification

The export automatically classifies nets:
- **Power**: VCC, VDD, VBUS, +3V3, +5V, 3V3, 1V8, PWR, etc.
- **Ground**: GND, AGND, DGND, VSS, etc.
- **Clock**: CLK, XTAL, SCK, SCLK, OSC, etc.
- **Differential pairs**: `_P`/`_N`, `_DP`/`_DN`, `D+`/`D-` suffixes — with interface detection (USB, CAN, Ethernet, HDMI, LVDS, PCIe, SATA, MIPI)

Components are classified by reference designator prefix (U=IC, C=capacitor, R=resistor, D=diode/LED/TVS, J=connector, FB=ferrite bead, TP=test point, etc.).

## Features

- **Standalone** — parses S-expression files directly, no KiCad installation required
- **Hierarchical schematics** — recursively processes all sub-sheets with correct instance resolution
- **Net class support** — reads net class assignments from `.kicad_pro`
- **Pre-computed analysis** — decoupling proximity uses actual pad coordinates (not component centroids) for accurate distance measurements
- **No dependencies** — Python standard library only

## Supported Versions

Tested against real projects from both major releases:

| KiCad | PCB format | Schematic format | Board net references |
|-------|-----------|------------------|----------------------|
| 9.0   | `20241229` | `20250114` | Top-level net table `(net N "name")`; pads/tracks/vias/zones reference nets by integer ordinal |
| 10.0  | `20260206` | `20260306` | No net table; pads/tracks/vias/zones carry the name inline as `(net "name")` |

The exporter detects the format automatically. For KiCad 10 boards (which
dropped the net table and integer ordinals) it synthesizes sequential net
ordinals in discovery order so the JSON output shape is identical across
versions. Compatible with any KiCad 9.x or 10.x project.
