#!/usr/bin/env python3
"""Extract deterministic rail relationships from topology role resolution.

PR 13 scope only: consume role-resolution evidence and emit conservative rail
parent/child relationship candidates. This script does not infer current,
calculate voltage drop/current density/thermal rise, create findings, call AI,
or mutate prior artifacts.
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
GROUND_NAMES = {"GND", "AGND", "DGND", "PGND", "SGND", "VSS"}
PASS_THROUGH_SUBTYPES = {
    "zero_ohm_link",
    "ferrite_bead",
    "fuse",
    "current_sense",
    "jumper",
    "inductor_or_choke_pass_through",
}
NO_RELATIONSHIP_SUBTYPES = {
    "pullup_resistor",
    "pulldown_resistor",
    "divider_or_bleeder_candidate",
    "differential_termination_candidate",
    "series_termination_candidate",
    "passive_decoupling",
    "test_point",
    "test_point_power_or_ground",
    "test_point_signal",
}


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


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def evidence(item_type: str, source: str, field: str, value: Any, reason: str) -> dict[str, Any]:
    return {"type": item_type, "source": source, "field": field, "value": value, "reason": reason}


def parse_voltage_from_net_name(net_name: str | None) -> float | None:
    if not net_name:
        return None
    text = str(net_name).strip().upper()
    if "_" in text:
        text = text.split("_", 1)[0]
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


def is_ground_name(net_name: str) -> bool:
    return net_name.upper() in GROUND_NAMES


def is_rail_like_name(net_name: str) -> bool:
    upper = str(net_name or "").upper()
    if is_ground_name(upper):
        return True
    if upper in {"VCC", "VDD", "VSYS", "VBAT", "VBUS", "VIN", "VOUT"}:
        return True
    if "_" in upper:
        base, suffix = upper.split("_", 1)
        if parse_voltage_from_net_name(base) is None:
            return False
        return suffix in {"SW", "SWITCHED", "LOAD", "EN", "OUT", "FUSED", "PROT", "IN", "RAW", "VIN", "BUS"}
    return parse_voltage_from_net_name(upper) is not None


def unresolved_record(
    category: str,
    target_type: str,
    target_id: str,
    notes: str,
    blocks: list[str] | None = None,
    recommended: str = "human_review",
    rules: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"unres_rail_{safe_id(target_type)}_{safe_id(target_id)}_{safe_id(category)}",
        "category": category,
        "target_type": target_type,
        "target_id": target_id,
        "notes": notes,
        "blocks": blocks or ["current_allocation", "calculation_readiness"],
        "recommended_resolution": recommended,
        "candidate_rule_ids": rules or [],
    }


def load_optional_json(path: Path | None) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None:
        return None, []
    if not path.exists():
        return None, [f"optional input missing: {path}"]
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"optional input must be a JSON object: {path}")
    return data, []


def schematic_root(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("schematic"), dict):
        return data["schematic"]
    return data if isinstance(data, dict) else {}


def analysis_names(schematic: dict[str, Any] | None, key: str) -> set[str]:
    root = schematic_root(schematic)
    analysis = root.get("analysis") if isinstance(root.get("analysis"), dict) else {}
    values = analysis.get(key)
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if value not in (None, "")}


def topology_power_rails(topology: dict[str, Any] | None) -> set[str]:
    if not isinstance(topology, dict):
        return set()
    rails: set[str] = set()
    for rail in topology.get("power_rails", []) if isinstance(topology.get("power_rails"), list) else []:
        if isinstance(rail, dict) and isinstance(rail.get("net_name"), str):
            rails.add(rail["net_name"])
    for net in topology.get("nets", []) if isinstance(topology.get("nets"), list) else []:
        if isinstance(net, dict) and net.get("net_type") == "power" and isinstance(net.get("net_name"), str):
            rails.add(net["net_name"])
    return rails


def discover_rail_names(role_resolution: dict[str, Any], topology: dict[str, Any] | None, schematic: dict[str, Any] | None) -> set[str]:
    rails: set[str] = set()
    for row in role_resolution.get("net_roles", []) if isinstance(role_resolution.get("net_roles"), list) else []:
        if isinstance(row, dict) and row.get("role") in {"power", "ground"} and isinstance(row.get("net_name"), str):
            rails.add(row["net_name"])
    for component in role_resolution.get("component_roles", []) if isinstance(role_resolution.get("component_roles"), list) else []:
        if not isinstance(component, dict):
            continue
        for key in ("power_nets", "ground_nets"):
            for net in component.get(key, []) if isinstance(component.get(key), list) else []:
                if isinstance(net, str):
                    rails.add(net)
        for net in component.get("connected_nets", []) if isinstance(component.get("connected_nets"), list) else []:
            if isinstance(net, str) and is_rail_like_name(net):
                rails.add(net)
    rails.update(topology_power_rails(topology))
    rails.update(analysis_names(schematic, "power_nets"))
    rails.update(analysis_names(schematic, "ground_nets"))
    return rails


def build_rail(name: str, role_resolution: dict[str, Any]) -> dict[str, Any]:
    net_role = next(
        (
            row
            for row in role_resolution.get("net_roles", [])
            if isinstance(row, dict) and row.get("net_name") == name
        ),
        {},
    )
    if is_ground_name(name) or net_role.get("role") == "ground":
        role = "return"
        confidence = 0.95
    elif net_role.get("role") == "power":
        role = "unknown"
        confidence = float(net_role.get("confidence") or 0.8)
    else:
        role = "unknown"
        confidence = 0.55
    voltage = parse_voltage_from_net_name(name)
    return {
        "rail": name,
        "role": role,
        "voltage": voltage,
        "voltage_source": "net_name" if voltage is not None else "unknown",
        "confidence": confidence,
        "source_components": [],
        "sink_components": [],
        "pass_through_components": [],
        "parent_rails": [],
        "child_rails": [],
        "evidence": [
            evidence("voltage_parse", "net_name", "net_name", name, "voltage parsed from net name")
        ]
        if voltage is not None
        else [],
        "unresolved": [],
    }


def component_by_refdes(role_resolution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["refdes"]: row
        for row in role_resolution.get("component_roles", [])
        if isinstance(row, dict) and isinstance(row.get("refdes"), str)
    }


def pin_roles_by_refdes(role_resolution: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_refdes: dict[str, list[dict[str, Any]]] = {}
    for row in role_resolution.get("pin_roles", []) if isinstance(role_resolution.get("pin_roles"), list) else []:
        if isinstance(row, dict) and isinstance(row.get("refdes"), str):
            by_refdes.setdefault(row["refdes"], []).append(row)
    return by_refdes


def add_unique(values: list[str], value: str | None) -> None:
    if isinstance(value, str) and value not in values:
        values.append(value)


def relationship_id(parent: str | None, through: str | None, child: str | None, rel_type: str) -> str:
    return f"rel_{safe_id(parent or 'external')}_{safe_id(through or rel_type)}_{safe_id(child or 'unknown')}"


def relationship(
    rel_type: str,
    parent: str | None,
    child: str | None,
    through: str | None,
    subtype: str | None,
    confidence: float,
    direction: str,
    ev: list[dict[str, Any]],
    unresolved: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "relationship_id": relationship_id(parent, through, child, rel_type),
        "relationship_type": rel_type,
        "parent_rail": parent,
        "child_rail": child,
        "through_component": through,
        "through_subtype": subtype,
        "confidence": confidence,
        "direction": direction,
        "evidence": ev,
        "unresolved": unresolved or [],
    }


def switched_score(name: str) -> int:
    upper = name.upper()
    score = 0
    if re.search(r"(_SW|_SWITCHED|_LOAD|_EN|_OUT|_FUSED|_PROT)(?:_|$)", upper):
        score += 2
    if re.search(r"(_IN|_RAW|_VIN|_BUS)(?:_|$)", upper):
        score -= 2
    return score


def choose_parent_child(rails: list[str]) -> tuple[str | None, str | None, bool]:
    if len(rails) != 2:
        return None, None, False
    first, second = rails
    score_first = switched_score(first)
    score_second = switched_score(second)
    if score_first != score_second:
        return (second, first, True) if score_first > score_second else (first, second, True)
    v_first = parse_voltage_from_net_name(first)
    v_second = parse_voltage_from_net_name(second)
    if v_first is not None and v_second is not None and abs(v_first) != abs(v_second):
        return (first, second, True) if abs(v_first) > abs(v_second) else (second, first, True)
    return first, second, False


def regulator_relationship(component: dict[str, Any], pins: list[dict[str, Any]], rails: set[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    refdes = component["refdes"]
    subtype = component.get("role_subtype")
    input_nets = sorted({pin.get("net_name") for pin in pins if pin.get("pin_role") == "power_in" and pin.get("net_name") in rails})
    output_nets = sorted({pin.get("net_name") for pin in pins if pin.get("pin_role") == "power_out" and pin.get("net_name") in rails})
    unresolved: list[dict[str, Any]] = []
    if len(input_nets) == 1 and len(output_nets) == 1:
        return relationship(
            "regulator_conversion",
            input_nets[0],
            output_nets[0],
            refdes,
            subtype,
            0.85,
            "parent_to_child",
            [
                evidence("pin_role", "role_resolution", "power_in", input_nets[0], "regulator input rail from power_in pin"),
                evidence("pin_role", "role_resolution", "power_out", output_nets[0], "regulator output rail from power_out pin"),
            ],
        ), unresolved
    unresolved.append(unresolved_record(
        "regulator_input_output_unknown",
        "component",
        refdes,
        "Regulator input/output rails are not uniquely determined.",
        recommended="datasheet_extraction",
        rules=["TOPO_RAIL_REGULATOR_001"],
    ))
    candidate = None
    if input_nets or output_nets:
        candidate = relationship(
            "candidate",
            input_nets[0] if input_nets else None,
            output_nets[0] if output_nets else None,
            refdes,
            subtype,
            0.45,
            "unknown",
            [evidence("pin_role", "role_resolution", "pin_roles", {"inputs": input_nets, "outputs": output_nets}, "partial regulator rail evidence")],
            unresolved,
        )
    return candidate, unresolved


def regulator_like_description(component: dict[str, Any]) -> bool:
    text = f"{component.get('description') or ''} {component.get('value') or ''} {component.get('mpn') or ''}".lower()
    return any(token in text for token in ("regulator", "ldo", "buck", "boost", "converter", "power_module", "pwr_lin"))


def regulator_relationship_from_voltage(component: dict[str, Any], effective_rails: list[str]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    refdes = component["refdes"]
    subtype = component.get("role_subtype")
    rails_with_voltage = [(rail, parse_voltage_from_net_name(rail)) for rail in effective_rails]
    rails_with_voltage = [(rail, voltage) for rail, voltage in rails_with_voltage if voltage is not None]
    if len(rails_with_voltage) != 2:
        item = unresolved_record(
            "regulator_input_output_unknown",
            "component",
            refdes,
            "Regulator-like component has no deterministic VIN/VOUT pin evidence.",
            recommended="datasheet_extraction",
            rules=["TOPO_RAIL_REGULATOR_001"],
        )
        return None, [item]
    parent, child = sorted(rails_with_voltage, key=lambda item: abs(item[1]), reverse=True)
    item = unresolved_record(
        "regulator_input_output_unknown",
        "relationship",
        f"{refdes}:{parent[0]}:{child[0]}",
        "Regulator relationship direction is voltage/name-derived because VIN/VOUT pin evidence is missing.",
        recommended="datasheet_extraction",
        rules=["TOPO_RAIL_REGULATOR_001"],
    )
    return relationship(
        "regulator_conversion",
        parent[0],
        child[0],
        refdes,
        subtype,
        0.7,
        "parent_to_child",
        [
            evidence("component_role", "role_resolution", "description", component.get("description"), "component description suggests regulator-like power conversion"),
            evidence("voltage_parse", "net_name", "connected_nets", effective_rails, "parent/child selected from parseable rail voltages"),
        ],
        [item],
    ), [item]


def extract_relationships(
    role_resolution: dict[str, Any],
    rail_names: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    relationships: list[dict[str, Any]] = []
    source_candidates: list[dict[str, Any]] = []
    derived_candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    pins_by_refdes = pin_roles_by_refdes(role_resolution)

    for component in role_resolution.get("component_roles", []) if isinstance(role_resolution.get("component_roles"), list) else []:
        if not isinstance(component, dict) or not isinstance(component.get("refdes"), str):
            continue
        refdes = component["refdes"]
        subtype = component.get("role_subtype")
        connected_rails = sorted(
            {
                net
                for net in component.get("connected_nets", [])
                if isinstance(net, str) and net in rail_names and not is_ground_name(net)
            }
        )
        power_rails = sorted(
            {
                net
                for net in component.get("power_nets", [])
                if isinstance(net, str) and net in rail_names and not is_ground_name(net)
            }
        )
        effective_rails = sorted(set(connected_rails) | set(power_rails))

        if component.get("role") == "source" and subtype == "connector_power_input_or_io":
            for rail in power_rails:
                rel = relationship(
                    "connector_input",
                    None,
                    rail,
                    refdes,
                    subtype,
                    0.65,
                    "unknown",
                    [evidence("component_role", "role_resolution", "role_subtype", subtype, "connector source candidate connected to power rail")],
                    [unresolved_record("relationship_direction_unknown", "relationship", f"{refdes}:{rail}", "Connector direction is ambiguous.", recommended="human_review", rules=["TOPO_RAIL_CONNECTOR_001"])],
                )
                relationships.append(rel)
                source_candidates.append({"rail": rail, "component": refdes, "confidence": rel["confidence"], "evidence": rel["evidence"]})
            continue

        subtype_text = str(subtype or "")
        is_regulator = component.get("role") == "source" and any(token in subtype_text for token in ("regulator", "ldo", "buck", "boost", "converter", "power_module"))
        pin_roles = pins_by_refdes.get(refdes, [])
        if is_regulator or (
            any(pin.get("pin_role") == "power_in" for pin in pin_roles)
            and any(pin.get("pin_role") == "power_out" for pin in pin_roles)
        ):
            rel, items = regulator_relationship(component, pin_roles, rail_names)
            unresolved.extend(items)
            if rel is not None:
                relationships.append(rel)
                derived_candidates.append({"rail": rel.get("child_rail"), "component": refdes, "confidence": rel["confidence"], "evidence": rel["evidence"]})
            continue
        if regulator_like_description(component) and len(effective_rails) == 2:
            rel, items = regulator_relationship_from_voltage(component, effective_rails)
            unresolved.extend(items)
            if rel is not None:
                relationships.append(rel)
                derived_candidates.append({"rail": rel.get("child_rail"), "component": refdes, "confidence": rel["confidence"], "evidence": rel["evidence"]})
            continue

        if subtype == "mosfet_power_switch_candidate":
            if len(effective_rails) == 2:
                parent, child, directional = choose_parent_child(effective_rails)
                items = [unresolved_record(
                    "power_path_direction_unknown",
                    "relationship",
                    f"{refdes}:{parent}:{child}",
                    "MOSFET power path direction is heuristic and unresolved.",
                    recommended="human_review",
                    rules=["TOPO_RAIL_POWER_SWITCH_001"],
                )]
                rel = relationship(
                    "switched_power_path",
                    parent,
                    child,
                    refdes,
                    subtype,
                    0.72 if directional else 0.65,
                    "parent_to_child" if directional else "unknown",
                    [evidence("component_role", "role_resolution", "role_subtype", subtype, "MOSFET power switch candidate connects two rail-like nets")],
                    items,
                )
                relationships.append(rel)
                unresolved.extend(items)
                derived_candidates.append({"rail": child, "component": refdes, "confidence": rel["confidence"], "evidence": rel["evidence"]})
            elif len(effective_rails) == 1:
                unresolved.append(unresolved_record("rail_child_unknown", "component", refdes, "MOSFET power switch candidate has only one rail-like net.", rules=["TOPO_RAIL_POWER_SWITCH_001"]))
            continue

        if component.get("role") == "pass_through" and subtype in PASS_THROUGH_SUBTYPES:
            if len(effective_rails) == 2:
                parent, child, directional = choose_parent_child(effective_rails)
                items = [] if directional else [unresolved_record("relationship_direction_unknown", "relationship", f"{refdes}:{parent}:{child}", "Pass-through relationship direction is not deterministic.", rules=["TOPO_RAIL_PASS_THROUGH_001"])]
                rel = relationship(
                    "pass_through",
                    parent,
                    child,
                    refdes,
                    subtype,
                    0.6,
                    "parent_to_child" if directional else "unknown",
                    [evidence("component_role", "role_resolution", "role_subtype", subtype, "pass-through component connects two rails")],
                    items,
                )
                relationships.append(rel)
                unresolved.extend(items)
            continue

        if subtype in NO_RELATIONSHIP_SUBTYPES:
            continue

        header_like = refdes.upper().startswith(("JP", "J", "P")) or "header" in str(component.get("description") or "").lower()
        if header_like and len(effective_rails) >= 2 and component.get("role") in {"unknown", "bidirectional_or_interface"}:
            for idx in range(len(effective_rails) - 1):
                parent = effective_rails[idx]
                child = effective_rails[idx + 1]
                items = [unresolved_record(
                    "ambiguous_pass_through",
                    "relationship",
                    f"{refdes}:{parent}:{child}",
                    "Header/jumper-like component connects multiple rails but direction/function is ambiguous.",
                    recommended="human_review",
                    rules=["TOPO_RAIL_PASS_THROUGH_001"],
                )]
                rel = relationship(
                    "candidate",
                    parent,
                    child,
                    refdes,
                    subtype,
                    0.4,
                    "unknown",
                    [evidence("schematic_connection", "role_resolution", "connected_nets", effective_rails, "unknown/interface component connects multiple rails")],
                    items,
                )
                relationships.append(rel)
                unresolved.extend(items)

    deduped: dict[str, dict[str, Any]] = {}
    for rel in relationships:
        deduped[rel["relationship_id"]] = rel
    return list(deduped.values()), source_candidates, derived_candidates, unresolved


def aggregate_rails(
    rails: dict[str, dict[str, Any]],
    components: dict[str, dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for refdes, component in components.items():
        subtype = component.get("role_subtype")
        for rail_name in component.get("connected_nets", []) if isinstance(component.get("connected_nets"), list) else []:
            if rail_name not in rails:
                continue
            rail = rails[rail_name]
            if rail["role"] != "return" and component.get("role") == "source" and subtype == "connector_power_input_or_io":
                add_unique(rail["source_components"], refdes)
            elif component.get("role") == "sink":
                add_unique(rail["sink_components"], refdes)
            elif component.get("role") == "pass_through" or subtype == "mosfet_power_switch_candidate":
                add_unique(rail["pass_through_components"], refdes)
            elif subtype in {"pullup_resistor", "pulldown_resistor", "divider_or_bleeder_candidate", "differential_termination_candidate"}:
                add_unique(rail["sink_components"], refdes)

    for rel in relationships:
        parent = rel.get("parent_rail")
        child = rel.get("child_rail")
        through = rel.get("through_component")
        if isinstance(child, str) and child in rails:
            if isinstance(parent, str):
                add_unique(rails[child]["parent_rails"], parent)
            if rel.get("relationship_type") in {"connector_input", "regulator_conversion", "switched_power_path"}:
                add_unique(rails[child]["source_components"], through)
        if isinstance(parent, str) and parent in rails and isinstance(child, str):
            add_unique(rails[parent]["child_rails"], child)

    for rail in rails.values():
        if rail["role"] == "return":
            continue
        if rail["parent_rails"]:
            rail["role"] = "switched" if any(switched_score(rail["rail"]) > 0 for _ in [rail]) else "derived"
        elif rail["source_components"]:
            rail["role"] = "source"
        elif rail["role"] == "unknown" and rail["child_rails"]:
            rail["role"] = "source"
        for key in ("source_components", "sink_components", "pass_through_components", "parent_rails", "child_rails"):
            rail[key] = sorted(rail[key])
    return [rails[name] for name in sorted(rails)]


def build_unresolved_for_rails(rails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved: list[dict[str, Any]] = []
    for rail in rails:
        if rail["role"] == "return":
            continue
        name = rail["rail"]
        if rail["voltage"] is None:
            unresolved.append(unresolved_record("voltage_unknown", "rail", name, "Rail voltage is not deterministic from net name.", recommended="deterministic_rule"))
        if rail["sink_components"] and not rail["source_components"] and not rail["parent_rails"]:
            unresolved.append(unresolved_record("rail_source_unknown", "rail", name, "Rail has sinks but no source or parent rail.", rules=["TOPO_RAIL_SOURCE_001"]))
        if (rail["source_components"] or rail["parent_rails"]) and not rail["sink_components"] and not rail["child_rails"]:
            unresolved.append(unresolved_record("rail_sink_unknown", "rail", name, "Rail has source evidence but no sink or child rail.", rules=["TOPO_RAIL_SINK_001"]))
    return unresolved


def extract_rail_relationships(
    project: str,
    role_resolution_path: Path,
    topology_path: Path | None,
    schematic_path: Path | None,
) -> dict[str, Any]:
    role_resolution = load_json(role_resolution_path)
    if not isinstance(role_resolution, dict):
        raise ValueError(f"role-resolution artifact must be a JSON object: {role_resolution_path}")
    topology, topology_warnings = load_optional_json(topology_path)
    schematic, schematic_warnings = load_optional_json(schematic_path)
    warnings = topology_warnings + schematic_warnings
    errors: list[str] = []

    rail_names = discover_rail_names(role_resolution, topology, schematic)
    rails = {name: build_rail(name, role_resolution) for name in rail_names}
    components = component_by_refdes(role_resolution)
    relationships, source_candidates, derived_candidates, unresolved = extract_relationships(role_resolution, rail_names)
    rail_rows = aggregate_rails(rails, components, relationships)
    unresolved.extend(build_unresolved_for_rails(rail_rows))
    unresolved_by_id = {item["id"]: item for item in unresolved}
    unresolved = [unresolved_by_id[key] for key in sorted(unresolved_by_id)]

    summary = {
        "rail_count": len(rail_rows),
        "relationship_count": len(relationships),
        "source_rail_count": sum(1 for rail in rail_rows if rail["role"] == "source"),
        "derived_rail_count": sum(1 for rail in rail_rows if rail["role"] == "derived"),
        "switched_rail_count": sum(1 for rail in rail_rows if rail["role"] == "switched"),
        "ambiguous_relationship_count": sum(1 for rel in relationships if rel["relationship_type"] == "candidate" or rel["direction"] == "unknown"),
        "unresolved_count": len(unresolved),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "role_resolution": str(role_resolution_path),
            "topology": str(topology_path) if topology_path else None,
            "schematic": str(schematic_path) if schematic_path else None,
        },
        "summary": summary,
        "rails": rail_rows,
        "relationships": sorted(relationships, key=lambda row: row["relationship_id"]),
        "source_candidates": source_candidates,
        "derived_candidates": derived_candidates,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "rail_relationship_pass": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract deterministic rail relationships.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--topology", default=None)
    parser.add_argument("--schematic", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    role_path = Path(args.role_resolution or default_path("exports/{project}-topology-role-resolution.json", project))
    topology_path = Path(args.topology) if args.topology else None
    schematic_path = Path(args.schematic) if args.schematic else None
    out_path = Path(args.out or default_path("exports/{project}-rail-relationships.json", project))

    try:
        if not role_path.exists():
            raise FileNotFoundError(f"missing role-resolution JSON: {role_path}")
        artifact = extract_rail_relationships(project, role_path, topology_path, schematic_path)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "rail relationship extraction: "
        f"rails={summary['rail_count']} relationships={summary['relationship_count']} "
        f"ambiguous={summary['ambiguous_relationship_count']} unresolved={summary['unresolved_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} out={out_path}"
    )
    return 0 if artifact["rail_relationship_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
