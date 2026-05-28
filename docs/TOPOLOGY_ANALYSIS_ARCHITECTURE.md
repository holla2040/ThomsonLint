# ThomsonLint Topology-Aware PCB Analysis Architecture

## 1. Executive Summary

ThomsonLint should evolve from geometry-centered board review into topology-aware PCB analysis. The key architectural change is that electrical topology must be constructed deterministically from structured design artifacts, not inferred by AI.

AI has one bounded role: extract datasheet-derived part behavior into structured, evidence-backed JSON. That includes supply pins, regulator input/output behavior, current limits, connector ratings, fuse ratings, thermal limits, pin roles, and voltage constraints. The extracted data is not trusted until validated by scripts.

Deterministic scripts then:

- Validate AI-generated `part_info` JSON.
- Build a topology graph from schematic, board, stackup, BOM, datasheet manifest, and validated `part_info`.
- Propagate rails through sources, pass-through devices, regulators, switches, fuses, ferrites, jumpers, and connectors.
- Assign nominal, maximum, bounded, or unresolved current models to rails and branches.
- Associate topology nodes and branches with board copper geometry.
- Run geometry, thermal, DFM, voltage-spacing, and electrical-criticality calculations.
- Generate evidence artifacts that later phases can convert into findings.

The primary new output is a deterministic topology map:

```text
exports/{project}-topology-map.json
```

This topology map becomes the bridge between electrical intent and physical layout. It allows later checks to answer questions current geometry helpers cannot answer reliably, such as which copper neck-down carries full feeder current, which branch feeds only one load, which vias are in the regulator output path, or which clearance pair involves a propagated high-voltage rail.

## 2. Problem Statement

Current helpers can inspect board geometry, stackup, schematic nets, BOM rows, datasheets, and cross-source evidence. They can calculate trace widths, net clearances, differential-pair geometry, edge clearance, copper balance, voltage spacing from net names, and stackup-informed physical checks.

The limitation is that these checks operate mostly at the net or geometry level. Net-level checks are insufficient for current-aware review because one net can contain multiple electrical regions:

- A feeder trace carrying total rail current.
- A branch trace carrying one load.
- A neck-down between a connector and fuse.
- A regulator input path carrying input current.
- A regulator output path carrying downstream load current.
- A ferrite-fed analog island carrying only filtered analog current.
- A plane connected to many sinks with spatially distributed current.

Without topology, ThomsonLint cannot reliably assign current to:

- Individual component load segments.
- Branch traces.
- Pass-through components.
- Feeder paths.
- Power planes.
- Neck-downs.
- Vias and via arrays.
- Connector, fuse, ferrite, switch, and regulator paths.

Voltage clearance also needs topology. Parsing voltage from net names catches simple cases like `24V`, `+5V`, or `3V3`, but it does not fully resolve:

- Rails renamed after fuses or ferrites.
- Regulator outputs with opaque net names.
- Switched rails.
- Isolated converter outputs.
- Connector pins with external voltage definitions.
- Sense, feedback, and enable pins that are voltage constrained but not rail sources.

DFM severity should depend on electrical role. A narrow trace, via annular ring issue, acid trap, copper bottleneck, or edge clearance problem is more important on a high-current feeder, high-voltage rail, switch node, sensitive analog rail, or power connector than on a low-risk static GPIO.

The largest missing input is structured IC/device behavior. CAD data normally does not contain:

- IC supply pin roles.
- Current draw by rail.
- Absolute maximum versus recommended operating limits.
- Regulator input/output/pass-through behavior.
- Connector pin current ratings.
- Fuse hold/trip current.
- Ferrite rated current and impedance.
- Thermal package limits.
- Pin voltage constraints.
- Signal role hints such as USB, CAN, RS485, LVDS, clock, or memory bus pins.

That information exists primarily in datasheets. AI can help extract it, but topology construction and calculations must remain deterministic.

## 3. Responsibility Boundary

| Area | Allowed responsibilities |
| --- | --- |
| AI may | Read datasheets; extract pin roles; extract current, voltage, and thermal limits; extract operating current modes; extract package and current ratings; cite evidence pages/text; assign confidence to extracted fields. |
| AI may not | Infer board topology; decide pass/fail gates; create final findings directly; invent missing current values; assign copper segment current without deterministic topology; perform final trace temperature calculations. |
| Scripts must | Validate AI `part_info` JSON; build topology graph; propagate rails; classify sources, sinks, and pass-throughs; aggregate current; associate board copper geometry; run thermal, DFM, and electrical calculations; generate evidence artifacts; pass/fail gates deterministically. |

Boundary rules:

- AI output is evidence-backed input, not a calculation result.
- Every extracted numerical field should cite a datasheet evidence reference where possible.
- Missing or ambiguous values must become unresolved fields, not guessed values.
- Deterministic scripts must preserve uncertainty and confidence in downstream artifacts.
- Phase gates should validate artifact completeness and execution separately from compliance results.
- Final findings are generated only after validated evidence artifacts exist.

## 4. Proposed Data Artifacts

| Artifact | Producer | Timing | Purpose |
| --- | --- | --- | --- |
| `exports/part_info/{normalized_mpn}.json` | `scripts/part_info_extract.py` | After Phase 6 datasheet retrieval | One AI-extracted, evidence-backed part behavior file per unique MPN. |
| `exports/part_info/part_info_index.json` | `scripts/part_info_index.py` or `scripts/part_info_merge.py` | After extraction and validation | Index from normalized MPNs to part info files, BOM rows, refdes, manufacturers, extraction status, and validation status. |
| `exports/{project}-part-info-validation.json` | `scripts/part_info_validate.py` | After extraction or manual authoring | Schema, evidence, unit, confidence, and unresolved-field validation. |
| `exports/{project}-power-topology.json` | `scripts/topology_builder.py` | Optional focused output from topology build | Compact rail/source/sink/current summary for easier review and early debugging. |
| `exports/{project}-topology-map.json` | `scripts/topology_builder.py` | After schematic/BOM/part_info inputs are available | Primary deterministic graph artifact for rails, devices, branches, current models, voltage models, and copper links. |
| `exports/{project}-topology-validation.json` | `scripts/topology_validate.py` | After topology build | Validation for graph consistency, missing sources, unresolved loads, impossible values, circular propagation, and geometry mapping gaps. |
| `exports/{project}-topology-aware-geometry-review.json` | `scripts/topology_aware_geometry_checks.py` | Optional Phase 11 enhancement | Topology-aware trace, via, plane, clearance, criticality, and signal-role review evidence. |
| `exports/{project}-topology-aware-geometry-validation.json` | `scripts/topology_aware_geometry_checks.py` | Alongside topology-aware geometry review | Execution and artifact validation for topology-aware geometry checks. |

