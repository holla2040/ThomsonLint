#!/usr/bin/env python3
"""Build a deterministic topology-map skeleton from schematic evidence.

PR 5 scope only:
- Parse schematic nets/components/pins.
- Optionally enrich devices from part_info_index.json.
- Emit a schema-valid topology map skeleton.
- Emit a compact power-topology summary.

The primary target input is the ThomsonLint converter's pads-v1 schematic
export: components/nets/nodes with analysis, extraction_counts, and bom_merge
metadata. Board and stackup paths may point to ipc2581-v1 converter exports but
are only recorded as sources in PR 5.

This script does not perform AI extraction, current aggregation, rail
propagation, copper geometry mapping, thermal checks, workflow integration, or
final findings generation.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = Path("schemas/topology_map_schema.json")

GROUND_NAMES = {"GND", "AGND", "DGND", "PGND", "SGND", "CHASSIS", "EARTH", "VSS"}
POWER_NAMES = {"VIN", "VOUT", "VBAT", "VBUS", "VSYS", "VCC", "VDD", "AVDD", "DVDD", "PVDD"}
POWER_PATTERNS = [
    re.compile(r"^[+-]?\d+(?:V\d*)?$", re.IGNORECASE),
    re.compile(r"^\d+V\d+$", re.IGNORECASE),
    re.compile(r"^V\d+P\d+$", re.IGNORECASE),
]

SOURCE_CATEGORIES = {
    "buck_regulator",
    "ldo_regulator",
    "boost_regulator",
    "buck_boost_regulator",
    "isolated_converter",
}
PASS_THROUGH_CATEGORIES = {
    "connector",
    "fuse",
    "ferrite_bead",
    "switch",
    "current_sense_resistor",
}
SINK_CATEGORIES = {"mcu", "fpga", "transceiver", "logic", "sensor"}
PASSIVE_CATEGORIES = {"resistor", "capacitor", "inductor", "passive"}


@dataclass(frozen=True)
class ParsedPin:
    refdes: str
    pin: str
    pin_name: str | None
    net_name: str | None

    @property
    def pin_ref(self) -> str:
        return f"{self.refdes}.{self.pin}"


@dataclass
class ParsedSchematic:
    components: dict[str, dict[str, Any]] = field(default_factory=dict)
    pins: list[ParsedPin] = field(default_factory=list)
    net_names: set[str] = field(default_factory=set)
    analysis: dict[str, Any] = field(default_factory=dict)
    extraction_counts: dict[str, Any] = field(default_factory=dict)
    bom_merge: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonschema() -> Any:
    try:
        import jsonschema  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "jsonschema is required for topology-map validation. Install it with "
            "`python3 -m pip install jsonschema` or add it to the project environment."
        ) from exc
    return jsonschema


def key_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def first_by_alias(data: dict[str, Any], aliases: set[str]) -> Any:
    for key, value in data.items():
        if key_name(key) in aliases and value not in (None, ""):
            return value
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def schematic_root(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("schematic"), dict):
        return data["schematic"]
    return data if isinstance(data, dict) else {}


def candidate_lists(root: dict[str, Any], key: str) -> list[Any]:
    value = root.get(key)
    return value if isinstance(value, list) else []


def extract_refdes(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"refdes", "reference", "designator", "component", "componentref", "componentid"})
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_pin_number(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"pin", "pinnumber", "number", "pinno", "pad", "padnumber"})
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_pin_name(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"pinname", "name", "signal", "pinlabel"})
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_net_name(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"net", "netname", "name", "id"})
    if isinstance(value, dict):
        value = first_by_alias(value, {"net", "netname", "name", "id"})
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_components(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    components: dict[str, dict[str, Any]] = {}
    for raw in candidate_lists(root, "components"):
        if not isinstance(raw, dict):
            continue
        refdes = extract_refdes(raw)
        if refdes:
            components[refdes] = raw
    return components


def parse_net_pin(raw: dict[str, Any], net_name: str | None) -> ParsedPin | None:
    refdes = extract_refdes(raw)
    pin = extract_pin_number(raw)
    if not refdes or not pin:
        return None
    pin_name = extract_pin_name(raw)
    node_net = extract_net_name(raw) or net_name
    return ParsedPin(refdes=refdes, pin=pin, pin_name=pin_name, net_name=node_net)


def parse_schematic(data: Any) -> ParsedSchematic:
    root = schematic_root(data)
    parsed = ParsedSchematic(
        components=parse_components(root),
        analysis=as_dict(root.get("analysis")),
        extraction_counts=as_dict(root.get("extraction_counts")),
        bom_merge=as_dict(root.get("bom_merge")),
        warnings=[str(item) for item in root.get("warnings", []) if item is not None]
        if isinstance(root.get("warnings"), list)
        else [],
    )
    seen_pins: set[tuple[str, str, str | None]] = set()

    for raw_net in candidate_lists(root, "nets"):
        if not isinstance(raw_net, dict):
            continue
        net_name = extract_net_name(raw_net)
        if net_name:
            parsed.net_names.add(net_name)
        for child_key in ("nodes", "pins", "connections"):
            raw_pins = raw_net.get(child_key, []) if isinstance(raw_net.get(child_key), list) else []
            if child_key == "nodes" and "node_count" in raw_net:
                try:
                    expected_count = int(raw_net.get("node_count"))
                except (TypeError, ValueError):
                    expected_count = None
                if expected_count is not None and expected_count != len(raw_pins):
                    parsed.warnings.append(
                        f"schematic net {net_name or '<unnamed>'} node_count={expected_count} "
                        f"does not match nodes length={len(raw_pins)}"
                    )
            for raw_pin in raw_pins:
                if not isinstance(raw_pin, dict):
                    continue
                pin = parse_net_pin(raw_pin, net_name)
                if pin is None:
                    continue
                key = (pin.refdes, pin.pin, pin.net_name)
                if key not in seen_pins:
                    seen_pins.add(key)
                    parsed.pins.append(pin)
                if pin.net_name:
                    parsed.net_names.add(pin.net_name)

    for raw_pin in candidate_lists(root, "pins"):
        if not isinstance(raw_pin, dict):
            continue
        pin = parse_net_pin(raw_pin, None)
        if pin is None:
            continue
        key = (pin.refdes, pin.pin, pin.net_name)
        if key not in seen_pins:
            seen_pins.add(key)
            parsed.pins.append(pin)
        if pin.net_name:
            parsed.net_names.add(pin.net_name)

    for pin in parsed.pins:
        parsed.components.setdefault(pin.refdes, {"refdes": pin.refdes})
    return parsed


def analysis_set(analysis: dict[str, Any], key: str) -> set[str]:
    value = analysis.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item).upper() for item in value if item not in (None, "")}


def classify_net(net_name: str | None, analysis: dict[str, Any] | None = None) -> tuple[str, float, list[str]]:
    if not net_name:
        return "unknown", 0.2, ["missing_net_name"]
    upper = net_name.upper()
    analysis = analysis or {}
    if upper in analysis_set(analysis, "ground_nets"):
        return "ground", 0.95, []
    if upper in analysis_set(analysis, "power_nets"):
        return "power", 0.95, []
    if upper in analysis_set(analysis, "clock_nets"):
        return "signal", 0.85, ["clock_net"]
    if upper in {"CHASSIS"}:
        return "chassis", 0.8, []
    if upper in {"EARTH"}:
        return "earth", 0.8, []
    if upper in GROUND_NAMES:
        return "ground", 0.8, []
    if upper in POWER_NAMES or any(pattern.match(upper) for pattern in POWER_PATTERNS):
        return "power", 0.8, []
    return "signal", 0.6, []


def pin_role_for_net(net_type: str) -> str:
    if net_type == "ground":
        return "ground"
    if net_type == "power":
        return "power"
    if net_type in {"chassis", "earth"}:
        return net_type
    if net_type == "signal":
        return "signal"
    return "unknown"


def load_part_info_index(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, [f"part_info_index missing: {path}"]
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"part_info_index must be a JSON object: {path}")
    return data, []


def component_mpn(component: dict[str, Any]) -> str | None:
    for source in [component, as_dict(component.get("bom")), as_dict(component.get("fields"))]:
        value = first_by_alias(source, {"mpn", "partnumber", "manufacturerpartnumber", "manufacturerpart"})
        if value is not None:
            return str(value).strip()
    return None


def component_manufacturer(component: dict[str, Any]) -> str | None:
    for source in [component, as_dict(component.get("bom")), as_dict(component.get("fields"))]:
        value = first_by_alias(source, {"manufacturer", "mfr", "vendor"})
        if value is not None:
            return str(value).strip()
    return None


def component_is_dnp(component: dict[str, Any]) -> bool:
    value = first_by_alias(component, {"dnp", "donotpopulate", "nopopulate"})
    if value is None:
        value = first_by_alias(as_dict(component.get("bom")), {"dnp", "donotpopulate", "nopopulate"})
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "dnp", "no_pop", "nopop", "do not populate"}


def normalize_mpn(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def first_file_record(mpn_entry: dict[str, Any]) -> dict[str, Any] | None:
    files = mpn_entry.get("files")
    if isinstance(files, list) and files and isinstance(files[0], dict):
        return files[0]
    return None


def part_info_for_refdes(refdes: str, component: dict[str, Any], index: dict[str, Any] | None) -> tuple[dict[str, Any] | None, list[str]]:
    if not index:
        return None, ["missing_part_info"]

    refdes_map = index.get("refdes")
    if isinstance(refdes_map, dict):
        row = refdes_map.get(refdes)
        if isinstance(row, dict):
            return row, []

    mpn = component_mpn(component)
    normalized = normalize_mpn(mpn)
    mpns = index.get("mpns")
    if normalized and isinstance(mpns, dict):
        mpn_entry = mpns.get(normalized)
        if isinstance(mpn_entry, dict) and not mpn_entry.get("ambiguous"):
            file_record = first_file_record(mpn_entry)
            if file_record:
                manufacturer = file_record.get("manufacturer") or component_manufacturer(component)
                return {
                    "refdes": refdes,
                    "mpn": file_record.get("mpn"),
                    "manufacturer": manufacturer,
                    "normalized_mpn": normalized,
                    "part_info_file": file_record.get("file"),
                    "component_category": file_record.get("component_category"),
                    "confidence_overall": file_record.get("confidence_overall"),
                    "human_review_needed": file_record.get("validation_human_review_needed", False),
                }, []
            return None, ["missing_part_info"]
        if isinstance(mpn_entry, dict) and mpn_entry.get("ambiguous"):
            return None, ["ambiguous_part_info"]
    return None, ["missing_part_info"]


def role_from_category(category: str | None) -> str:
    if category in SOURCE_CATEGORIES:
        return "source"
    if category in PASS_THROUGH_CATEGORIES:
        return "pass_through"
    if category in SINK_CATEGORIES:
        return "sink"
    if category in PASSIVE_CATEGORIES:
        return "passive"
    return "unknown"


def device_nets(refdes: str, pins: list[ParsedPin], net_type_by_name: dict[str, str]) -> dict[str, list[str]]:
    groups = {"input_nets": [], "output_nets": [], "supply_nets": [], "ground_nets": [], "signal_nets": []}
    for pin in pins:
        if pin.refdes != refdes or not pin.net_name:
            continue
        net_type = net_type_by_name.get(pin.net_name, "unknown")
        if net_type in {"ground", "chassis", "earth"}:
            key = "ground_nets"
        elif net_type == "power":
            key = "supply_nets"
        elif net_type == "signal":
            key = "signal_nets"
        else:
            key = "signal_nets"
        if pin.net_name not in groups[key]:
            groups[key].append(pin.net_name)
    return groups


def unresolved_item(
    *,
    item_id: str,
    item_type: str,
    net: str | None,
    refdes: list[str],
    part_info_ref: str | None,
    required_for: list[str],
    notes: str,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "net": net,
        "affected_refdes": refdes,
        "part_info_ref": part_info_ref,
        "required_for": required_for,
        "human_review_needed": True,
        "notes": notes,
    }


def build_topology(
    *,
    project: str,
    schematic_path: Path,
    board_path: Path,
    stackup_path: Path,
    bom_path: Path,
    part_info_index_path: Path,
    datasheet_manifest_path: Path,
    schematic_data: Any,
    part_info_index: dict[str, Any] | None,
    warnings: list[str],
) -> dict[str, Any]:
    parsed = parse_schematic(schematic_data)
    unresolved: list[dict[str, Any]] = []

    pins_by_net: dict[str, list[str]] = {}
    for pin in parsed.pins:
        if pin.net_name:
            pins_by_net.setdefault(pin.net_name, []).append(pin.pin_ref)

    net_type_by_name: dict[str, str] = {}
    nets: list[dict[str, Any]] = []
    for net_name in sorted(parsed.net_names):
        net_type, confidence, flags = classify_net(net_name, parsed.analysis)
        net_type_by_name[net_name] = net_type
        nets.append({
            "net_name": net_name,
            "net_type": net_type,
            "pin_refs": sorted(set(pins_by_net.get(net_name, []))),
            "nominal_voltage_v": None,
            "voltage_model_ref": None,
            "confidence": confidence,
            "unresolved_flags": flags,
        })

    devices: list[dict[str, Any]] = []
    pin_records: list[dict[str, Any]] = []
    part_info_by_refdes: dict[str, dict[str, Any] | None] = {}

    for refdes in sorted(parsed.components):
        component = parsed.components[refdes]
        part_info, flags = part_info_for_refdes(refdes, component, part_info_index)
        part_info_by_refdes[refdes] = part_info
        category = part_info.get("component_category") if isinstance(part_info, dict) else None
        part_info_ref = part_info.get("part_info_file") if isinstance(part_info, dict) else None
        confidence = part_info.get("confidence_overall") if isinstance(part_info, dict) else None
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.3
        unresolved_flags = list(flags)
        if component_is_dnp(component):
            unresolved_flags.append("dnp_component")
            warnings.append(f"{refdes} is marked DNP in schematic BOM metadata")
        if "missing_part_info" in unresolved_flags:
            unresolved.append(unresolved_item(
                item_id=f"unres_{refdes}_part_info",
                item_type="missing_part_info",
                net=None,
                refdes=[refdes],
                part_info_ref=None,
                required_for=["device_classification", "pin_role_mapping"],
                notes="No part_info_index entry matched this schematic component.",
            ))
        elif "ambiguous_part_info" in unresolved_flags:
            unresolved.append(unresolved_item(
                item_id=f"unres_{refdes}_ambiguous_part_info",
                item_type="missing_part_info",
                net=None,
                refdes=[refdes],
                part_info_ref=None,
                required_for=["device_classification", "pin_role_mapping"],
                notes="part_info_index entry was ambiguous; topology builder did not guess.",
            ))

        net_groups = device_nets(refdes, parsed.pins, net_type_by_name)
        devices.append({
            "refdes": refdes,
            "mpn": (part_info.get("mpn") or component_mpn(component)) if isinstance(part_info, dict) else component_mpn(component),
            "manufacturer": (part_info.get("manufacturer") or component_manufacturer(component))
            if isinstance(part_info, dict)
            else component_manufacturer(component),
            "device_role": role_from_category(category if isinstance(category, str) else None),
            "input_nets": net_groups["input_nets"],
            "output_nets": net_groups["output_nets"],
            "supply_nets": net_groups["supply_nets"],
            "ground_nets": net_groups["ground_nets"],
            "signal_nets": net_groups["signal_nets"],
            "part_info_ref": part_info_ref if isinstance(part_info_ref, str) else None,
            "current_model": None,
            "confidence": confidence_value,
            "unresolved": unresolved_flags,
        })

    for pin in parsed.pins:
        net_type = net_type_by_name.get(pin.net_name or "", classify_net(pin.net_name, parsed.analysis)[0])
        part_info = part_info_by_refdes.get(pin.refdes)
        flags = []
        if not part_info:
            flags.append("missing_part_info")
        flags.append("pin_mapping_conflict")
        if "pin_mapping_conflict" in flags:
            unresolved.append(unresolved_item(
                item_id=f"unres_{pin.refdes}_{pin.pin}_pin_mapping",
                item_type="pin_mapping_conflict",
                net=pin.net_name,
                refdes=[pin.refdes],
                part_info_ref=part_info.get("part_info_file") if isinstance(part_info, dict) else None,
                required_for=["pin_role_mapping"],
                notes="PR 5 does not match schematic pins to datasheet pin roles.",
            ))
        pin_records.append({
            "pin_ref": pin.pin_ref,
            "refdes": pin.refdes,
            "pin": pin.pin,
            "pin_name": pin.pin_name,
            "net_name": pin.net_name,
            "role": pin_role_for_net(net_type),
            "confidence": 0.4 if flags else 0.6,
            "part_info_pin_ref": None,
            "unresolved_flags": flags,
        })

    if not parsed.net_names:
        unresolved.append(unresolved_item(
            item_id="unres_no_nets_extracted",
            item_type="other",
            net=None,
            refdes=[],
            part_info_ref=None,
            required_for=["schematic_net_graph"],
            notes="No nets were extracted from schematic JSON.",
        ))
    if not parsed.pins:
        unresolved.append(unresolved_item(
            item_id="unres_no_pins_extracted",
            item_type="other",
            net=None,
            refdes=[],
            part_info_ref=None,
            required_for=["schematic_net_graph"],
            notes="No pin-to-net relationships were extracted from schematic JSON.",
        ))

    # Deduplicate unresolved records by id.
    unresolved_by_id = {item["id"]: item for item in unresolved}
    unresolved = list(unresolved_by_id.values())

    validation_warnings = list(warnings)
    validation_warnings.extend(parsed.warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "schematic": str(schematic_path),
            "board": str(board_path),
            "stackup": str(stackup_path),
            "bom": str(bom_path),
            "part_info_index": str(part_info_index_path),
            "datasheet_manifest": str(datasheet_manifest_path),
        },
        "assumptions": [],
        "graph_summary": {
            "net_count": len(nets),
            "device_count": len(devices),
            "power_rail_count": 0,
            "branch_count": 0,
            "unresolved_count": len(unresolved),
        },
        "nets": nets,
        "power_rails": [],
        "devices": devices,
        "pins": pin_records,
        "pass_through_edges": [],
        "source_nodes": [],
        "sink_nodes": [],
        "branches": [],
        "copper_geometry_links": [],
        "current_models": [],
        "voltage_models": [],
        "unresolved": unresolved,
        "validation": {
            "execution_pass": True,
            "artifact_validation_pass": False,
            "topology_consistency_pass": not unresolved,
            "unresolved_items_present": bool(unresolved),
            "human_review_needed": bool(unresolved),
            "errors": [],
            "warnings": validation_warnings,
        },
    }


def build_power_summary(project: str, topology: dict[str, Any], warnings: list[str], errors: list[str]) -> dict[str, Any]:
    nets = topology.get("nets") if isinstance(topology.get("nets"), list) else []
    power_like = [net for net in nets if isinstance(net, dict) and net.get("net_type") == "power"]
    ground = [net for net in nets if isinstance(net, dict) and net.get("net_type") in {"ground", "chassis", "earth"}]
    pins = topology.get("pins") if isinstance(topology.get("pins"), list) else []
    devices = topology.get("devices") if isinstance(topology.get("devices"), list) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "summary": {
            "net_count": len(nets),
            "device_count": len(devices),
            "pin_count": len(pins),
            "power_like_net_count": len(power_like),
            "ground_net_count": len(ground),
        },
        "power_like_nets": [net.get("net_name") for net in power_like],
        "ground_nets": [net.get("net_name") for net in ground],
        "warnings": warnings,
        "errors": errors,
        "execution_pass": not errors,
    }


def validate_topology(schema_path: Path, topology: dict[str, Any]) -> list[str]:
    jsonschema = load_jsonschema()
    if not schema_path.exists():
        raise FileNotFoundError(f"missing topology schema: {schema_path}")
    schema = load_json(schema_path)
    if not isinstance(schema, dict):
        raise ValueError(f"topology schema must be a JSON object: {schema_path}")
    jsonschema.Draft7Validator.check_schema(schema)
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(topology), key=lambda err: list(err.path))
    return [f"{'.'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a ThomsonLint topology-map skeleton.")
    parser.add_argument("--project", default="example")
    parser.add_argument("--schematic", default=None)
    parser.add_argument("--board", default=None)
    parser.add_argument("--stackup", default=None)
    parser.add_argument("--bom", default=None)
    parser.add_argument("--part-info-index", default=None)
    parser.add_argument("--datasheet-manifest", default=None)
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--out", default=None)
    parser.add_argument("--power-out", default=None)
    parser.add_argument("--examples", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    schematic_path = Path(args.schematic or default_path("exports/{project}-thomson-export-sch.json", project))
    board_path = Path(args.board or default_path("exports/{project}-thomson-export-brd.json", project))
    stackup_path = Path(args.stackup or default_path("exports/{project}-thomson-export-stack.json", project))
    bom_path = Path(args.bom or default_path("exports/{project}-bom.json", project))
    part_info_index_path = Path(args.part_info_index or "exports/part_info/part_info_index.json")
    datasheet_manifest_path = Path(args.datasheet_manifest or "exports/datasheets/datasheet_manifest.jsonl")
    schema_path = Path(args.schema)
    out_path = Path(args.out or default_path("exports/{project}-topology-map.json", project))
    power_out_path = Path(args.power_out or default_path("exports/{project}-power-topology.json", project))

    warnings: list[str] = []
    errors: list[str] = []
    try:
        if not schematic_path.exists():
            if args.examples:
                warnings.append(f"schematic missing in examples mode: {schematic_path}")
                schematic_data: Any = {"components": [], "nets": []}
            else:
                raise FileNotFoundError(f"missing schematic JSON: {schematic_path}")
        else:
            schematic_data = load_json(schematic_path)

        for label, path in [
            ("board", board_path),
            ("stackup", stackup_path),
            ("bom", bom_path),
            ("datasheet_manifest", datasheet_manifest_path),
        ]:
            if not path.exists():
                warnings.append(f"{label} input missing: {path}")

        part_info_index, part_warnings = load_part_info_index(part_info_index_path)
        warnings.extend(part_warnings)

        if args.strict and warnings:
            errors.extend(warnings)

        topology = build_topology(
            project=project,
            schematic_path=schematic_path,
            board_path=board_path,
            stackup_path=stackup_path,
            bom_path=bom_path,
            part_info_index_path=part_info_index_path,
            datasheet_manifest_path=datasheet_manifest_path,
            schematic_data=schematic_data,
            part_info_index=part_info_index,
            warnings=warnings,
        )
        topology["validation"]["errors"].extend(errors)
        schema_errors = validate_topology(schema_path, topology)
        if schema_errors:
            topology["validation"]["errors"].extend(schema_errors)
            topology["validation"]["artifact_validation_pass"] = False
        else:
            topology["validation"]["artifact_validation_pass"] = not errors
        if errors:
            topology["validation"]["execution_pass"] = False
            topology["validation"]["topology_consistency_pass"] = False

        power_summary = build_power_summary(project, topology, warnings, topology["validation"]["errors"])
        write_json(out_path, topology)
        write_json(power_out_path, power_summary)
    except Exception as exc:
        errors.append(str(exc))
        power_summary = {
            "schema_version": SCHEMA_VERSION,
            "project": project,
            "generated_at_utc": utc_now(),
            "summary": {"net_count": 0, "device_count": 0, "pin_count": 0, "power_like_net_count": 0, "ground_net_count": 0},
            "power_like_nets": [],
            "ground_nets": [],
            "warnings": warnings,
            "errors": errors,
            "execution_pass": False,
        }
        try:
            write_json(power_out_path, power_summary)
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = topology["graph_summary"]
    print(
        "topology builder: "
        f"nets={summary['net_count']} devices={summary['device_count']} pins={len(topology['pins'])} "
        f"unresolved={summary['unresolved_count']} out={out_path} power_out={power_out_path}"
    )
    if topology["validation"]["errors"]:
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
