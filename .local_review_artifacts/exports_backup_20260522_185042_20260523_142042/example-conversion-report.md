# Conversion Report (Phase 6) - example

## Metadata
- Converter: thomson_bundle_converter 0.5.0-phase5
- Generated (UTC): 2026-05-22T18:47:24.297914+00:00

## Discovery Counts
- bom_csv_candidate: 1
- ipc2581_candidate: 1
- layout_pdf_candidate: 1
- pads_ascii_candidate: 1
- schematic_pdf_candidate: 1

## BOM
- Source file: `example_bom.csv`
- Row count: 38

## Schematic (PADS)
- Source file: `example_pads.asc`
- Detected dialect: pads_pcb_ascii_orcad_or_altium
- Components: 85
- Nets: 131
- Nodes: 413
- Schematic JSON validation: pass

## IPC-2581 / Board
- Source file: `example_ipc.xml`
- Root: IPC-2581
- Revision: B
- Namespace present: True
- Board components: 85
- Layers: 17
- Nets: 186
- Stack layers: 17
- Board JSON validation: pass
- Stack JSON validation: pass

## Images / PDF Render
- pdftoppm available: True
- Pages converted: 18
- Output validation: pass

## Validation
- ok: True
- json_round_trip_ok: True
- required_outputs_ok: True
- image_outputs_ok: True
- strict_would_fail: True
- ready_for_thomsonlint_smoke_test: True

## Warnings
- WARN_EXAMPLES_FLAT_LAYOUT: Using examples compatibility mode with flat folder scan because pre_conversion tree is missing.
- WARN_IPC_STACKUP_UNAVAILABLE: Material/thickness stackup details unavailable; using known ordered layer metadata.