Minimal non-disruptive insertion:

- Keep existing Phase 6 datasheet manifest artifacts unchanged.
- Add `part_info` extraction after Phase 6.
- Add topology construction after Phase 10 stackup evidence and before Phase 11 DFM checks when artifacts are available.
- Allow existing Phase 11 to run without topology artifacts.
- Allow topology-aware Phase 11 checks to produce stronger evidence when topology artifacts exist.

## 5. part_info JSON Schema

`part_info` describes one unique manufacturer part number. It captures behavior from datasheets, not board-specific connectivity. It must not claim how the part is connected on a specific PCB.

Recommended file:

```text
exports/part_info/{normalized_mpn}.json
```

Top-level schema shape:

```json
{
  "schema_version": "1.0",
  "mpn": "TPS54302DDCR",
  "manufacturer": "Texas Instruments",
  "normalized_mpn": "tps54302ddcr",
  "component_category": "buck_regulator",
  "package": {
    "name": "SOT-23-6",
    "pin_count": 6,
    "thermal_pad": false,
    "evidence_refs": ["ds:p1:package"]
  },
  "datasheet_sources": [
    {
      "source_id": "ds",
      "local_path": "exports/datasheets/TPS54302DDCR.pdf",
      "url": "https://example.invalid/datasheet.pdf",
      "manufacturer_source": true,
      "retrieved_at_utc": "2026-05-28T00:00:00Z"
    }
  ],
  "extraction_method": {
    "type": "ai_datasheet_extraction",
    "model": "model-name",
    "prompt_version": "part-info-v1",
    "extracted_at_utc": "2026-05-28T00:00:00Z",
    "text_extraction_tool": "pdftotext",
    "human_reviewed": false
  },
  "pin_roles": [],
  "power_behavior": {},
  "load_behavior": {},
  "pass_through_behavior": {},
  "signal_behavior": {},
  "voltage_limits": [],
  "current_limits": [],
  "thermal_behavior": {},
  "operating_modes": [],
  "confidence": {},
  "unresolved_fields": [],
  "evidence": []
}
```

### Shared numeric value shape

Every extracted numerical field should use this shape where practical:

```json
{
  "value": 3.3,
  "unit": "V",
  "min": 3.0,
  "typ": 3.3,
  "max": 3.6,
  "condition": "recommended operating range",
  "evidence_ref": "ds:p6:recommended-operating",
  "confidence": 0.92
}
```

Rules:

- Use `value` for a single exact extracted value.
- Use `min`, `typ`, and `max` when the datasheet table provides ranges.
- Include `condition` whenever the value depends on voltage, temperature, load, mode, frequency, airflow, pin grouping, or package.
- Include `evidence_ref` for every extracted numeric field when possible.
- Distinguish absolute maximum ratings from recommended operating values.
- Distinguish device current limits from actual board load current.
- Mark unavailable values as unresolved rather than inventing them.

### pin_roles

Each pin role record:

```json
{
  "pin": "5",
  "pin_name": "VIN",
  "role": "power",
  "direction": "input",
  "power_domain": "vin",
  "associated_supply": null,
  "current_role": "source_input",
  "voltage_range_v": {
    "min": 4.5,
    "max": 28.0,
    "unit": "V",
    "condition": "recommended operating input voltage",
    "evidence_ref": "ds:p6:vin-range",
    "confidence": 0.95
  },
  "notes": "Buck regulator input supply pin.",
  "evidence_refs": ["ds:p3:pin-functions", "ds:p6:recommended-operating"]
}
```

Allowed `role` values:

- `power`
- `ground`
- `enable`
- `feedback`
- `switch`
- `sense`
- `signal`
- `no_connect`
- `thermal`
- `mechanical`
- `unknown`

Allowed `direction` values:

- `input`
- `output`
- `bidirectional`
- `passive`
- `not_connected`
- `unknown`

Allowed `current_role` values:

- `source_input`
- `source_output`
- `sink_supply`
- `return`
- `pass_through_input`
- `pass_through_output`
- `sense_only`
- `signal_only`
- `unknown`

### power_behavior

Required shape:

```json
{
  "device_role": "source",
  "input_pins": ["VIN"],
  "output_pins": ["SW"],
  "ground_pins": ["GND"],
  "enable_pins": ["EN"],
  "feedback_pins": ["FB"],
  "nominal_current_by_rail": [],
  "max_current_by_rail": [
    {
      "rail": "VOUT",
      "max": 3.0,
      "unit": "A",
      "condition": "switch current limit / output capability, not board load",
      "evidence_ref": "ds:p1:features",
      "confidence": 0.88
    }
  ],
  "quiescent_current_a": {
    "typ": 0.00011,
    "unit": "A",
    "condition": "non-switching, VIN=12 V",
    "evidence_ref": "ds:p6:iq",
    "confidence": 0.8
  },
  "standby_current_a": null,
  "peak_current_a": null,
  "max_output_current_a": {
    "max": 3.0,
    "unit": "A",
    "condition": "device capability, not actual board load",
    "evidence_ref": "ds:p1:features",
    "confidence": 0.88
  },
  "efficiency_data": [
    {
      "input_v": 12.0,
      "output_v": 5.0,
      "load_a": 1.0,
      "efficiency": 0.9,
      "condition": "from typical efficiency curve",
      "evidence_ref": "ds:p8:efficiency-curve",
      "confidence": 0.65
    }
  ],
  "assumptions_allowed": false
}
```

Allowed `device_role` values:

- `source`
- `sink`
- `pass_through`
- `transformer`
- `passive`
- `mixed`
- `unknown`

### pass_through_behavior

For fuses, ferrites, zero-ohm resistors, jumpers, switches, connectors, and sense resistors:

```json
{
  "is_pass_through": true,
  "pass_through_type": "fuse",
  "input_pins": ["1"],
  "output_pins": ["2"],
  "bidirectional": true,
  "fuse_hold_current_a": {
    "typ": 1.1,
    "unit": "A",
    "condition": "25 C",
    "evidence_ref": "ds:p2:hold-current",
    "confidence": 0.93
  },
  "fuse_trip_current_a": {
    "typ": 2.2,
    "unit": "A",
    "condition": "25 C",
    "evidence_ref": "ds:p2:trip-current",
    "confidence": 0.93
  },
  "ferrite_rated_current_a": null,
  "ferrite_impedance_ohm": null,
  "zero_ohm_resistor_rating_a": null,
  "jumper_rating_a": null,
  "switch_current_rating_a": null,
  "connector_pin_current_rating_a": null,
  "current_sense_resistor_rating_w": null,
  "evidence_refs": ["ds:p2:electrical-characteristics"]
}
```

