# Converter usage

```bash
python3 pads_ascii_to_thomson_sch.py --netlist review_bundle/schematic/pads_netlist.asc --bom review_bundle/schematic/bom.csv --project my_board --output ./exports --pretty
python3 ipc2581_to_thomson.py review_bundle/layout/ipc2581.xml --project my_board --output ./exports --pretty
python3 altium_orcad_to_thomson_bundle.py --bundle ./review_bundle --project my_board --output ./exports --pretty
python3 altium_orcad_to_thomson_bundle.py --bundle ./review_bundle --project my_board --output ./exports --strict --pretty
python3 pads_ascii_to_thomson_sch.py --netlist review_bundle/schematic/pads_netlist.asc --inspect --project my_board
python3 ipc2581_to_thomson.py review_bundle/layout/ipc2581.xml --inspect
python3 -m pytest tests
```


## Phase 1 bundle converter skeleton

```bash
python3 thomson_bundle_converter.py <project_root> --dry-run --report-only
python3 thomson_bundle_converter.py <project_root> --pretty
python3 thomson_bundle_converter.py examples --dry-run --report-only
```

Notes:
- Phase 1 performs discovery/classification and report generation only.
- Deep BOM/PADS/IPC parsing is deferred to later phases.

## Phase 2 BOM parser integration

```bash
python3 thomson_bundle_converter.py examples --project-name example --pretty
python3 thomson_bundle_converter.py examples --project-name example --pretty --strict
python3 thomson_bundle_converter.py examples --dry-run --report-only
```

Notes:
- Phase 2 adds BOM CSV parsing and writes `<project>-bom.json` in non-dry-run, non-report-only mode.
- Phase 2 does not yet implement PADS/IPC/PDF deep conversion outputs.

## Phase 3 schematic parser integration

```bash
python3 thomson_bundle_converter.py examples --project-name example --pretty
python3 thomson_bundle_converter.py examples --project-name example --pretty --strict
python3 thomson_bundle_converter.py examples --dry-run --report-only
```

Notes:
- Phase 3 adds PADS ASCII schematic extraction and writes `<project>-thomson-export-sch.json` in non-dry-run, non-report-only mode.
- BOM metadata is merged into matching schematic components by refdes.

## Phase 4 IPC-2581 board/stack parser integration

```bash
python3 thomson_bundle_converter.py examples --project-name example --pretty
python3 thomson_bundle_converter.py examples --project-name example --pretty --strict
python3 thomson_bundle_converter.py examples --dry-run --report-only
```

Notes:
- Phase 4 adds IPC-2581 layout extraction and writes `<project>-thomson-export-brd.json` and `<project>-thomson-export-stack.json` in non-dry-run, non-report-only mode.
- Stack output remains a supplemental deterministic artifact when full material data is unavailable.

## Phase 5 PDF-to-PNG rendering integration

```bash
python3 thomson_bundle_converter.py examples --project-name example --pretty
python3 thomson_bundle_converter.py examples --project-name example --pretty --strict
python3 thomson_bundle_converter.py examples --dry-run --report-only
```

Notes:
- Phase 5 adds PDF rendering via `pdftoppm`.
- New options: `--schematic-pdf-dpi` (default 300), `--gerber-pdf-dpi` (default 400).
- If `pdftoppm` is missing, warning includes install hint: `sudo apt install poppler-utils`.
