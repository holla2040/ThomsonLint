#!/usr/bin/env python3
"""Resolve deterministic topology roles from schematic and topology artifacts.

PR 12 scope only: classify component, net, pin, and simple role-edge evidence.
This script does not call AI, infer current, calculate ampacity/current density,
compute thermal rise or voltage drop, create findings, mutate topology maps, or
modify workflow state.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"

CONNECTOR_PREFIXES = {"J", "P", "CN", "CON", "TB"}
GROUND_NAMES = {"GND", "VSS", "AGND", "DGND", "PGND", "SGND", "CHASSIS", "EARTH"}
POWER_NAMES = {"VIN", "VOUT", "VBAT", "VBUS", "VSYS", "VCC", "VDD", "AVDD", "DVDD", "PVDD"}
SIGNAL_PIN_NAMES = {"SDA", "SCL", "MISO", "MOSI", "CLK", "TX", "RX", "GPIO"}
POWER_NET_PATTERNS = [
    re.compile(r"^[+-]?\d+(?:V\d*)?$", re.IGNORECASE),
    re.compile(r"^\d+V\d+$", re.IGNORECASE),
    re.compile(r"^V\d+P\d+$", re.IGNORECASE),
    re.compile(r"^VN\d+P\d+$", re.IGNORECASE),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def key_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def refdes_prefix(refdes: str) -> str:
    match = re.match(r"^[A-Za-z]+", refdes or "")
    return match.group(0).upper() if match else ""


def first_by_alias(data: dict[str, Any], aliases: set[str]) -> Any:
    alias_keys = {key_name(alias) for alias in aliases}
    for key, value in data.items():
        if key_name(key) in alias_keys and value not in (None, ""):
            return value
    return None


def first_from_sources(sources: list[dict[str, Any]], aliases: set[str]) -> Any:
    for source in sources:
        value = first_by_alias(source, aliases)
        if value not in (None, ""):
            return value
    return None


def schematic_root(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("schematic"), dict):
        return data["schematic"]
    return data if isinstance(data, dict) else {}


def evidence(item_type: str, field: str, value: Any, reason: str) -> dict[str, Any]:
    return {"type": item_type, "field": field, "value": value, "reason": reason}


def normalized_mpn(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def component_sources(component: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [component]
    for key in ("bom", "fields", "raw", "custom_metadata"):
        nested = component.get(key)
        if isinstance(nested, dict):
            sources.append(nested)
    return sources


def component_refdes(component: dict[str, Any]) -> str | None:
    value = first_from_sources(component_sources(component), {"refdes", "reference", "designator", "componentref"})
    return str(value).strip() if value not in (None, "") else None


def component_value(component: dict[str, Any]) -> str | None:
    value = first_from_sources(component_sources(component), {"value", "val", "resistance", "capacitance"})
    return str(value).strip() if value not in (None, "") else None


def component_mpn(component: dict[str, Any]) -> str | None:
    value = first_from_sources(component_sources(component), {"mpn", "partnumber", "manufacturerpartnumber", "manufacturerpart"})
    return str(value).strip() if value not in (None, "") else None


def component_description(component: dict[str, Any], part_info: dict[str, Any] | None = None) -> str:
    values: list[str] = []
    for source in component_sources(component) + ([part_info] if isinstance(part_info, dict) else []):
        for alias in ("description", "desc", "value", "footprint", "mpn", "part_number", "component_category", "category"):
            value = first_by_alias(source, {alias})
            if value not in (None, ""):
                values.append(str(value))
    return " ".join(values)


def component_footprint(component: dict[str, Any]) -> str | None:
    value = first_from_sources(component_sources(component), {"footprint", "package", "pattern"})
    return str(value).strip() if value not in (None, "") else None


def pin_number(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"pin", "pinnumber", "number", "pinno", "pad", "padnumber"})
    return str(value).strip() if value not in (None, "") else None


def pin_name(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"pinname", "name", "signal", "pinlabel"})
    return str(value).strip() if value not in (None, "") else None


def net_name(raw: dict[str, Any]) -> str | None:
    value = first_by_alias(raw, {"net", "netname", "name", "id"})
    if isinstance(value, dict):
        value = first_by_alias(value, {"net", "netname", "name", "id"})
    return str(value).strip() if value not in (None, "") else None


def parse_schematic(data: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], set[str], dict[str, Any]]:
    root = schematic_root(data)
    components: dict[str, dict[str, Any]] = {}
    pins: list[dict[str, Any]] = []
    nets: set[str] = set()
    seen_pins: set[tuple[str, str, str | None]] = set()

    for raw in root.get("components", []) if isinstance(root.get("components"), list) else []:
        if not isinstance(raw, dict):
            continue
        refdes = component_refdes(raw)
        if refdes:
            components[refdes] = raw

    def add_pin(raw_pin: dict[str, Any], fallback_net: str | None = None) -> None:
        refdes = component_refdes(raw_pin)
        number = pin_number(raw_pin)
        if not refdes or not number:
            return
        pin_net = net_name(raw_pin) or fallback_net
        key = (refdes, number, pin_net)
        if key in seen_pins:
            return
        seen_pins.add(key)
        pins.append({
            "refdes": refdes,
            "pin_number": number,
            "pin_name": pin_name(raw_pin),
            "net_name": pin_net,
        })
        components.setdefault(refdes, {"refdes": refdes})
        if pin_net:
            nets.add(pin_net)

    for raw_net in root.get("nets", []) if isinstance(root.get("nets"), list) else []:
        if not isinstance(raw_net, dict):
            continue
        current_net = net_name(raw_net)
        if current_net:
            nets.add(current_net)
        for child_key in ("nodes", "pins", "connections"):
            child_rows = raw_net.get(child_key) if isinstance(raw_net.get(child_key), list) else []
            for raw_pin in child_rows:
                if isinstance(raw_pin, dict):
                    add_pin(raw_pin, current_net)

    for raw_pin in root.get("pins", []) if isinstance(root.get("pins"), list) else []:
        if isinstance(raw_pin, dict):
            add_pin(raw_pin)

    return components, pins, nets, as_dict(root.get("analysis"))


def parse_topology(data: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], set[str], dict[str, str], set[str]]:
    topology = data if isinstance(data, dict) else {}
    components: dict[str, dict[str, Any]] = {}
    pins: list[dict[str, Any]] = []
    nets: set[str] = set()
    net_types: dict[str, str] = {}
    power_rails: set[str] = set()

    for device in topology.get("devices", []) if isinstance(topology.get("devices"), list) else []:
        if isinstance(device, dict) and isinstance(device.get("refdes"), str):
            components[device["refdes"]] = device

    for net in topology.get("nets", []) if isinstance(topology.get("nets"), list) else []:
        if not isinstance(net, dict):
            continue
        name = net.get("net_name") or net.get("name")
        if isinstance(name, str):
            nets.add(name)
            net_type = net.get("net_type") or net.get("role")
            if isinstance(net_type, str):
                net_types[name] = net_type

    for rail in topology.get("power_rails", []) if isinstance(topology.get("power_rails"), list) else []:
        if isinstance(rail, dict) and isinstance(rail.get("net_name"), str):
            power_rails.add(rail["net_name"])

    for pin in topology.get("pins", []) if isinstance(topology.get("pins"), list) else []:
        if not isinstance(pin, dict):
            continue
        refdes = pin.get("refdes")
        number = pin.get("pin") or pin.get("pin_number")
        if isinstance(refdes, str) and number not in (None, ""):
            net = pin.get("net_name")
            pins.append({
                "refdes": refdes,
                "pin_number": str(number),
                "pin_name": pin.get("pin_name"),
                "net_name": net if isinstance(net, str) else None,
            })
            if isinstance(net, str):
                nets.add(net)
    return components, pins, nets, net_types, power_rails


def merge_inputs(topology: Any, schematic: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], set[str], dict[str, Any], dict[str, str], set[str]]:
    sch_components, sch_pins, sch_nets, analysis = parse_schematic(schematic)
    topo_components, topo_pins, topo_nets, topo_net_types, power_rails = parse_topology(topology)
    components = dict(topo_components)
    components.update(sch_components)

    pins: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for pin in sch_pins + topo_pins:
        key = (pin.get("refdes"), pin.get("pin_number"), pin.get("net_name"))
        if key not in seen:
            seen.add(key)
            pins.append(pin)
    return components, pins, sch_nets | topo_nets, analysis, topo_net_types, power_rails


def load_part_info_index(path: Path | None) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None or not path.exists():
        return None, [f"part_info_index missing: {path}"] if path is not None else []
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"part_info_index must be a JSON object: {path}")
    return data, []


def first_file_record(mpn_entry: dict[str, Any]) -> dict[str, Any] | None:
    files = mpn_entry.get("files")
    if isinstance(files, list) and files and isinstance(files[0], dict):
        return files[0]
    return None


def part_info_for_component(refdes: str, component: dict[str, Any], index: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(index, dict):
        return None
    refdes_map = index.get("refdes")
    if isinstance(refdes_map, dict) and isinstance(refdes_map.get(refdes), dict):
        return refdes_map[refdes]

    mpn = component_mpn(component)
    normalized = normalized_mpn(mpn)
    mpns = index.get("mpns")
    if normalized and isinstance(mpns, dict):
        entry = mpns.get(normalized)
        if isinstance(entry, dict) and not entry.get("ambiguous"):
            file_record = first_file_record(entry)
            if isinstance(file_record, dict):
                return {
                    "refdes": refdes,
                    "mpn": file_record.get("mpn"),
                    "manufacturer": file_record.get("manufacturer"),
                    "normalized_mpn": normalized,
                    "part_info_file": file_record.get("file"),
                    "component_category": file_record.get("component_category"),
                    "confidence_overall": file_record.get("confidence_overall"),
                }
    return None


def analysis_names(analysis: dict[str, Any], key: str) -> set[str]:
    value = analysis.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item).upper() for item in value if item not in (None, "")}


def parse_voltage_from_net_name(name: str | None) -> float | None:
    if not name:
        return None
    text = name.strip().upper()
    sign = 1.0
    if text.startswith("+"):
        text = text[1:]
    elif text.startswith("-"):
        sign = -1.0
        text = text[1:]
    elif re.fullmatch(r"VN\d+P\d+", text):
        sign = -1.0
        text = "V" + text[2:]
    match = re.fullmatch(r"V(\d+)P(\d+)", text)
    if match:
        return sign * float(f"{int(match.group(1))}.{match.group(2)}")
    match = re.fullmatch(r"(\d+)V(\d+)", text)
    if match:
        return sign * float(f"{int(match.group(1))}.{match.group(2)}")
    match = re.fullmatch(r"(\d+)V", text)
    if match:
        return sign * float(match.group(1))
    return None


def classify_net_role(name: str, analysis: dict[str, Any], topology_net_types: dict[str, str], power_rails: set[str]) -> dict[str, Any]:
    upper = name.upper()
    ev: list[dict[str, Any]] = []
    role = "signal"
    confidence = 0.55
    if name in power_rails:
        role, confidence = "power", 0.95
        ev.append(evidence("topology", "power_rails", name, "net is present in topology power_rails"))
    elif upper in analysis_names(analysis, "power_nets"):
        role, confidence = "power", 0.95
        ev.append(evidence("schematic_connection", "analysis.power_nets", name, "schematic analysis classifies net as power"))
    elif upper in analysis_names(analysis, "ground_nets"):
        role, confidence = "ground", 0.95
        ev.append(evidence("schematic_connection", "analysis.ground_nets", name, "schematic analysis classifies net as ground"))
    elif upper in analysis_names(analysis, "clock_nets"):
        role, confidence = "clock", 0.9
        ev.append(evidence("schematic_connection", "analysis.clock_nets", name, "schematic analysis classifies net as clock"))
    elif topology_net_types.get(name) in {"power", "ground", "signal", "clock"}:
        role = topology_net_types[name]
        confidence = 0.85
        ev.append(evidence("topology", "topology.nets.net_type", role, "topology net_type supplies net role"))
    elif upper in GROUND_NAMES:
        role, confidence = "ground", 0.8
        ev.append(evidence("net_name", "net_name", name, "net name matches ground token"))
    elif upper in POWER_NAMES or any(pattern.match(upper) for pattern in POWER_NET_PATTERNS):
        role, confidence = "power", 0.8
        ev.append(evidence("net_name", "net_name", name, "net name matches power token or voltage pattern"))

    return {
        "net_name": name,
        "role": role,
        "voltage": parse_voltage_from_net_name(name) if role == "power" else None,
        "confidence": confidence,
        "evidence": ev,
        "connected_sources": [],
        "connected_sinks": [],
        "connected_pass_through": [],
        "unresolved": [],
    }


def pins_for_refdes(pins: list[dict[str, Any]], refdes: str) -> list[dict[str, Any]]:
    return [pin for pin in pins if pin.get("refdes") == refdes]


def pin_role(pin_name_value: Any, component_role: str = "unknown") -> tuple[str, float, list[dict[str, Any]]]:
    raw = str(pin_name_value or "").strip()
    upper = raw.upper()
    compact = key_name(raw).upper()
    if upper in {"GND", "VSS", "AGND", "PGND", "DGND"}:
        return "ground", 0.95, [evidence("pin_name", "pin_name", raw, "pin name is a ground token")]
    if upper in {"VIN", "IN", "VBUS", "VSYS", "VCC_IN", "PVIN", "AVIN"}:
        return "power_in", 0.9, [evidence("pin_name", "pin_name", raw, "pin name is an input power token")]
    if upper in {"VOUT", "OUT", "SW_OUT"}:
        return "power_out", 0.9, [evidence("pin_name", "pin_name", raw, "pin name is an output power token")]
    if upper in {"VDD", "VCC", "AVDD", "DVDD", "PVDD"}:
        confidence = 0.85 if component_role == "sink" else 0.65
        return "power_in", confidence, [evidence("pin_name", "pin_name", raw, "pin name is an IC supply token")]
    if upper in {"EN", "ENABLE"}:
        return "enable", 0.9, [evidence("pin_name", "pin_name", raw, "pin name is enable")]
    if upper in {"FB", "VFB"}:
        return "feedback", 0.9, [evidence("pin_name", "pin_name", raw, "pin name is feedback")]
    if upper in {"SW", "LX", "PHASE", "PH"}:
        return "switch_node", 0.9, [evidence("pin_name", "pin_name", raw, "pin name is switch-node")]
    if upper in SIGNAL_PIN_NAMES or compact.startswith("GPIO"):
        return "signal", 0.85, [evidence("pin_name", "pin_name", raw, "pin name is a signal token")]
    return "unknown", 0.25, []


def text_contains(text: str, tokens: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for token in tokens:
        if token in lowered:
            return token
    return None


def looks_zero_ohm(value: str | None, text: str) -> bool:
    compact = re.sub(r"[\s_\-]+", "", f"{value or ''} {text}".lower().replace("ω", "ohm"))
    return any(token in compact for token in ("0r", "0r0", "0r00", "0ohm", "zeroohm", "jumper", "link"))


def looks_current_sense(value: str | None, text: str) -> bool:
    lowered = f"{value or ''} {text}".lower().replace("ω", "ohm")
    if "shunt" in lowered or "current sense" in lowered:
        return True
    return bool(re.search(r"\b0\.(?:00)?[0-9]+\s*(?:r|ohm)", lowered))


def connected_net_groups(component_pins: list[dict[str, Any]], net_role_by_name: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    groups = {"connected_nets": [], "power_nets": [], "ground_nets": [], "signal_nets": []}
    for pin in component_pins:
        name = pin.get("net_name")
        if not isinstance(name, str):
            continue
        if name not in groups["connected_nets"]:
            groups["connected_nets"].append(name)
        role = net_role_by_name.get(name, {}).get("role", "unknown")
        key = "signal_nets"
        if role == "power":
            key = "power_nets"
        elif role == "ground":
            key = "ground_nets"
        if name not in groups[key]:
            groups[key].append(name)
    for key in groups:
        groups[key] = sorted(groups[key])
    return groups


def subtype_for_regulator(text: str, category: str | None) -> str:
    lowered = text.lower()
    category = (category or "").lower()
    if "buck" in lowered or "buck" in category:
        return "buck_regulator"
    if "boost" in lowered or "boost" in category:
        return "boost_regulator"
    if "ldo" in lowered or "ldo" in category:
        return "ldo"
    if "power module" in lowered or "module" in category:
        return "power_module"
    return "regulator"


def unresolved_record(category: str, target_type: str, target_id: str, notes: str, blocks: list[str], recommended: str, rules: list[str]) -> dict[str, Any]:
    return {
        "id": f"unres_role_{safe_id(target_type)}_{safe_id(target_id)}_{safe_id(category)}",
        "category": category,
        "target_type": target_type,
        "target_id": target_id,
        "notes": notes,
        "blocks": blocks,
        "recommended_resolution": recommended,
        "candidate_rule_ids": rules,
    }


def classify_component(refdes: str, component: dict[str, Any], part_info: dict[str, Any] | None, component_pins: list[dict[str, Any]], net_role_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prefix = refdes_prefix(refdes)
    value = component_value(component)
    mpn = component_mpn(component) or (part_info.get("mpn") if isinstance(part_info, dict) else None)
    footprint = component_footprint(component)
    text = component_description(component, part_info)
    lowered = text.lower()
    category = part_info.get("component_category") if isinstance(part_info, dict) else None
    category_text = str(category or "").lower()
    groups = connected_net_groups(component_pins, net_role_by_name)
    pin_roles = [pin_role(pin.get("pin_name"))[0] for pin in component_pins]
    ev: list[dict[str, Any]] = []
    unresolved: list[str] = []
    role = "unknown"
    subtype = "unknown"
    confidence = 0.25

    def add_prefix(reason: str) -> None:
        ev.append(evidence("refdes_prefix", "refdes", prefix, reason))

    keyword = text_contains(lowered, ("battery", "coin cell", "lithium"))
    if prefix == "BT" or keyword:
        role, subtype, confidence = "source", "battery", 0.95
        add_prefix("battery refdes prefix") if prefix == "BT" else ev.append(evidence("description_keyword", "description", keyword, "description/value contains battery keyword"))
    elif text_contains(f"{lowered} {category_text}", ("load switch", "power switch", "ideal diode", "oring", "efuse", "hot swap")):
        role, subtype, confidence = "source", "power_switch", 0.86
        ev.append(evidence("description_keyword", "description", text_contains(lowered, ("load switch", "power switch", "ideal diode", "oring", "efuse", "hot swap")), "description/value contains power-path keyword"))
    elif (
        text_contains(f"{lowered} {category_text}", ("regulator", "ldo", "buck", "boost", "converter", "dc-dc", "dcdc", "switching regulator", "power module"))
        or {"power_out", "feedback", "enable", "switch_node"}.intersection(pin_roles) and prefix in {"U", "IC"}
    ):
        role, subtype, confidence = "source", subtype_for_regulator(lowered, category if isinstance(category, str) else None), 0.88
        ev.append(evidence("description_keyword", "description", category or text, "component text or part_info indicates regulator/converter"))
        if "power_out" not in pin_roles:
            unresolved.append("regulator_input_output_unknown")
    elif prefix in CONNECTOR_PREFIXES:
        add_prefix("connector refdes prefix")
        if groups["power_nets"]:
            role, subtype, confidence = "source", "connector_power_input_or_io", 0.72
            unresolved.append("connector_direction_unknown")
        else:
            role, subtype, confidence = "bidirectional_or_interface", "interface", 0.75
    elif prefix == "FB" or text_contains(lowered, ("ferrite bead", "ferrite", "bead")):
        role, subtype, confidence = "pass_through", "ferrite_bead", 0.9
        add_prefix("ferrite bead refdes prefix") if prefix == "FB" else ev.append(evidence("description_keyword", "description", "ferrite", "description/value contains ferrite keyword"))
    elif prefix in {"F", "PF"} or text_contains(lowered, ("polyfuse", "resettable fuse", "fuse", "ptc")):
        role, subtype, confidence = "pass_through", "fuse", 0.9
        add_prefix("fuse refdes prefix") if prefix in {"F", "PF"} else ev.append(evidence("description_keyword", "description", "fuse", "description/value contains fuse keyword"))
    elif looks_current_sense(value, lowered):
        role, subtype, confidence = "pass_through", "current_sense", 0.78
        ev.append(evidence("value_keyword", "value", value, "value/description indicates current sense or shunt"))
    elif prefix in {"R", "JP"} and looks_zero_ohm(value, lowered):
        role, subtype, confidence = "pass_through", "zero_ohm_link" if prefix == "R" else "jumper", 0.82
        ev.append(evidence("value_keyword", "value", value, "value/description indicates zero-ohm link or jumper"))
    elif prefix in {"L", "CM", "CMC"} or text_contains(lowered, ("choke", "common mode")):
        role, subtype, confidence = "pass_through", "inductor_or_choke_pass_through", 0.62
        add_prefix("series magnetic refdes prefix")
    elif prefix == "C" and groups["power_nets"] and groups["ground_nets"]:
        role, subtype, confidence = "sink", "passive_decoupling", 0.65
        add_prefix("capacitor refdes prefix")
        unresolved.append("not a load current model")
    elif (prefix in {"U", "IC"} or category_text in {"mcu", "fpga", "transceiver", "logic", "sensor"}) and groups["power_nets"] and groups["ground_nets"]:
        role, subtype, confidence = "sink", "ic_load", 0.84
        add_prefix("IC refdes prefix") if prefix in {"U", "IC"} else ev.append(evidence("part_info", "component_category", category, "part_info category is an IC-like load"))
    elif prefix in {"D", "LED"} and ("led" in lowered or prefix == "LED"):
        role, subtype, confidence = "sink", "led_load", 0.78
        add_prefix("LED/diode refdes prefix")
    elif text_contains(lowered, ("motor", "solenoid", "relay", "heater", "actuator", "fan")):
        role, subtype, confidence = "sink", "load", 0.78
        ev.append(evidence("description_keyword", "description", text, "description/value contains load keyword"))

    return {
        "refdes": refdes,
        "mpn": mpn,
        "value": value,
        "description": component_description(component, part_info),
        "footprint": footprint,
        "role": role,
        "role_subtype": subtype,
        "confidence": confidence,
        "evidence": ev,
        "connected_nets": groups["connected_nets"],
        "power_nets": groups["power_nets"],
        "ground_nets": groups["ground_nets"],
        "input_nets": [],
        "output_nets": [],
        "pass_through_nets": groups["connected_nets"] if role == "pass_through" else [],
        "unresolved": unresolved,
    }


def build_pin_roles(pins: list[dict[str, Any]], component_roles: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pin in sorted(pins, key=lambda row: (str(row.get("refdes") or ""), str(row.get("pin_number") or ""), str(row.get("net_name") or ""))):
        refdes = str(pin.get("refdes") or "")
        role, confidence, ev = pin_role(pin.get("pin_name"), component_roles.get(refdes, {}).get("role", "unknown"))
        rows.append({
            "refdes": refdes,
            "pin_number": pin.get("pin_number"),
            "pin_name": pin.get("pin_name"),
            "net_name": pin.get("net_name"),
            "pin_role": role,
            "confidence": confidence,
            "evidence": ev,
        })
    return rows


def assign_component_io(component_roles: dict[str, dict[str, Any]], pin_roles: list[dict[str, Any]]) -> None:
    by_refdes: dict[str, list[dict[str, Any]]] = {}
    for pin in pin_roles:
        by_refdes.setdefault(str(pin.get("refdes")), []).append(pin)
    for refdes, role in component_roles.items():
        input_nets = sorted({pin.get("net_name") for pin in by_refdes.get(refdes, []) if pin.get("pin_role") == "power_in" and isinstance(pin.get("net_name"), str)})
        output_nets = sorted({pin.get("net_name") for pin in by_refdes.get(refdes, []) if pin.get("pin_role") == "power_out" and isinstance(pin.get("net_name"), str)})
        role["input_nets"] = input_nets
        role["output_nets"] = output_nets
        if role["role"] == "pass_through":
            role["pass_through_nets"] = role["connected_nets"]


def build_role_edges(component_roles: list[dict[str, Any]], pin_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    edge_ids: set[str] = set()

    def add_edge(edge: dict[str, Any]) -> None:
        if edge["edge_id"] in edge_ids:
            return
        edge_ids.add(edge["edge_id"])
        edges.append(edge)

    for role in component_roles:
        refdes = role["refdes"]
        if role["role"] == "source":
            nets = role["output_nets"] or role["power_nets"]
            for net in nets:
                add_edge({
                    "edge_id": f"edge_{safe_id(refdes)}_feeds_{safe_id(net)}",
                    "from_refdes": refdes,
                    "to_refdes": None,
                    "through_refdes": None,
                    "net_name": net,
                    "edge_type": "feeds",
                    "confidence": min(role["confidence"], 0.85),
                    "evidence": [evidence("schematic_connection", "net_name", net, "source component is connected to power/output net")],
                })
        elif role["role"] == "sink":
            for net in role["power_nets"]:
                add_edge({
                    "edge_id": f"edge_{safe_id(refdes)}_consumes_{safe_id(net)}",
                    "from_refdes": None,
                    "to_refdes": refdes,
                    "through_refdes": None,
                    "net_name": net,
                    "edge_type": "consumes",
                    "confidence": min(role["confidence"], 0.8),
                    "evidence": [evidence("schematic_connection", "net_name", net, "sink component is connected to power net")],
                })
        elif role["role"] == "pass_through" and len(role["connected_nets"]) >= 2:
            edge_net = "->".join(role["connected_nets"][:2])
            add_edge({
                "edge_id": f"edge_{safe_id(refdes)}_passes_{safe_id(edge_net)}",
                "from_refdes": None,
                "to_refdes": None,
                "through_refdes": refdes,
                "net_name": edge_net,
                "edge_type": "passes_through",
                "confidence": min(role["confidence"], 0.8),
                "evidence": [evidence("schematic_connection", "connected_nets", role["connected_nets"][:2], "pass-through component connects two nets")],
            })
    return sorted(edges, key=lambda row: row["edge_id"])


def collect_unresolved(component_roles: list[dict[str, Any]], net_roles: list[dict[str, Any]], role_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    sources_by_net: dict[str, list[str]] = {}
    sinks_by_net: dict[str, list[str]] = {}
    for edge in role_edges:
        if edge.get("edge_type") == "feeds" and isinstance(edge.get("net_name"), str):
            sources_by_net.setdefault(edge["net_name"], []).append(str(edge.get("from_refdes")))
        elif edge.get("edge_type") == "consumes" and isinstance(edge.get("net_name"), str):
            sinks_by_net.setdefault(edge["net_name"], []).append(str(edge.get("to_refdes")))

    for role in component_roles:
        refdes = role["refdes"]
        if role["role"] == "unknown":
            unresolved.append(unresolved_record(
                "component_role_unknown",
                "component",
                refdes,
                "Component role could not be deterministically classified.",
                ["rail_relationships", "current_allocation", "calculation_readiness"],
                "ai_rule_batch",
                ["TOPO_ROLE_IC_LOAD_001"],
            ))
        if "connector_direction_unknown" in role.get("unresolved", []):
            unresolved.append(unresolved_record(
                "connector_direction_unknown",
                "component",
                refdes,
                "Connector is attached to a power net but direction is not deterministic.",
                ["rail_relationships", "current_allocation"],
                "human_review",
                ["TOPO_ROLE_CONNECTOR_001"],
            ))
        if "regulator_input_output_unknown" in role.get("unresolved", []):
            unresolved.append(unresolved_record(
                "regulator_input_output_unknown",
                "component",
                refdes,
                "Regulator/converter role was detected but input/output pins were not both deterministic.",
                ["rail_relationships", "current_allocation"],
                "datasheet_extraction",
                ["TOPO_ROLE_REGULATOR_001"],
            ))
        if role["role"] == "pass_through" and len(role["connected_nets"]) < 2:
            unresolved.append(unresolved_record(
                "pass_through_direction_unknown",
                "component",
                refdes,
                "Pass-through component does not have two deterministic connected nets.",
                ["rail_relationships"],
                "deterministic_rule",
                ["TOPO_ROLE_PASS_THROUGH_001"],
            ))

    for net in net_roles:
        if net["role"] != "power":
            continue
        name = net["net_name"]
        if not sources_by_net.get(name):
            unresolved.append(unresolved_record(
                "rail_source_unknown",
                "rail",
                name,
                "Power rail has no deterministic source candidate.",
                ["rail_relationships", "current_allocation", "calculation_readiness"],
                "ai_rule_batch",
                ["TOPO_ROLE_RAIL_SOURCE_001"],
            ))
        if not sinks_by_net.get(name):
            unresolved.append(unresolved_record(
                "rail_sink_unknown",
                "rail",
                name,
                "Power rail has no deterministic sink candidate.",
                ["current_allocation", "calculation_readiness"],
                "ai_rule_batch",
                ["TOPO_ROLE_IC_LOAD_001"],
            ))
        unresolved.append(unresolved_record(
            "current_model_missing",
            "rail",
            name,
            "Role resolution does not infer or calculate rail current.",
            ["current_allocation", "calculation_readiness"],
            "datasheet_extraction",
            [],
        ))
    return sorted({item["id"]: item for item in unresolved}.values(), key=lambda row: row["id"])


def resolve_roles(
    project: str,
    topology_path: Path,
    schematic_path: Path,
    part_info_index_path: Path | None,
    part_info_dir: Path | None,
    *,
    strict: bool,
) -> dict[str, Any]:
    topology = load_json(topology_path)
    schematic = load_json(schematic_path)
    if not isinstance(topology, dict):
        raise ValueError(f"topology artifact must be a JSON object: {topology_path}")
    if not isinstance(schematic, dict):
        raise ValueError(f"schematic artifact must be a JSON object: {schematic_path}")
    part_info_index, part_warnings = load_part_info_index(part_info_index_path)

    components, pins, net_names, analysis, topology_net_types, power_rails = merge_inputs(topology, schematic)
    warnings = list(part_warnings)
    errors: list[str] = []

    net_roles = [
        classify_net_role(name, analysis, topology_net_types, power_rails)
        for name in sorted(net_names)
    ]
    net_role_by_name = {row["net_name"]: row for row in net_roles}

    component_roles_by_refdes: dict[str, dict[str, Any]] = {}
    for refdes in sorted(components):
        component = components[refdes]
        part_info = part_info_for_component(refdes, component, part_info_index)
        component_roles_by_refdes[refdes] = classify_component(
            refdes,
            component,
            part_info,
            pins_for_refdes(pins, refdes),
            net_role_by_name,
        )

    pin_roles = build_pin_roles(pins, component_roles_by_refdes)
    assign_component_io(component_roles_by_refdes, pin_roles)
    component_roles = [component_roles_by_refdes[refdes] for refdes in sorted(component_roles_by_refdes)]
    role_edges = build_role_edges(component_roles, pin_roles)

    for edge in role_edges:
        net = edge.get("net_name")
        if not isinstance(net, str):
            continue
        if edge.get("edge_type") == "feeds":
            row = net_role_by_name.get(net)
            if row is not None and edge.get("from_refdes") not in row["connected_sources"]:
                row["connected_sources"].append(edge.get("from_refdes"))
        elif edge.get("edge_type") == "consumes":
            row = net_role_by_name.get(net)
            if row is not None and edge.get("to_refdes") not in row["connected_sinks"]:
                row["connected_sinks"].append(edge.get("to_refdes"))
        elif edge.get("edge_type") == "passes_through":
            for net_part in str(net).split("->"):
                row = net_role_by_name.get(net_part)
                if row is not None and edge.get("through_refdes") not in row["connected_pass_through"]:
                    row["connected_pass_through"].append(edge.get("through_refdes"))

    unresolved = collect_unresolved(component_roles, net_roles, role_edges)
    if strict and any(row["role"] == "unknown" for row in component_roles):
        errors.append("strict mode: unknown component roles present")

    summary = {
        "component_count": len(component_roles),
        "net_count": len(net_roles),
        "role_candidate_count": len(component_roles),
        "source_candidate_count": sum(1 for row in component_roles if row["role"] == "source"),
        "sink_candidate_count": sum(1 for row in component_roles if row["role"] == "sink"),
        "pass_through_candidate_count": sum(1 for row in component_roles if row["role"] == "pass_through"),
        "unknown_candidate_count": sum(1 for row in component_roles if row["role"] == "unknown"),
        "power_net_count": sum(1 for row in net_roles if row["role"] == "power"),
        "unresolved_count": len(unresolved),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "topology": str(topology_path),
            "schematic": str(schematic_path),
            "part_info_index": str(part_info_index_path) if part_info_index_path else None,
            "part_info_dir": str(part_info_dir) if part_info_dir else None,
        },
        "summary": summary,
        "component_roles": component_roles,
        "net_roles": net_roles,
        "pin_roles": pin_roles,
        "role_edges": role_edges,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "role_resolution_pass": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve deterministic topology roles.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--schematic", default=None)
    parser.add_argument("--part-info-index", default=None)
    parser.add_argument("--part-info-dir", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    topology_path = Path(args.topology or default_path("exports/{project}-topology-map.json", project))
    schematic_path = Path(args.schematic or default_path("exports/{project}-thomson-export-sch.json", project))
    part_info_index_path = Path(args.part_info_index or default_path("exports/{project}-part-info-index.json", project))
    part_info_dir = Path(args.part_info_dir or "exports/part_info")
    out_path = Path(args.out or default_path("exports/{project}-topology-role-resolution.json", project))

    try:
        if not topology_path.exists():
            raise FileNotFoundError(f"missing topology JSON: {topology_path}")
        if not schematic_path.exists():
            raise FileNotFoundError(f"missing schematic JSON: {schematic_path}")
        artifact = resolve_roles(
            project,
            topology_path,
            schematic_path,
            part_info_index_path,
            part_info_dir,
            strict=args.strict,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology role resolution: "
        f"components={summary['component_count']} nets={summary['net_count']} "
        f"sources={summary['source_candidate_count']} sinks={summary['sink_candidate_count']} "
        f"pass_through={summary['pass_through_candidate_count']} unresolved={summary['unresolved_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} out={out_path}"
    )
    return 0 if artifact["role_resolution_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