Supported pass-through fields:

- `fuse_hold_current_a`
- `fuse_trip_current_a`
- `ferrite_rated_current_a`
- `ferrite_impedance_ohm`
- `zero_ohm_resistor_rating_a`
- `jumper_rating_a`
- `switch_current_rating_a`
- `connector_pin_current_rating_a`
- `current_sense_resistor_rating_w`

### Example 1: buck regulator

```json
{
  "schema_version": "1.0",
  "mpn": "TPS54302DDCR",
  "manufacturer": "Texas Instruments",
  "normalized_mpn": "tps54302ddcr",
  "component_category": "buck_regulator",
  "package": {"name": "SOT-23-6", "pin_count": 6, "thermal_pad": false},
  "pin_roles": [
    {"pin": "5", "pin_name": "VIN", "role": "power", "direction": "input", "current_role": "source_input", "evidence_refs": ["ds:p3"]},
    {"pin": "1", "pin_name": "SW", "role": "switch", "direction": "output", "current_role": "source_output", "evidence_refs": ["ds:p3"]},
    {"pin": "2", "pin_name": "GND", "role": "ground", "direction": "passive", "current_role": "return", "evidence_refs": ["ds:p3"]},
    {"pin": "3", "pin_name": "FB", "role": "feedback", "direction": "input", "current_role": "sense_only", "evidence_refs": ["ds:p3"]},
    {"pin": "4", "pin_name": "EN", "role": "enable", "direction": "input", "current_role": "signal_only", "evidence_refs": ["ds:p3"]}
  ],
  "power_behavior": {
    "device_role": "source",
    "input_pins": ["VIN"],
    "output_pins": ["SW"],
    "ground_pins": ["GND"],
    "enable_pins": ["EN"],
    "feedback_pins": ["FB"],
    "max_output_current_a": {"max": 3.0, "unit": "A", "condition": "device output capability", "evidence_ref": "ds:p1", "confidence": 0.9},
    "assumptions_allowed": false
  },
  "confidence": {"overall": 0.88},
  "unresolved_fields": ["board_actual_output_current"],
  "evidence": [{"id": "ds:p3", "source": "exports/datasheets/TPS54302DDCR.pdf", "page": 3, "locator": "pin functions"}]
}
```

### Example 2: MCU or FPGA multi-rail sink

```json
{
  "schema_version": "1.0",
  "mpn": "STM32F407VGT6",
  "manufacturer": "STMicroelectronics",
  "normalized_mpn": "stm32f407vgt6",
  "component_category": "mcu",
  "pin_roles": [
    {"pin": "19", "pin_name": "VDD", "role": "power", "direction": "input", "power_domain": "digital_core_io", "current_role": "sink_supply", "evidence_refs": ["ds:p47"]},
    {"pin": "13", "pin_name": "VDDA", "role": "power", "direction": "input", "power_domain": "analog", "current_role": "sink_supply", "evidence_refs": ["ds:p47"]},
    {"pin": "12", "pin_name": "VSS", "role": "ground", "direction": "passive", "current_role": "return", "evidence_refs": ["ds:p47"]}
  ],
  "power_behavior": {
    "device_role": "sink",
    "input_pins": ["VDD", "VDDA", "VBAT"],
    "output_pins": [],
    "ground_pins": ["VSS", "VSSA"],
    "nominal_current_by_rail": [
      {"rail": "VDD", "typ": 0.08, "unit": "A", "condition": "example run mode at stated frequency; board mode unresolved", "evidence_ref": "ds:p112", "confidence": 0.62}
    ],
    "max_current_by_rail": [],
    "assumptions_allowed": false
  },
  "operating_modes": [
    {"mode": "run", "current_a": {"typ": 0.08, "unit": "A", "condition": "datasheet example mode", "evidence_ref": "ds:p112", "confidence": 0.62}},
    {"mode": "standby", "current_a": {"typ": 0.00001, "unit": "A", "condition": "standby mode", "evidence_ref": "ds:p118", "confidence": 0.8}}
  ],
  "unresolved_fields": ["actual_clock_frequency", "enabled_peripherals", "board_current_by_rail"],
  "confidence": {"overall": 0.7}
}
```

### Example 3: connector

```json
{
  "schema_version": "1.0",
  "mpn": "043045-0414",
  "manufacturer": "Molex",
  "normalized_mpn": "0430450414",
  "component_category": "connector",
  "pin_roles": [
    {"pin": "1", "pin_name": "1", "role": "power", "direction": "bidirectional", "current_role": "pass_through_input", "evidence_refs": ["ds:p2"]},
    {"pin": "2", "pin_name": "2", "role": "power", "direction": "bidirectional", "current_role": "pass_through_input", "evidence_refs": ["ds:p2"]}
  ],
  "power_behavior": {"device_role": "pass_through", "input_pins": ["1", "2"], "output_pins": ["3", "4"], "ground_pins": [], "assumptions_allowed": false},
  "pass_through_behavior": {
    "is_pass_through": true,
    "pass_through_type": "connector",
    "connector_pin_current_rating_a": {"max": 5.0, "unit": "A", "condition": "per pin, datasheet rating", "evidence_ref": "ds:p2", "confidence": 0.85}
  },
  "unresolved_fields": ["which_pins_are_power_on_board"],
  "confidence": {"overall": 0.78}
}
```

### Example 4: fuse/ferrite/pass-through component

```json
{
  "schema_version": "1.0",
  "mpn": "BLM18AG601SN1D",
  "manufacturer": "Murata",
  "normalized_mpn": "blm18ag601sn1d",
  "component_category": "ferrite_bead",
  "pin_roles": [
    {"pin": "1", "pin_name": "1", "role": "power", "direction": "bidirectional", "current_role": "pass_through_input", "evidence_refs": ["ds:p1"]},
    {"pin": "2", "pin_name": "2", "role": "power", "direction": "bidirectional", "current_role": "pass_through_output", "evidence_refs": ["ds:p1"]}
  ],
  "power_behavior": {"device_role": "pass_through", "input_pins": ["1"], "output_pins": ["2"], "ground_pins": [], "assumptions_allowed": false},
  "pass_through_behavior": {
    "is_pass_through": true,
    "pass_through_type": "ferrite",
    "ferrite_rated_current_a": {"max": 0.5, "unit": "A", "condition": "rated current", "evidence_ref": "ds:p1", "confidence": 0.92},
    "ferrite_impedance_ohm": {"typ": 600, "unit": "ohm", "condition": "100 MHz", "evidence_ref": "ds:p1", "confidence": 0.92}
  },
  "confidence": {"overall": 0.9}
}
```

