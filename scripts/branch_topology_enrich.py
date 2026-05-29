#!/usr/bin/env python3
"""Enrich branch topology with role and rail context.

PR 14 scope only: attach deterministic role-resolution, rail-relationship, and
optional geometry-review context to branch records. This script does not infer
current, allocate current, calculate voltage drop/current density/thermal rise,
create findings, call AI, or mutate prior artifacts.
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
POWER_NAMES = {"VCC", "VDD", "VBAT", "VSYS", "VBUS", "VIN", "VOUT"}


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


def add_unique(values: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in values:
        values.append(value)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def parse_voltage_from_net_name(net_name: Any) -> float | None:
    if not isinstance(net_name, str) or not net_name:
        return None
    text = net_name.strip().upper()
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


def is_ground_name(net_name: Any) -> bool:
    return isinstance(net_name, str) and net_name.upper() in GROUND_NAMES


def is_power_like_name(net_name: Any) -> bool:
    if not isinstance(net_name, str) or not net_name:
        return False
    upper = net_name.upper()
    if upper in POWER_NAMES:
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
    *,
    blocks: list[str] | None = None,
    recommended: str = "human_review",
    rules: list[str] | None = None,
    seed: str | None = None,
) -> dict[str, Any]:
    suffix = safe_id(seed or notes)
    return {
        "id": f"unres_enrich_{safe_id(target_type)}_{safe_id(target_id)}_{safe_id(category)}_{suffix}",
        "category": category,
        "target_type": target_type,
        "target_id": target_id,
        "notes": notes,
        "blocks": blocks or ["current_allocation", "calculation_readiness"],
        "recommended_resolution": recommended,
        "candidate_rule_ids": rules or [],
    }


def normalize_unresolved(item: dict[str, Any], *, target_type: str, target_id: str, seed: str) -> dict[str, Any]:
    category = item.get("category") or item.get("type") or "human_review_needed"
    notes = item.get("notes") or f"Upstream unresolved item: {category}."
    blocks = item.get("blocks") if isinstance(item.get("blocks"), list) else ["current_allocation", "calculation_readiness"]
    recommended = item.get("recommended_resolution") if isinstance(item.get("recommended_resolution"), str) else "human_review"
    rules = item.get("candidate_rule_ids") if isinstance(item.get("candidate_rule_ids"), list) else []
    return unresolved_record(
        str(category),
        target_type,
        target_id,
        str(notes),
        blocks=[str(block) for block in blocks],
        recommended=recommended,
        rules=[str(rule) for rule in rules],
        seed=seed,
    )


def branch_rows(branch_topology: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("branches", "branch_records", "branch_topology", "records"):
        rows = branch_topology.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def role_net_index(role_resolution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["net_name"]: row
        for row in as_list(role_resolution.get("net_roles"))
        if isinstance(row, dict) and isinstance(row.get("net_name"), str)
    }


def component_index(role_resolution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["refdes"]: row
        for row in as_list(role_resolution.get("component_roles"))
        if isinstance(row, dict) and isinstance(row.get("refdes"), str)
    }


def rail_index(rail_relationships: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["rail"]: row
        for row in as_list(rail_relationships.get("rails"))
        if isinstance(row, dict) and isinstance(row.get("rail"), str)
    }


def relationship_index(rail_relationships: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["relationship_id"]: row
        for row in as_list(rail_relationships.get("relationships"))
        if isinstance(row, dict) and isinstance(row.get("relationship_id"), str)
    }


def geometry_indexes(geometry_review: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    if not isinstance(geometry_review, dict):
        return {}, {}
    records = {
        row["branch_id"]: row
        for row in as_list(geometry_review.get("review_records"))
        if isinstance(row, dict) and isinstance(row.get("branch_id"), str)
    }
    evidence_counts: dict[str, int] = {}
    for row in as_list(geometry_review.get("evidence_records")):
        if isinstance(row, dict) and isinstance(row.get("branch_id"), str):
            evidence_counts[row["branch_id"]] = evidence_counts.get(row["branch_id"], 0) + 1
    return records, evidence_counts


def lookup_case_insensitive(index: dict[str, dict[str, Any]], name: Any) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(name, str):
        return None, None
    if name in index:
        return name, index[name]
    lowered = name.lower()
    for key, value in index.items():
        if key.lower() == lowered:
            return key, value
    return None, None


def role_for_net(net_roles: dict[str, dict[str, Any]], net_name: str | None) -> str:
    _, row = lookup_case_insensitive(net_roles, net_name)
    role = row.get("role") if isinstance(row, dict) else None
    return role if isinstance(role, str) else "unknown"


def component_touches_net(component: dict[str, Any], net_name: str) -> bool:
    for key in ("connected_nets", "power_nets", "ground_nets", "input_nets", "output_nets", "pass_through_nets"):
        if any(isinstance(net, str) and net.lower() == net_name.lower() for net in as_list(component.get(key))):
            return True
    return False


def candidate_record(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "refdes": component.get("refdes"),
        "role": component.get("role", "unknown"),
        "role_subtype": component.get("role_subtype", "unknown"),
        "confidence": float(component.get("confidence") or 0.0),
        "evidence_refs": [],
    }


def connected_component_record(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "refdes": component.get("refdes"),
        "role": component.get("role", "unknown"),
        "role_subtype": component.get("role_subtype", "unknown"),
        "confidence": float(component.get("confidence") or 0.0),
    }


def dedupe_records(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        value = record.get(key)
        if isinstance(value, str):
            deduped[value] = record
    return [deduped[name] for name in sorted(deduped)]


def relationship_snippet(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "relationship_id": row.get("relationship_id"),
        "relationship_type": row.get("relationship_type"),
        "parent_rail": row.get("parent_rail"),
        "child_rail": row.get("child_rail"),
        "through_component": row.get("through_component"),
        "through_subtype": row.get("through_subtype"),
        "confidence": float(row.get("confidence") or 0.0),
        "direction": row.get("direction", "unknown"),
    }


def attach_relationships(
    rail_name: str | None,
    net_name: str,
    relationships: dict[str, dict[str, Any]],
    components: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relationship in relationships.values():
        parent = relationship.get("parent_rail")
        child = relationship.get("child_rail")
        through = relationship.get("through_component")
        involves_rail = isinstance(rail_name, str) and (parent == rail_name or child == rail_name)
        through_touches = (
            isinstance(through, str)
            and through in components
            and component_touches_net(components[through], net_name)
        )
        if involves_rail or through_touches:
            rows.append(relationship_snippet(relationship))
    return sorted(rows, key=lambda row: str(row.get("relationship_id") or ""))


def summarize_geometry(record: dict[str, Any] | None, evidence_count: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    geometry = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    stackup = record.get("stackup") if isinstance(record.get("stackup"), dict) else {}
    context = {
        "has_geometry_context": True,
        "geometry_record_count": 1,
        "evidence_count": evidence_count or len(as_list(record.get("evidence"))),
        "unresolved_count": len(as_list(record.get("unresolved_flags"))),
        "branch_type": record.get("branch_type"),
        "layer": record.get("layer") or stackup.get("primary_layer"),
        "copper_thickness": stackup.get("copper_thickness"),
        "stackup": {
            "primary_layer": stackup.get("primary_layer"),
            "is_copper_layer": stackup.get("is_copper_layer"),
            "is_drill_layer": stackup.get("is_drill_layer"),
            "layer_function": stackup.get("layer_function"),
            "side": stackup.get("side"),
            "via_span": stackup.get("via_span"),
        },
    }
    for key in ("units", "known_width_count", "min_width", "max_width", "total_length", "total_area", "bbox"):
        if key in geometry:
            context[key] = geometry.get(key)
    return context


def explicit_current(branch: dict[str, Any]) -> tuple[bool, float | None, str | None, float]:
    for key in ("branch_current_a", "estimated_current_a", "current_a"):
        value = branch.get(key)
        if is_number(value):
            source = branch.get("current_source") or branch.get("current_model_ref") or branch.get("current_basis")
            confidence = branch.get("current_confidence")
            return True, float(value), str(source) if source not in (None, "") else "branch_topology", float(confidence) if is_number(confidence) else 1.0
    return False, None, None, 0.0


def upstream_unresolved_for_branch(branch: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    branch_id = str(branch.get("branch_id") or "unknown")
    for flag in as_list(branch.get("unresolved_flags")):
        if isinstance(flag, str):
            rows.append(unresolved_record(
                flag,
                "branch",
                branch_id,
                f"Upstream branch topology unresolved flag: {flag}.",
                recommended="deterministic_rule",
                seed=flag,
            ))
    for item in as_list(branch.get("unresolved")):
        if isinstance(item, dict):
            rows.append(normalize_unresolved(item, target_type="branch", target_id=branch_id, seed=str(item.get("id") or item.get("type") or item.get("category"))))
    return rows


def role_unresolved_for_branch(net_name: str, connected: list[dict[str, Any]], role_resolution: dict[str, Any]) -> list[dict[str, Any]]:
    refdeses = {row.get("refdes") for row in connected if isinstance(row.get("refdes"), str)}
    rows: list[dict[str, Any]] = []
    for item in as_list(role_resolution.get("unresolved")):
        if not isinstance(item, dict):
            continue
        target_type = item.get("target_type")
        target_id = item.get("target_id")
        if (target_type == "component" and target_id in refdeses) or (target_type in {"rail", "net"} and target_id == net_name):
            rows.append(normalize_unresolved(item, target_type="branch", target_id=net_name, seed=str(item.get("id") or item.get("category"))))
    return rows


def rail_unresolved_for_branch(
    rail_name: str | None,
    relationship_rows: list[dict[str, Any]],
    rail_relationships: dict[str, Any],
    relationship_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rel_ids = {row.get("relationship_id") for row in relationship_rows}
    rows: list[dict[str, Any]] = []
    for item in as_list(rail_relationships.get("unresolved")):
        if not isinstance(item, dict):
            continue
        target_type = item.get("target_type")
        target_id = item.get("target_id")
        matched = (
            (target_type == "rail" and rail_name is not None and target_id == rail_name)
            or (target_type == "relationship" and target_id in rel_ids)
        )
        if matched:
            rows.append(normalize_unresolved(item, target_type="branch", target_id=rail_name or str(target_id), seed=str(item.get("id") or item.get("category"))))
    for rel_id in rel_ids:
        relationship = relationship_by_id.get(str(rel_id))
        if not isinstance(relationship, dict):
            continue
        for item in as_list(relationship.get("unresolved")):
            if isinstance(item, dict):
                rows.append(normalize_unresolved(item, target_type="branch", target_id=rail_name or str(rel_id), seed=f"{rel_id}:{item.get('id') or item.get('category')}"))
    return rows


def build_rail_context_rows(
    rails: dict[str, dict[str, Any]],
    relationships: dict[str, dict[str, Any]],
    branches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    branch_ids_by_rail: dict[str, list[str]] = {name: [] for name in rails}
    for branch in branches:
        rail_name = branch.get("rail_name")
        branch_id = branch.get("branch_id")
        if isinstance(rail_name, str) and isinstance(branch_id, str):
            add_unique(branch_ids_by_rail.setdefault(rail_name, []), branch_id)

    rows: list[dict[str, Any]] = []
    for name in sorted(rails):
        rail = rails[name]
        relationship_ids = sorted(
            rel_id
            for rel_id, rel in relationships.items()
            if rel.get("parent_rail") == name or rel.get("child_rail") == name
        )
        rows.append({
            "rail": name,
            "role": rail.get("role", "unknown"),
            "voltage": rail.get("voltage"),
            "parent_rails": sorted(as_list(rail.get("parent_rails"))),
            "child_rails": sorted(as_list(rail.get("child_rails"))),
            "source_components": sorted(as_list(rail.get("source_components"))),
            "sink_components": sorted(as_list(rail.get("sink_components"))),
            "pass_through_components": sorted(as_list(rail.get("pass_through_components"))),
            "branch_ids": sorted(branch_ids_by_rail.get(name, [])),
            "relationship_ids": relationship_ids,
            "unresolved": as_list(rail.get("unresolved")),
        })
    return rows


def enrich_branch(
    branch: dict[str, Any],
    *,
    net_roles: dict[str, dict[str, Any]],
    components: dict[str, dict[str, Any]],
    rails: dict[str, dict[str, Any]],
    relationships: dict[str, dict[str, Any]],
    role_resolution: dict[str, Any],
    rail_relationships: dict[str, Any],
    geometry_records: dict[str, dict[str, Any]],
    geometry_evidence_counts: dict[str, int],
) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id") or f"branch_{safe_id(branch.get('net_name'))}")
    net_name = str(branch.get("net_name") or "")
    branch_type = str(branch.get("branch_type") or "unknown")
    rail_name, rail = lookup_case_insensitive(rails, net_name)
    net_role = role_for_net(net_roles, net_name)
    rail_role = str(rail.get("role") if rail else "unknown")
    is_ground = rail_role == "return" or net_role == "ground" or is_ground_name(net_name)
    is_power = (
        rail_role in {"source", "derived", "switched"}
        or net_role == "power"
        or (not is_ground and is_power_like_name(net_name))
    )

    connected_components = [
        connected_component_record(component)
        for component in components.values()
        if component_touches_net(component, net_name)
    ]

    rail_source_refs = set(as_list(rail.get("source_components") if rail else []))
    rail_sink_refs = set(as_list(rail.get("sink_components") if rail else []))
    rail_pass_refs = set(as_list(rail.get("pass_through_components") if rail else []))

    source_candidates = [
        candidate_record(component)
        for component in components.values()
        if component_touches_net(component, net_name)
        and (component.get("role") == "source" or component.get("refdes") in rail_source_refs)
    ]
    sink_candidates = [
        candidate_record(component)
        for component in components.values()
        if component_touches_net(component, net_name)
        and (component.get("role") == "sink" or component.get("refdes") in rail_sink_refs)
    ]
    pass_through_candidates = [
        candidate_record(component)
        for component in components.values()
        if component_touches_net(component, net_name)
        and (
            component.get("role") == "pass_through"
            or component.get("role_subtype") == "mosfet_power_switch_candidate"
            or component.get("refdes") in rail_pass_refs
        )
    ]

    relationship_rows = attach_relationships(rail_name, net_name, relationships, components)
    relationship_ids = [row["relationship_id"] for row in relationship_rows if isinstance(row.get("relationship_id"), str)]
    geometry_record = geometry_records.get(branch_id)
    geometry_context = summarize_geometry(geometry_record, geometry_evidence_counts.get(branch_id, 0))
    current_known, current_a, current_source, current_confidence = explicit_current(branch)

    has_rail_context = rail_name is not None
    parent_rails = sorted(as_list(rail.get("parent_rails") if rail else []))
    child_rails = sorted(as_list(rail.get("child_rails") if rail else []))
    has_source_context = bool(source_candidates or parent_rails or rail_role == "source")
    has_sink_context = bool(sink_candidates or child_rails)
    has_geometry_context = bool(geometry_context)

    unresolved: list[dict[str, Any]] = []
    if is_power and not has_rail_context:
        unresolved.append(unresolved_record("branch_rail_unknown", "branch", branch_id, "Power-like branch does not map to a rail context.", rules=["TOPO_BRANCH_RAIL_001"], seed="branch_rail_unknown"))
    if is_power and not current_known:
        unresolved.append(unresolved_record("branch_current_unknown", "branch", branch_id, "Power branch current remains unresolved.", recommended="datasheet_extraction", seed="branch_current_unknown"))
    if is_power and not has_source_context:
        unresolved.append(unresolved_record("branch_source_unknown", "branch", branch_id, "Power branch has no source or parent rail context.", rules=["TOPO_BRANCH_SOURCE_001"], seed="branch_source_unknown"))
    if is_power and not has_sink_context:
        unresolved.append(unresolved_record("branch_sink_unknown", "branch", branch_id, "Power branch has no sink or child rail context.", rules=["TOPO_BRANCH_SINK_001"], seed="branch_sink_unknown"))
    if is_power and not has_geometry_context:
        unresolved.append(unresolved_record("geometry_context_missing", "branch", branch_id, "Power branch has no geometry review context attached.", recommended="not_required", seed="geometry_context_missing"))

    unresolved.extend(upstream_unresolved_for_branch(branch))
    unresolved.extend(role_unresolved_for_branch(net_name, connected_components, role_resolution))
    unresolved.extend(rail_unresolved_for_branch(rail_name, relationship_rows, rail_relationships, relationships))

    blocked_reasons = sorted({item["category"] for item in unresolved})
    if not current_known and is_power:
        add_unique(blocked_reasons, "branch_current_unknown")
    if is_power and not has_geometry_context:
        add_unique(blocked_reasons, "geometry_context_missing")

    readiness = {
        "has_rail_context": has_rail_context,
        "has_source_context": has_source_context,
        "has_sink_context": has_sink_context,
        "has_geometry_context": has_geometry_context,
        "has_current_model": current_known,
        "ready_for_current_allocation": bool(is_power and has_rail_context and has_source_context and has_sink_context),
        "blocked_reasons": sorted(blocked_reasons),
    }

    branch_evidence = [
        evidence("branch_topology", "branch_topology", "branch_id", branch_id, "branch identity preserved from branch topology"),
        evidence("net_name", "branch_topology", "net_name", net_name, "branch net used for rail and component context mapping"),
    ]
    if rail_name:
        branch_evidence.append(evidence("rail_relationship", "rail_relationships", "rail", rail_name, "branch net maps to rail context"))
    if connected_components:
        branch_evidence.append(evidence("component_role", "role_resolution", "connected_components", [row["refdes"] for row in connected_components], "component roles touch branch net"))
    if geometry_context:
        branch_evidence.append(evidence("geometry_review", "geometry_review", "branch_id", branch_id, "geometry review context attached by branch_id"))

    unresolved_by_id = {item["id"]: item for item in unresolved}
    unresolved = [unresolved_by_id[key] for key in sorted(unresolved_by_id)]

    return {
        "branch_id": branch_id,
        "net_name": net_name,
        "rail_name": rail_name,
        "branch_type": branch_type,
        "is_power_branch": bool(is_power),
        "is_ground_branch": bool(is_ground),
        "rail_role": rail_role,
        "rail_voltage": rail.get("voltage") if rail else None,
        "voltage_source": rail.get("voltage_source") if rail else "unknown",
        "parent_rails": parent_rails,
        "child_rails": child_rails,
        "rail_relationships": relationship_rows,
        "source_candidates": dedupe_records(source_candidates, "refdes"),
        "sink_candidates": dedupe_records(sink_candidates, "refdes"),
        "pass_through_candidates": dedupe_records(pass_through_candidates, "refdes"),
        "connected_components": dedupe_records(connected_components, "refdes"),
        "geometry_context": geometry_context,
        "current_model_status": {
            "branch_current_known": current_known,
            "branch_current_a": current_a,
            "current_source": current_source,
            "current_confidence": current_confidence,
            "current_unresolved": not current_known,
        },
        "calculation_readiness_seed": readiness,
        "evidence": branch_evidence,
        "unresolved": unresolved,
        "_relationship_ids": relationship_ids,
    }


def enrich_branches(
    project: str,
    branch_topology_path: Path,
    role_resolution_path: Path,
    rail_relationships_path: Path,
    geometry_review_path: Path | None,
) -> dict[str, Any]:
    branch_topology = load_json(branch_topology_path)
    role_resolution = load_json(role_resolution_path)
    rail_relationships = load_json(rail_relationships_path)
    if not isinstance(branch_topology, dict):
        raise ValueError(f"branch topology artifact must be a JSON object: {branch_topology_path}")
    if not isinstance(role_resolution, dict):
        raise ValueError(f"role-resolution artifact must be a JSON object: {role_resolution_path}")
    if not isinstance(rail_relationships, dict):
        raise ValueError(f"rail-relationships artifact must be a JSON object: {rail_relationships_path}")
    geometry_review = None
    warnings: list[str] = []
    errors: list[str] = []
    if geometry_review_path is not None:
        if geometry_review_path.exists():
            geometry_review = load_json(geometry_review_path)
            if not isinstance(geometry_review, dict):
                raise ValueError(f"geometry-review artifact must be a JSON object: {geometry_review_path}")
        else:
            warnings.append(f"optional geometry-review input missing: {geometry_review_path}")

    source_branches = sorted(branch_rows(branch_topology), key=lambda row: str(row.get("branch_id") or ""))
    net_roles = role_net_index(role_resolution)
    components = component_index(role_resolution)
    rails = rail_index(rail_relationships)
    relationships = relationship_index(rail_relationships)
    geometry_records, geometry_evidence_counts = geometry_indexes(geometry_review)

    branches = [
        enrich_branch(
            branch,
            net_roles=net_roles,
            components=components,
            rails=rails,
            relationships=relationships,
            role_resolution=role_resolution,
            rail_relationships=rail_relationships,
            geometry_records=geometry_records,
            geometry_evidence_counts=geometry_evidence_counts,
        )
        for branch in source_branches
    ]
    for branch in branches:
        branch.pop("_relationship_ids", None)

    rail_context = build_rail_context_rows(rails, relationships, branches)
    unresolved_by_id: dict[str, dict[str, Any]] = {}
    for branch in branches:
        for item in branch["unresolved"]:
            unresolved_by_id[item["id"]] = item
    unresolved = [unresolved_by_id[key] for key in sorted(unresolved_by_id)]

    summary = {
        "branch_count": len(branches),
        "power_branch_count": sum(1 for branch in branches if branch["is_power_branch"]),
        "enriched_branch_count": len(branches),
        "branches_with_rail_context": sum(1 for branch in branches if branch["rail_name"] is not None),
        "branches_with_source_candidates": sum(1 for branch in branches if branch["source_candidates"]),
        "branches_with_sink_candidates": sum(1 for branch in branches if branch["sink_candidates"]),
        "branches_with_pass_through_candidates": sum(1 for branch in branches if branch["pass_through_candidates"]),
        "branches_with_geometry_context": sum(1 for branch in branches if branch["geometry_context"]),
        "branches_ready_for_current_allocation": sum(1 for branch in branches if branch["calculation_readiness_seed"]["ready_for_current_allocation"]),
        "branches_blocked_for_current_allocation": sum(1 for branch in branches if branch["is_power_branch"] and not branch["calculation_readiness_seed"]["ready_for_current_allocation"]),
        "unresolved_count": len(unresolved),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "branch_topology": str(branch_topology_path),
            "role_resolution": str(role_resolution_path),
            "rail_relationships": str(rail_relationships_path),
            "geometry_review": str(geometry_review_path) if geometry_review_path else None,
        },
        "summary": summary,
        "branches": branches,
        "rail_context": rail_context,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "branch_enrichment_pass": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich branch topology with deterministic role and rail context.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--branch-topology", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--geometry-review", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    branch_path = Path(args.branch_topology or default_path("exports/{project}-branch-topology.json", project))
    role_path = Path(args.role_resolution or default_path("exports/{project}-topology-role-resolution.json", project))
    rail_path = Path(args.rail_relationships or default_path("exports/{project}-rail-relationships.json", project))
    geometry_path = Path(args.geometry_review) if args.geometry_review else None
    out_path = Path(args.out or default_path("exports/{project}-branch-topology-enriched.json", project))

    try:
        if not branch_path.exists():
            raise FileNotFoundError(f"missing branch-topology JSON: {branch_path}")
        if not role_path.exists():
            raise FileNotFoundError(f"missing role-resolution JSON: {role_path}")
        if not rail_path.exists():
            raise FileNotFoundError(f"missing rail-relationships JSON: {rail_path}")
        artifact = enrich_branches(project, branch_path, role_path, rail_path, geometry_path)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "branch topology enrichment: "
        f"branches={summary['branch_count']} "
        f"power={summary['power_branch_count']} "
        f"rail_context={summary['branches_with_rail_context']} "
        f"alloc_ready={summary['branches_ready_for_current_allocation']} "
        f"unresolved={summary['unresolved_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["branch_enrichment_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
