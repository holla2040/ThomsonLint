# Converter format notes

## ThomsonLint field expectations

No ThomsonLint repository, schema, or sample exports were present in this workspace during this implementation pass, including no local `tools/kicad-export.py`, so compatibility checks are best-effort and contract-based.

### Confirmed (from existing local converter conventions)
- Schematic file naming: `<project>-thomson-export-sch.json`.
- Board file naming: `<project>-thomson-export-brd.json`.
- Stack file naming: `<project>-thomson-export-stack.json`.
- Top-level arrays expected by this project:
  - schematic: `components`, `nets`
  - board: `components`, `placements`, `layers`
  - stack: `layers`

### Inferred
- `metadata` object including source format, source files, converter version, timestamp.
- Per-object source traceability fields (`source_element`, `source_attributes`, confidence).
- `analysis` block describing missing schematic semantics.

## Unsupported/missing schematic fields
- Symbol graphics and full sheet hierarchy
- Pin electrical types and ERC semantics
- Schematic intent beyond connectivity and BOM enrichment

## Unsupported/missing board fields
- Full DRC/rules extraction
- Full copper geometry semantics and polygon richness
- Definitive via stack details across all dialect variants

## Known gaps
- IPC-2581 is layout/manufacturing oriented, not schematic-native.
- PADS ASCII netlist + BOM provides connectivity and part metadata, but not full schematic behavior.
- Full ThomsonLint parity requires validating against official ThomsonLint schemas/sample exports.