### Example 5: passive resistor/capacitor

```json
{
  "schema_version": "1.0",
  "mpn": "GRM155R71H104KE14D",
  "manufacturer": "Murata",
  "normalized_mpn": "grm155r71h104ke14d",
  "component_category": "capacitor",
  "pin_roles": [
    {"pin": "1", "pin_name": "1", "role": "passive", "direction": "passive", "current_role": "unknown", "evidence_refs": ["ds:p1"]},
    {"pin": "2", "pin_name": "2", "role": "passive", "direction": "passive", "current_role": "unknown", "evidence_refs": ["ds:p1"]}
  ],
  "power_behavior": {"device_role": "passive", "input_pins": [], "output_pins": [], "ground_pins": [], "assumptions_allowed": false},
  "voltage_limits": [
    {"limit_type": "rated_voltage", "max": 50.0, "unit": "V", "condition": "rated voltage", "evidence_ref": "ds:p1", "confidence": 0.9}
  ],
  "load_behavior": {"acts_as_load": false, "notes": "Decoupling capacitor; no DC load current model."},
  "unresolved_fields": ["dc_bias_derating_curve_if_needed"],
  "confidence": {"overall": 0.84}
}
```

## 6. AI Datasheet Extraction Strategy

Required scripts:

- `scripts/part_info_extract.py`
- `scripts/part_info_validate.py`
- `scripts/part_info_index.py` or `scripts/part_info_merge.py`

### Extraction flow

1. Read `exports/{project}-bom.json`.
2. Normalize unique MPNs using the same conservative conventions as datasheet retrieval.
3. Locate local datasheet PDFs from `exports/datasheets/datasheet_manifest.jsonl`.
4. For each unique MPN, extract relevant text, tables, and page references from local PDFs.
5. Ask AI to produce strict JSON only, matching `part_info` schema.
6. Validate the JSON against schema.
7. Normalize units.
8. Reject invalid JSON or mark unresolved fields when evidence is missing.
9. Store one JSON file per MPN under `exports/part_info/`.
10. Build `exports/part_info/part_info_index.json`.
11. Emit `exports/{project}-part-info-validation.json`.

### Prompt strategy

The extraction prompt must require:

- JSON only.
- No Markdown.
- No prose outside JSON.
- No invented fields.
- Evidence references for extracted values.
- `unknown` or `unresolved_fields` when datasheet data is absent.
- Clear distinction between absolute maximum and recommended operating conditions.
- Clear distinction between device maximum rating and actual board load current.
- Clear distinction between typical, maximum, peak, standby, sleep, and quiescent currents.
- Clear distinction between output current capability and downstream current demand.
- Confidence scores for extracted fields and overall extraction.

Prompt rules:

```text
You extract datasheet-derived part behavior only.
Do not infer board topology.
Do not decide whether a design passes or fails.
Do not invent current values.
Return strict JSON only.
Every numerical value must include unit, condition, evidence_ref, and confidence when possible.
If the datasheet does not state a value, mark it unknown and add an unresolved field.
```

### Validation strategy

`scripts/part_info_validate.py` should perform:

- JSON parse validation.
- Schema validation.
- Required top-level key validation.
- Unit normalization for voltage, current, resistance, power, temperature, and impedance.
- Numeric sanity checks.
- Evidence reference presence checks for numerical fields.
- Evidence reference existence checks against `evidence[]`.
- Datasheet path existence checks.
- Confidence range validation, normally `0.0 <= confidence <= 1.0`.
- Unresolved-field tracking.
- Human-review-needed flag generation.

Validation should mark human review needed when:

- Required behavior fields are missing for an active IC.
- Numerical fields lack evidence.
- Confidence is below threshold.
- AI extracted a value from an absolute maximum table but labeled it as operating.
- A current limit appears to be used as nominal current.
- Pin count conflicts with package metadata.
- Pin names are internally inconsistent.
- Datasheet source is not local.

Suggested validation artifact:

```json
{
  "phase": "part_info_validation",
  "project": "example",
  "generated_at_utc": "2026-05-28T00:00:00Z",
  "schema_version": "1.0",
  "summary": {
    "part_info_files_checked": 42,
    "valid_files": 35,
    "invalid_files": 2,
    "human_review_needed": 5,
    "missing_part_info_count": 8
  },
  "validations": [
    {"check": "schema_validation", "passed": true},
    {"check": "evidence_required_for_numerics", "passed": true},
    {"check": "unit_normalization", "passed": true}
  ],
  "parts": [],
  "errors": [],
  "overall_pass": true
}
```

## 7. Topology Map JSON Schema

The topology map is deterministic board-specific evidence. It combines schematic connectivity, BOM identity, validated `part_info`, board geometry, and stackup context.

Top-level shape:

```json
{
  "schema_version": "1.0",
  "project": "example",
  "generated_at_utc": "2026-05-28T00:00:00Z",
  "sources": {
    "schematic": "exports/example-thomson-export-sch.json",
    "board": "exports/example-thomson-export-brd.json",
    "stackup": "exports/example-thomson-export-stack.json",
    "bom": "exports/example-bom.json",
    "part_info_index": "exports/part_info/part_info_index.json",
    "datasheet_manifest": "exports/datasheets/datasheet_manifest.jsonl"
  },
  "assumptions": [],
  "graph_summary": {},
  "nets": [],
  "power_rails": [],
  "devices": [],
  "pins": [],
  "pass_through_edges": [],
  "source_nodes": [],
  "sink_nodes": [],
  "branches": [],
  "copper_geometry_links": [],
  "current_models": [],
  "voltage_models": [],
  "unresolved": [],
  "validation": {}
}
```

### devices

```json
{
  "refdes": "U1",
  "mpn": "TPS54302DDCR",
  "manufacturer": "Texas Instruments",
  "device_role": "source",
  "input_nets": ["VIN_FUSED"],
  "output_nets": ["SW_5V"],
  "supply_nets": ["VIN_FUSED"],
  "ground_nets": ["GND"],
  "signal_nets": ["EN_5V", "FB_5V"],
  "part_info_ref": "exports/part_info/tps54302ddcr.json",
  "current_model": {
    "model_id": "cm_U1",
    "type": "regulator_source",
    "basis": "downstream_aggregation",
    "confidence": 0.75
  },
  "confidence": 0.82,
  "unresolved": ["output_voltage_from_feedback_not_implemented_v0"]
}
```

### rails

```json
{
  "net_name": "3V3",
  "nominal_voltage_v": 3.3,
  "voltage_source": "regulator_output",
  "source_components": ["U2"],
  "pass_through_components": ["FB1"],
  "sink_components": ["U3", "U4", "U5"],
  "total_nominal_current_a": 0.18,
  "total_max_current_a": 0.42,
  "unresolved_current_a": null,
  "confidence": 0.72
}
```

### branches

```json
{
  "branch_id": "br_3v3_fb1_downstream",
  "net": "3V3_A",
  "source_ref": "FB1.2",
  "sink_refs": ["U4.VDDA", "U5.VDD"],
  "upstream_branch_id": "br_3v3_reg_to_fb1",
  "downstream_branch_ids": [],
  "pass_through_refdes": ["FB1"],
  "estimated_current_a": 0.035,
  "current_basis": "sink_sum_typical",
  "copper_geometry_refs": ["track:123", "via:45", "zone:3"],
  "thermal_check_required": true,
  "unresolved_flags": []
}
```

### copper_geometry_links

```json
{
  "link_id": "cgl_001",
  "net": "3V3",
  "branch_id": "br_3v3_reg_to_fb1",
  "tracks": ["track:123", "track:124"],
  "vias": ["via:45"],
  "zones": ["zone:3"],
  "pads": ["U2.3", "FB1.1"],
  "layer": "TOP",
  "source_proximity": {"ref": "U2.3", "distance_mm": 0.25},
  "sink_proximity": {"ref": "FB1.1", "distance_mm": 0.3},
  "branch_assignment_confidence": 0.6
}
```

### Example 1: connector -> fuse -> regulator input

```json
{
  "power_rails": [
    {"net_name": "VIN_CONN", "nominal_voltage_v": 24.0, "voltage_source": "external_connector", "source_components": ["J1"], "pass_through_components": ["F1"], "sink_components": ["U1"], "total_nominal_current_a": null, "total_max_current_a": null, "unresolved_current_a": null, "confidence": 0.68}
  ],
  "pass_through_edges": [
    {"edge_id": "pte_F1", "refdes": "F1", "type": "fuse", "from_net": "VIN_CONN", "to_net": "VIN_FUSED", "current_limit_a": 1.1, "limit_basis": "hold_current", "confidence": 0.9}
  ],
  "branches": [
    {"branch_id": "br_j1_to_f1", "net": "VIN_CONN", "source_ref": "J1.1", "sink_refs": ["F1.1"], "estimated_current_a": null, "current_basis": "unresolved_external_source_load", "thermal_check_required": true, "unresolved_flags": ["external_input_current_unknown"]},
    {"branch_id": "br_f1_to_u1", "net": "VIN_FUSED", "source_ref": "F1.2", "sink_refs": ["U1.VIN"], "estimated_current_a": null, "current_basis": "regulator_input_current_unresolved", "thermal_check_required": true, "unresolved_flags": ["downstream_regulator_load_unknown"]}
  ]
}
```

### Example 2: regulator output -> ferrite -> downstream analog rail

```json
{
  "pass_through_edges": [
    {"edge_id": "pte_FB1", "refdes": "FB1", "type": "ferrite", "from_net": "3V3", "to_net": "3V3_A", "current_limit_a": 0.5, "limit_basis": "rated_current", "confidence": 0.92}
  ],
  "power_rails": [
    {"net_name": "3V3", "nominal_voltage_v": 3.3, "voltage_source": "regulator_output", "source_components": ["U2"], "pass_through_components": ["FB1"], "sink_components": ["U3"], "total_nominal_current_a": 0.2, "total_max_current_a": 0.5, "unresolved_current_a": null, "confidence": 0.75},
    {"net_name": "3V3_A", "nominal_voltage_v": 3.3, "voltage_source": "pass_through_from_3V3", "source_components": ["FB1"], "pass_through_components": [], "sink_components": ["U4"], "total_nominal_current_a": 0.025, "total_max_current_a": 0.06, "unresolved_current_a": null, "confidence": 0.7}
  ]
}
```

### Example 3: power plane with multiple sinks

```json
{
  "power_rails": [
    {"net_name": "5V", "nominal_voltage_v": 5.0, "voltage_source": "regulator_output", "source_components": ["U1"], "pass_through_components": [], "sink_components": ["U2", "U3", "J2"], "total_nominal_current_a": 0.85, "total_max_current_a": 1.8, "unresolved_current_a": 0.2, "confidence": 0.64}
  ],
  "copper_geometry_links": [
    {"link_id": "cgl_5v_plane_l2", "net": "5V", "branch_id": null, "tracks": [], "vias": ["via:10", "via:11"], "zones": ["zone:5"], "pads": ["U1.VOUT", "U2.VDD", "U3.VDD", "J2.1"], "layer": "LAYER2", "branch_assignment_confidence": 0.35}
  ],
  "current_models": [
    {"model_id": "cm_5v_plane", "target": "rail:5V", "type": "plane_distributed", "nominal_current_a": 0.85, "max_current_a": 1.8, "basis": "sink_sum_with_unresolved_current", "confidence": 0.64}
  ]
}
```

### Example 4: unresolved rail/load

```json
{
  "power_rails": [
    {"net_name": "V_AUX", "nominal_voltage_v": null, "voltage_source": "unknown", "source_components": [], "pass_through_components": [], "sink_components": ["U9"], "total_nominal_current_a": null, "total_max_current_a": null, "unresolved_current_a": null, "confidence": 0.2}
  ],
  "unresolved": [
    {"id": "unres_v_aux_source", "type": "power_net_no_source", "net": "V_AUX", "affected_refdes": ["U9"], "required_for": ["voltage_clearance", "trace_current"], "human_review_needed": true},
    {"id": "unres_u9_current", "type": "sink_current_unknown", "net": "V_AUX", "affected_refdes": ["U9"], "part_info_ref": "exports/part_info/u9part.json", "human_review_needed": true}
  ]
}
```

## 8. Deterministic Topology Builder Algorithm

The proposed builder is:

```text
scripts/topology_builder.py
```

It should produce:

```text
exports/{project}-power-topology.json
exports/{project}-topology-map.json
```

### 8.1 Parse Inputs

Inputs:

- `exports/{project}-thomson-export-sch.json`
- `exports/{project}-thomson-export-brd.json`
- `exports/{project}-thomson-export-stack.json`
- `exports/{project}-bom.json`
- `exports/part_info/part_info_index.json`
- `exports/datasheets/datasheet_manifest.jsonl`

Parsing requirements:

- Reuse existing schematic graph conventions from `scripts/schematic_helpers.py`.
- Reuse BOM parsing conventions from `scripts/bom_helpers.py` and `scripts/datasheet_helper.py`.
- Reuse board extraction helpers from `scripts/geometry_helpers.py` for routes, pads, vias, polygons, units, and net names.
- Reuse stackup unit conversion and layer interpretation patterns from `scripts/stackup_helpers.py` and `geometry_helpers.py`.
- Preserve source file paths in topology `sources`.
- Record missing inputs as validation blockers or limitations depending on phase policy.

### 8.2 Build Schematic Net Graph

Graph nodes:

- Component pins.
- Nets.
- Components.
- Power rails.
- Ground rails.

Edges:

- Component pin connected to net.
- Component owns pin.
- Pass-through component connects input net to output net.
- Regulator transforms input rail to output rail.
- Connector exposes external source/sink pins.
- Ground pins connect devices to reference nets.

Initial graph model:

```text
component -> pin -> net
net -> pin -> component
pass_through_component: net_a <-> net_b
regulator_component: input_net -> output_net
sink_component: supply_net -> load_current_model
source_component: output_net -> source_current_model
```

### 8.3 Classify Nets

Power net detection should combine naming, schematic connectivity, and part_info roles.

Power net name patterns:

- `24V`, `12V`, `5V`, `3V3`, `1V8`, `2V5`
- `+5V`, `+12V`, `-12V`
- `V24P0`, `V5P0`, `V3P3`, `V1P8`
- `VIN`, `VOUT`, `VBAT`, `VBUS`, `VSYS`
- `VCC`, `VDD`, `AVDD`, `DVDD`, `PVDD`
- `VREF` when connected to reference or analog power pins

Ground net detection:

- `GND`
- `AGND`
- `DGND`
- `PGND`
- `SGND`
- `CHASSIS`
- `EARTH`
- `VSS`

Signal net detection:

- Everything else unless part_info or schematic symbols indicate power role.
- Nets connected only to signal pins remain signals even if names are ambiguous.

Classification precedence:

1. Ground pin connectivity from part_info.
2. Explicit power pin connectivity from part_info.
3. Regulator output inference from part_info plus schematic pin mapping.
4. Connector power pin metadata when available.
5. Net name patterns.
6. Existing CAD net class or signal classification if present.
7. Unknown.

### 8.4 Classify Components

Use BOM, schematic pins, board placement, and part_info.

Classifications:

- `source`
- `sink`
- `pass_through`
- `regulator`
- `transformer`
- `protection`
- `passive_load`
- `signal_only`
- `unknown`

Rules:

- Regulators and converters are source/transformer devices: input rail is not the same as output rail.
- Fuses, ferrites, jumpers, zero-ohm resistors, current sense resistors, switches, relays, and connectors may be pass-through devices.
- ICs with supply pins and no output rail are sinks unless part_info says otherwise.
- LEDs and resistor loads may be passive loads when connected between rails.
- Capacitors are not DC loads for current aggregation, but they matter for decoupling and inrush in later work.
- Unknown devices connected to power nets should become unresolved sinks or unresolved pass-throughs, not ignored.

### 8.5 Propagate Power Rails

Handle:

- Connectors as external sources.
- Fuses.
- Ferrites.
- Jumpers.
- Zero-ohm resistors.
- Current sense resistors.
- Load switches.
- Regulators.
- LDOs.
- Buck converters.
- Boost converters.
- Buck-boost converters.
- Isolated converters.
- Transformers.

Propagation rules:

- Pass-through devices propagate voltage unless part_info marks voltage drop behavior.
- Ferrites propagate nominal voltage but add current rating and impedance metadata.
- Fuses propagate nominal voltage but add hold/trip current constraints.
- Switches propagate voltage only when default state is known; otherwise mark switched rail unresolved.
- Regulators create new output rails; do not assume output voltage unless derived from explicit data, net name, CAD metadata, or supported feedback calculation.
- Isolated converters create isolated output domains; do not merge grounds unless schematic connectivity proves it.
- Connectors can be external sources or sinks. If direction is unknown, record ambiguity.

### 8.6 Assign Current

Priority order:

1. Explicit board requirement if available.
2. `part_info` typical/max current per rail.
3. Resistor, LED, or passive load calculations from schematic values.
4. Downstream aggregation through topology.
5. Regulator, fuse, connector, switch, and ferrite current limits as caps or validation limits.
6. Conservative class defaults only when clearly marked as assumptions.
7. Unresolved current marker.

Important current rules:

- Distinguish current draw from current limit.
- Distinguish typical, maximum, standby, quiescent, peak, and inrush current.
- Carry uncertainty and confidence.
- Never silently use a max rating as actual load.
- Device current rating can validate a path but does not by itself define board current.
- Regulator input current should be derived from output load, efficiency, input voltage, and output voltage when enough data exists; otherwise unresolved.
- Connector current rating should be checked against aggregated current per pin when pin mapping exists.
- Fuse hold/trip current should validate steady-state and fault assumptions, not define load current.

Current model categories:

- `explicit_requirement`
- `datasheet_typical`
- `datasheet_max`
- `calculated_passive_load`
- `downstream_aggregation`
- `rating_limit_only`
- `class_default_assumption`
- `unresolved`

### 8.7 Associate Copper Geometry

Start simple and grow precision over time.

Level 0: net-level current only

- Map rail current to every copper object on the same net.
- Conservative for checks, but may overstate branch current.
- Good first milestone for identifying obviously undersized rails.

Level 1: source/sink pin proximity on same net

- Associate tracks, vias, zones, and pads near known source/sink pins.
- Improve feeder versus local branch distinction.
- Use distance and same-net constraints only.

Level 2: graph of tracks/vias/pads/zones

- Build physical copper connectivity graph.
- Nodes are route endpoints, pads, vias, zone contact regions.
- Edges are copper segments and via transitions.

Level 3: branch path extraction

- Extract likely paths from source pins through pass-through devices to sink pins.
- Assign branch current from downstream aggregation.
- Detect neck-downs and bottlenecks on path edges.

Level 4: plane current spreading approximation

- Model zones/planes with source/sink distribution.
- Approximate constrictions, thermal relief bottlenecks, via arrays, and local copper widths.
- Treat results as approximate and confidence-scored.

### 8.8 Validation

`scripts/topology_validate.py` must detect:

- Power nets with no source.
- Power nets with sinks but no current model.
- Source outputs with no sinks.
- Pass-through chains that cannot be resolved.
- Regulator outputs with no voltage estimate.
- Devices with missing part_info.
- Copper objects not mappable to topology.
- Impossible current or voltage values.
- Circular rail propagation.
- Duplicate refdes or mismatched MPN references.
- Part_info package or pin count conflicts.
- Schematic pins that cannot be matched to part_info pins.
- Rails joined through signal-only pins.
- Ground domains merged without schematic evidence.

Validation output should separate:

- `execution_pass`
- `artifact_validation_pass`
- `topology_consistency_pass`
- `unresolved_items_present`
- `human_review_needed`
- `phase_gate_passed`

Compliance-like problems should not hide successful execution. This follows the existing Phase 11 and Phase 16 pattern.

## 9. Topology-Aware Geometry/DFM/Thermal Checks

Existing helpers should evolve without breaking current callers.

Two acceptable implementation paths:

1. Add `scripts/topology_aware_geometry_checks.py` as a new module that imports existing geometry and Saturn helpers.
2. Refactor `scripts/geometry_helpers.py` into topology-aware modules after the new behavior is stable.

The first path is preferred for PR-sized delivery.

### Trace Temperature

Use:

- Branch current from topology.
- Copper thickness from stackup.
- Trace width and length from board geometry.
- Layer external/internal classification.
- IPC-2152 or Saturn-style approximations where available.
- I^2R heating estimate.

Outputs should include:

- Trace or segment reference.
- Branch ID.
- Net name.
- Current basis.
- Estimated current.
- Width.
- Copper thickness.
- Layer.
- Calculated temperature rise.
- Limit.
- Confidence.
- Unresolved flags.

### Via Current

Use:

- Branch current through via stacks.
- Via barrel geometry.
- Drill diameter and finished hole when available.
- Plating assumptions when not available.
- Count of parallel vias.
- Thermal derating.

Validation must distinguish:

- One via carrying full branch current.
- Multiple parallel vias sharing current.
- Unknown current sharing.
- Via-in-pad or thermal via arrays.

### Plane / Pour Current

Use:

- Total rail current.
- Source/sink distribution.
- Neck-down detection.
- Thermal relief bottlenecks.
- Via array bottlenecks.
- Local copper width approximations.

Early milestone:

- Net-level plane association.
- Identify narrow exits from pads/zones.
- Flag zones with high rail current and low mapping confidence.

Later milestone:

- Current spreading approximation.
- Local constriction analysis.
- Thermal relief derating.

### Clearance

Use:

- Topology-resolved rail voltages.
- Voltage propagated through fuses, ferrites, switches, and jumpers.
- Regulator output voltages.
- Board JSON spacing and clearance calculations.
- IPC rule thresholds.

Do not rely solely on net names when topology provides a better voltage model.

### DFM Severity

Use:

- Electrical criticality.
- High-current nets.
- High-voltage nets.
- Switch nodes.
- Sensitive analog rails.
- Thermal pads.
- Power connectors.
- External connectors.
- Safety or chassis-related nets.

Severity modifiers should be evidence fields for later findings, not final findings in the helper output.

### Impedance / Signal Role

Use part_info pin roles to identify:

- USB.
- Ethernet.
- CAN.
- RS485.
- LVDS.
- Clock pins.
- Oscillator nets.
- High-speed memory buses.
- Controlled impedance candidates.

Do not attempt full impedance extraction in the first topology milestone. Treat signal role extraction as classification evidence that can improve candidate detection for existing differential-pair and impedance helpers.

## 10. Integration with Existing Phase Workflow

The current 22-phase architecture should be preserved. Do not replace existing Phase 11 immediately.

Preferred future phase model:

- Phase 6A: Datasheet Retrieval.
- Phase 6B: AI Part Info Extraction.
- Phase 6C: Part Info Validation.
- Phase 10A: Power Topology Construction.
- Phase 10B: Topology Validation.
- Phase 11: Topology-Aware DFM/Thermal/Electrical Checks.
- Phase 19: Findings from topology-aware evidence.

Minimal non-disruptive insertion into the current 22-phase structure:

- Add scripts runnable after Phase 6 and before Phase 11.
- Add artifacts consumed by Phase 11 when available.
- Existing workflow must still run when topology artifacts are absent.
- Topology-aware checks should produce stronger results when topology artifacts are present.
- The pre-findings gate should eventually accept topology validation as optional until stable.
- Once stable, topology gates can become required for projects with enough schematic/BOM/part_info evidence.

Recommended incremental behavior:

- Phase 6 remains datasheet retrieval only.
- Phase 14 remains datasheet evidence review and does not become a topology builder.
- Topology construction is a deterministic evidence sub-pipeline, not a findings phase.
- Phase 11 can include topology-aware artifacts but must keep existing `geometry_helpers_dfm_results` for audit compatibility.
- Phase 19 remains the only phase that writes final findings.

## 11. Proposed Scripts

### scripts/part_info_extract.py

Inputs:

- `exports/{project}-bom.json`
- `exports/datasheets/datasheet_manifest.jsonl`
- Local PDF files under `exports/datasheets/`

Outputs:

- `exports/part_info/{normalized_mpn}.json`
- Extraction logs under `exports/part_info/` or `.agents_tmp/`

Responsibilities:

- Enumerate unique MPNs.
- Locate local datasheets.
- Extract relevant PDF text/tables/pages.
- Call AI with strict JSON prompt.
- Write raw and normalized extraction artifacts.
- Avoid final pass/fail claims.

### scripts/part_info_validate.py

Inputs:

- `exports/part_info/*.json`

Outputs:

- `exports/{project}-part-info-validation.json`

Responsibilities:

- Validate schema.
- Validate evidence references.
- Normalize units.
- Check numerical sanity.
- Mark low-confidence and unresolved records.
- Produce machine-readable validation details.

### scripts/part_info_index.py

Inputs:

- `exports/part_info/*.json`
- `exports/{project}-bom.json`

Outputs:

- `exports/part_info/part_info_index.json`

Responsibilities:

- Map normalized MPNs to part_info files.
- Map BOM refdes to normalized MPNs.
- Preserve manufacturer and alternate MPN data.
- Record missing, invalid, ambiguous, and human-review-needed entries.

### scripts/topology_builder.py

Inputs:

- `exports/{project}-thomson-export-sch.json`
- `exports/{project}-thomson-export-brd.json`
- `exports/{project}-thomson-export-stack.json`
- `exports/{project}-bom.json`
- `exports/part_info/part_info_index.json`

Outputs:

- `exports/{project}-power-topology.json`
- `exports/{project}-topology-map.json`

Responsibilities:

- Build schematic net graph.
- Classify nets and components.
- Propagate rails.
- Assign current models.
- Associate net-level copper geometry initially.
- Preserve unresolved items.

### scripts/topology_validate.py

Inputs:

- `exports/{project}-topology-map.json`

Outputs:

- `exports/{project}-topology-validation.json`

Responsibilities:

- Validate topology schema.
- Detect missing sources, sinks, currents, voltages, and part_info.
- Detect impossible values and circular propagation.
- Validate copper mapping completeness.
- Emit execution and consistency fields separately.

### scripts/topology_aware_geometry_checks.py

Inputs:

- `exports/{project}-topology-map.json`
- `exports/{project}-thomson-export-brd.json`
- `exports/{project}-thomson-export-stack.json`

Outputs:

- `exports/{project}-topology-aware-geometry-review.json`
- `exports/{project}-topology-aware-geometry-validation.json`

Responsibilities:

- Run topology-aware trace current checks.
- Run via current checks.
- Run plane/pour bottleneck checks.
- Run topology-resolved voltage clearance checks.
- Add DFM electrical criticality context.
- Preserve all outputs as evidence, not findings.

## 12. Testing Strategy

Test categories:

- `part_info` schema validation.
- Evidence-required numerical fields.
- MPN normalization.
- Source/sink/pass-through classification.
- Rail propagation.
- Current aggregation.
- Unresolved current handling.
- Topology map schema.
- Copper object mapping.
- Net-level current assignment.
- Branch-level current assignment.
- Topology-aware trace current checks.
- Regression fixtures using small synthetic boards.

Proposed tests:

- `tests/test_part_info_schema.py`
- `tests/test_part_info_extraction_validation.py`
- `tests/test_topology_builder_power_rails.py`
- `tests/test_topology_current_aggregation.py`
- `tests/test_topology_validation.py`
- `tests/test_topology_aware_geometry.py`

Fixture recommendations:

- Connector -> fuse -> regulator -> load.
- Regulator output -> ferrite -> analog sink.
- Multi-rail MCU sink.
- Power plane with multiple sinks.
- Unknown IC current draw.
- Missing part_info.
- Circular pass-through chain.
- Net with sinks and no source.
- High-current branch with narrow neck-down.
- Multiple vias in parallel.

Acceptance criteria:

- Invalid AI JSON is rejected before topology use.
- Numerical fields without evidence are flagged.
- Missing current never becomes zero current.
- Device max rating is not used as nominal load unless explicitly marked as a conservative bound.
- Power nets with sinks and no source are unresolved validation items.
- Current aggregation through pass-through devices is deterministic.
- Topology-aware geometry checks can run at Level 0 net-level precision before branch extraction exists.

## 13. Implementation Plan

### PR 1 - Architecture doc and schemas only

- Add `docs/TOPOLOGY_ANALYSIS_ARCHITECTURE.md`.
- Add `schemas/part_info_schema.json`.
- Add `schemas/topology_map_schema.json`.
- No workflow integration.
- No AI calls.
- No topology scripts.

### PR 2 - Part info validator

- Implement `scripts/part_info_validate.py`.
- Validate existing/manual `part_info` JSON.
- Emit `exports/{project}-part-info-validation.json`.
- Add schema and evidence-reference tests.
- No AI calls yet.

### PR 3 - Part info extraction prototype

- Implement `scripts/part_info_extract.py`.
- Extract text from local datasheet PDFs.
- Call AI for strict JSON.
- Validate before accepting output.
- Store one JSON per MPN.
- Mark missing or low-confidence fields unresolved.

### PR 4 - Part info index

- Implement `scripts/part_info_index.py`.
- Merge unique MPNs into `part_info_index.json`.
- Map BOM refdes to MPN and part_info file.
- Track missing, ambiguous, invalid, and human-review-needed records.

### PR 5 - Schematic net graph builder

- Start `scripts/topology_builder.py`.
- Build deterministic graph from schematic evidence.
- Reuse existing schematic parsing patterns.
- No board geometry required yet.
- Emit graph summary and basic devices/nets.

### PR 6 - Power topology v0

- Add source/sink/pass-through classification.
- Add net-level rail propagation.
- Add net-level current aggregation.
- Preserve unresolved current and voltage items.
- Emit `exports/{project}-power-topology.json` and `exports/{project}-topology-map.json`.

### PR 7 - Topology validation

- Implement `scripts/topology_validate.py`.
- Detect missing source, sink, current, voltage, part_info, impossible values, and circular propagation.
- Emit `exports/{project}-topology-validation.json`.

### PR 8 - Board copper net association

- Map topology nets to board tracks, vias, zones, and pads.
- Assign rail current at Level 0 net precision.
- Add mapping confidence.
- Add tests for unmapped copper and missing board nets.

### PR 9 - Branch topology v1

- Extract branch paths between sources and sinks.
- Account for pass-through components.
- Assign branch currents from downstream aggregation.
- Add branch-level copper links.

### PR 10 - Topology-aware thermal checks

- Implement `scripts/topology_aware_geometry_checks.py`.
- Run trace and via current checks from topology current models.
- Reuse existing Saturn and geometry helpers where possible.
- Emit topology-aware review and validation artifacts.

### PR 11 - Topology-aware DFM severity

- Add electrical criticality to DFM evidence.
- Improve severity context for high-current, high-voltage, switch-node, analog, connector, and thermal-pad copper.
- Keep final findings generation out of this script.

### PR 12 - Workflow phase integration

- Add optional topology sub-pipeline gates.
- Update prompts and audit integration only after artifacts are stable.
- Preserve current workflow behavior when topology artifacts are absent.
- Add compatibility checks to Phase 11 and Phase 17 only after topology validation is reliable.

## 14. Open Questions and Risks

- PDF extraction quality varies widely across datasheets.
- Current draw varies by operating mode, clock, firmware, temperature, load, and enabled peripherals.
- Datasheets often lack board-specific current draw.
- Regulator efficiency depends on load, input voltage, output voltage, switching frequency, and external components.
- Copper plane current spreading is approximate.
- Schematic symbol pin naming may not match datasheet pin names.
- Multiple equivalent MPNs and alternate manufacturers may have different ratings.
- Generic passives may have incomplete MPN data.
- Connector pin current depends on pin count, temperature rise, wire gauge, grouping, and derating.
- Ferrite rated current and impedance do not define actual rail load.
- Fuse hold/trip current does not define load current.
- Zero-ohm resistor current ratings may be absent or package-dependent.
- Load switches may have enable-state ambiguity.
- Isolated converters require careful ground-domain handling.
- AI extraction can create false confidence if validation is weak.
- Low-confidence `part_info` requires human review before strong topology conclusions.
- Board JSON may not expose enough geometry for branch-level path extraction in early milestones.
- Current sharing across parallel copper features is hard to prove deterministically.
- Existing phase gates distinguish execution from compliance; topology validation should follow the same pattern.

## 15. Immediate Next Steps

1. Create schemas.
2. Create manual `part_info` examples for 5 component classes.
3. Build validator.
4. Build topology v0 from schematic/BOM/part_info only.
5. Add topology validation artifact.
6. Only then connect geometry helpers.
