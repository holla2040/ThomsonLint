#!/usr/bin/env python3
"""Inventory deterministic calculation readiness from enriched branch topology.

PR 15 scope only: report what is ready, blocked, and missing before later
current-allocation and copper-calculation stages. This script does not infer,
allocate, or calculate current; compute voltage drop/current density/thermal
rise; create findings; call AI; or mutate prior artifacts.
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
CURRENT_ALLOCATION_BLOCKERS = {
    "branch_rail_unknown",
    "branch_source_unknown",
    "branch_sink_unknown",
    "rail_source_unknown",
    "rail_sink_unknown",
    "relationship_direction_unknown",
    "power_path_direction_unknown",
    "ambiguous_pass_through",
    "component_role_unknown",
    "source_sink_not_resolved",
}
COPPER_BLOCKERS = {
    "branch_current_unknown",
    "current_model_missing",
    "geometry_context_missing",
    "geometry_width_missing",
    "geometry_length_missing",
    "geometry_area_missing",
    "copper_thickness_missing",
    "layer_unknown",
    "voltage_unknown",
}
GROUND_ROLES = {"return"}


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


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evidence(item_type: str, source: str, field: str, value: Any, reason: str) -> dict[str, Any]:
    return {"type": item_type, "source": source, "field": field, "value": value, "reason": reason}


def load_optional_json(path: Path | None, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None:
        return None, []
    if not path.exists():
        return None, [f"optional {label} input missing: {path}"]
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return data, []


def missing_blocks_for_category(category: str) -> list[str]:
    mapping = {
        "branch_rail_unknown": ["current_allocation", "calculation_readiness"],
        "branch_source_unknown": ["current_allocation", "calculation_readiness"],
        "branch_sink_unknown": ["current_allocation", "calculation_readiness"],
        "rail_source_unknown": ["current_allocation", "calculation_readiness"],
        "rail_sink_unknown": ["current_allocation", "calculation_readiness"],
        "relationship_direction_unknown": ["current_allocation", "calculation_readiness"],
        "connector_direction_unknown": ["current_allocation"],
        "power_path_direction_unknown": ["current_allocation", "calculation_readiness"],
        "ambiguous_pass_through": ["current_allocation", "calculation_readiness"],
        "component_role_unknown": ["current_allocation", "calculation_readiness"],
        "source_sink_not_resolved": ["current_allocation", "calculation_readiness"],
        "branch_current_unknown": ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"],
        "current_model_missing": ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"],
        "geometry_context_missing": ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"],
        "geometry_width_missing": ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"],
        "geometry_length_missing": ["copper_calculation", "voltage_drop_calculation"],
        "geometry_area_missing": ["copper_calculation", "thermal_calculation"],
        "copper_thickness_missing": ["copper_calculation", "thermal_calculation"],
        "layer_unknown": ["copper_calculation", "thermal_calculation"],
        "voltage_unknown": ["voltage_drop_calculation"],
    }
    return mapping.get(category, ["calculation_readiness"])


def severity_for_category(category: str) -> str:
    if category in {
        "branch_rail_unknown",
        "branch_source_unknown",
        "branch_sink_unknown",
        "rail_source_unknown",
        "rail_sink_unknown",
        "relationship_direction_unknown",
        "power_path_direction_unknown",
        "branch_current_unknown",
        "current_model_missing",
        "geometry_context_missing",
        "geometry_width_missing",
        "geometry_area_missing",
        "copper_thickness_missing",
        "layer_unknown",
    }:
        return "blocker"
    if category in {"connector_direction_unknown", "ambiguous_pass_through", "component_role_unknown", "source_sink_not_resolved", "voltage_unknown"}:
        return "warning"
    return "info"


def recommended_for_category(category: str) -> str:
    if category in {"branch_current_unknown", "current_model_missing", "regulator_input_output_unknown"}:
        return "datasheet_extraction"
    if category in {"component_role_unknown", "ambiguous_pass_through"}:
        return "ai_rule_batch"
    if category in {"geometry_context_missing"}:
        return "deterministic_rule"
    if category in {"connector_direction_unknown", "power_path_direction_unknown", "relationship_direction_unknown"}:
        return "human_review"
    if category in {"branch_rail_unknown", "branch_source_unknown", "branch_sink_unknown", "rail_source_unknown", "rail_sink_unknown"}:
        return "deterministic_rule"
    return "human_review"


def source_for_category(category: str) -> str:
    if category.startswith("geometry_") or category in {"copper_thickness_missing", "layer_unknown"}:
        return "geometry_review"
    if category in {"rail_source_unknown", "rail_sink_unknown", "relationship_direction_unknown", "power_path_direction_unknown", "ambiguous_pass_through", "voltage_unknown"}:
        return "rail_relationships"
    if category in {"component_role_unknown", "connector_direction_unknown", "regulator_input_output_unknown"}:
        return "role_resolution"
    return "branch_topology_enriched"


def missing_data_id(category: str, target_type: str, target_id: str, blocks: list[str]) -> str:
    block_slug = safe_id("_".join(blocks))
    return f"mdi_{safe_id(category)}_{safe_id(target_type)}_{safe_id(target_id)}_{block_slug}"


def missing_data_item(
    category: str,
    target_type: str,
    target_id: str,
    notes: str,
    *,
    scope: str | None = None,
    blocks: list[str] | None = None,
    recommended: str | None = None,
    source_artifact: str | None = None,
    ev: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_blocks = blocks or missing_blocks_for_category(category)
    return {
        "id": missing_data_id(category, target_type, target_id, resolved_blocks),
        "scope": scope or target_type,
        "target_type": target_type,
        "target_id": target_id,
        "category": category,
        "severity": severity_for_category(category),
        "blocks": resolved_blocks,
        "recommended_resolution": recommended or recommended_for_category(category),
        "source_artifact": source_artifact or source_for_category(category),
        "evidence": ev or [],
        "notes": notes,
    }


def add_missing(items: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]], item: dict[str, Any]) -> str:
    key = (item["category"], item["target_type"], item["target_id"], tuple(item["blocks"]))
    if key not in items:
        items[key] = item
    return items[key]["id"]


def readiness(status: str, reasons: list[str], ids: list[str], notes: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "ready": status == "ready",
        "blocking_reasons": sorted(set(reasons)),
        "required_missing_data_ids": sorted(set(ids)),
        "notes": notes or [],
    }


def has_value(value: Any) -> bool:
    return value not in (None, "")


def branch_available_context(branch: dict[str, Any]) -> dict[str, bool]:
    seed = as_dict(branch.get("calculation_readiness_seed"))
    geometry = as_dict(branch.get("geometry_context"))
    stackup = as_dict(geometry.get("stackup"))
    current = as_dict(branch.get("current_model_status"))
    has_layer = has_value(geometry.get("layer")) or has_value(stackup.get("primary_layer"))
    has_copper_thickness = has_value(geometry.get("copper_thickness")) or has_value(stackup.get("copper_thickness"))
    has_width = bool(geometry.get("known_width_count")) or has_value(geometry.get("min_width")) or has_value(geometry.get("max_width"))
    has_length_or_area = has_value(geometry.get("total_length")) or has_value(geometry.get("total_area")) or has_value(geometry.get("bbox"))
    return {
        "has_rail_context": bool(seed.get("has_rail_context") or branch.get("rail_name")),
        "has_source_context": bool(seed.get("has_source_context") or branch.get("source_candidates") or branch.get("parent_rails") or branch.get("rail_role") == "source"),
        "has_sink_context": bool(seed.get("has_sink_context") or branch.get("sink_candidates") or branch.get("child_rails")),
        "has_pass_through_context": bool(branch.get("pass_through_candidates")),
        "has_geometry_context": bool(seed.get("has_geometry_context") or geometry),
        "has_current_model": bool(seed.get("has_current_model") or current.get("branch_current_known")),
        "has_voltage": has_value(branch.get("rail_voltage")),
        "has_layer": has_layer,
        "has_copper_thickness": has_copper_thickness,
        "has_width": has_width,
        "has_length_or_area": has_length_or_area,
    }


def branch_current_allocation(
    branch: dict[str, Any],
    context: dict[str, bool],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id") or "unknown")
    if not branch.get("is_power_branch") or branch.get("is_ground_branch") or branch.get("rail_role") in GROUND_ROLES:
        return readiness("not_required", [], [], ["current allocation is not required for signal or return branches"])

    reasons: list[str] = []
    ids: list[str] = []
    checks = [
        ("has_rail_context", "branch_rail_unknown", "Power branch has no rail context."),
        ("has_source_context", "branch_source_unknown", "Power branch has no source or parent rail context."),
        ("has_sink_context", "branch_sink_unknown", "Power branch has no sink or downstream rail context."),
    ]
    for key, category, notes in checks:
        if not context[key]:
            reasons.append(category)
            ids.append(add_missing(missing, missing_data_item(
                category,
                "branch",
                branch_id,
                notes,
                scope="branch",
                ev=[evidence("branch_topology_enriched", "branch_topology_enriched", key, False, "branch readiness context is missing")],
            )))

    for item in as_list(branch.get("unresolved")):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or item.get("type") or "")
        if category in {"relationship_direction_unknown", "power_path_direction_unknown", "ambiguous_pass_through", "component_role_unknown", "source_sink_not_resolved"}:
            ids.append(add_missing(missing, missing_data_item(
                category,
                str(item.get("target_type") or "branch"),
                str(item.get("target_id") or branch_id),
                str(item.get("notes") or f"{category} affects current allocation."),
                scope="branch",
                blocks=missing_blocks_for_category(category),
                recommended=item.get("recommended_resolution") if isinstance(item.get("recommended_resolution"), str) else None,
                source_artifact=source_for_category(category),
                ev=[evidence("branch_topology_enriched", "branch_topology_enriched", "unresolved", category, "upstream unresolved item affects allocation graph")],
            )))

    status = "blocked" if reasons else "ready"
    return readiness(status, reasons, ids)


def branch_copper_calculation(
    branch: dict[str, Any],
    context: dict[str, bool],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id") or "unknown")
    if not branch.get("is_power_branch") or branch.get("is_ground_branch") or branch.get("rail_role") in GROUND_ROLES:
        return readiness("not_required", [], [], ["copper calculation is not required for signal or return branches in PR 15"])

    reasons: list[str] = []
    ids: list[str] = []

    def require(condition: bool, category: str, notes: str) -> None:
        if condition:
            return
        reasons.append(category)
        ids.append(add_missing(missing, missing_data_item(
            category,
            "branch",
            branch_id,
            notes,
            scope="branch",
            ev=[evidence("branch_topology_enriched", "available_context", category, False, "branch lacks required copper calculation input")],
        )))

    require(context["has_current_model"], "branch_current_unknown", "Power branch current is unknown; PR 15 does not infer current.")
    require(context["has_geometry_context"], "geometry_context_missing", "Power branch lacks geometry review context.")
    require(context["has_layer"], "layer_unknown", "Power branch layer is not known.")
    require(context["has_copper_thickness"], "copper_thickness_missing", "Power branch copper thickness is not known.")
    geometry = as_dict(branch.get("geometry_context"))
    has_area_or_shape = has_value(geometry.get("total_area")) or has_value(geometry.get("bbox"))
    if not (context["has_width"] or has_area_or_shape):
        reasons.append("geometry_width_missing")
        ids.append(add_missing(missing, missing_data_item(
            "geometry_width_missing",
            "branch",
            branch_id,
            "Power branch lacks usable width or area/shape geometry metric.",
            scope="branch",
        )))
    if not context["has_voltage"]:
        reasons.append("voltage_unknown")
        ids.append(add_missing(missing, missing_data_item(
            "voltage_unknown",
            "branch",
            branch_id,
            "Power branch rail voltage is unknown for later voltage-drop readiness.",
            scope="branch",
        )))

    return readiness("blocked" if reasons else "ready", reasons, ids)


def branch_readiness_record(
    branch: dict[str, Any],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    context = branch_available_context(branch)
    allocation = branch_current_allocation(branch, context, missing)
    copper = branch_copper_calculation(branch, context, missing)
    unresolved = [
        item for item in as_list(branch.get("unresolved"))
        if isinstance(item, dict)
    ]
    return {
        "branch_id": branch.get("branch_id"),
        "net_name": branch.get("net_name"),
        "rail_name": branch.get("rail_name"),
        "branch_type": branch.get("branch_type"),
        "is_power_branch": bool(branch.get("is_power_branch")),
        "is_ground_branch": bool(branch.get("is_ground_branch")),
        "rail_role": branch.get("rail_role", "unknown"),
        "rail_voltage": branch.get("rail_voltage"),
        "current_allocation_readiness": allocation,
        "copper_calculation_readiness": copper,
        "available_context": context,
        "source_candidates": as_list(branch.get("source_candidates")),
        "sink_candidates": as_list(branch.get("sink_candidates")),
        "pass_through_candidates": as_list(branch.get("pass_through_candidates")),
        "rail_relationships": as_list(branch.get("rail_relationships")),
        "evidence": [
            evidence("branch_topology_enriched", "branch_topology_enriched", "branch_id", branch.get("branch_id"), "readiness derived from enriched branch record")
        ],
        "unresolved": unresolved,
    }


def rail_available_context(rail: dict[str, Any], branch_records: list[dict[str, Any]]) -> dict[str, bool]:
    source_components = as_list(rail.get("source_components"))
    sink_components = as_list(rail.get("sink_components"))
    parent_rails = as_list(rail.get("parent_rails"))
    child_rails = as_list(rail.get("child_rails"))
    return {
        "has_source_context": bool(source_components),
        "has_sink_context": bool(sink_components),
        "has_parent_or_source": bool(parent_rails or source_components or rail.get("role") == "source"),
        "has_child_or_sink": bool(child_rails or sink_components),
        "has_voltage": has_value(rail.get("voltage")),
        "has_any_branch_geometry": any(row["available_context"]["has_geometry_context"] for row in branch_records),
        "has_any_branch_current": any(row["available_context"]["has_current_model"] for row in branch_records),
    }


def rail_current_allocation(
    rail: dict[str, Any],
    context: dict[str, bool],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    rail_name = str(rail.get("rail") or "unknown")
    if rail.get("role") in GROUND_ROLES:
        return readiness("not_required", [], [], ["current allocation is not required for return rails in PR 15"])
    reasons: list[str] = []
    ids: list[str] = []
    if not context["has_parent_or_source"]:
        reasons.append("rail_source_unknown")
        ids.append(add_missing(missing, missing_data_item(
            "rail_source_unknown",
            "rail",
            rail_name,
            "Rail has no source component or parent rail context.",
            scope="rail",
        )))
    if not context["has_child_or_sink"]:
        reasons.append("rail_sink_unknown")
        ids.append(add_missing(missing, missing_data_item(
            "rail_sink_unknown",
            "rail",
            rail_name,
            "Rail has no sink component or child rail context.",
            scope="rail",
        )))
    for item in as_list(rail.get("unresolved")):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or item.get("type") or "")
        if category in {"relationship_direction_unknown", "power_path_direction_unknown", "ambiguous_pass_through"}:
            reasons.append(category)
            ids.append(add_missing(missing, missing_data_item(
                category,
                str(item.get("target_type") or "rail"),
                str(item.get("target_id") or rail_name),
                str(item.get("notes") or f"{category} affects rail allocation."),
                scope="rail",
                recommended=item.get("recommended_resolution") if isinstance(item.get("recommended_resolution"), str) else None,
            )))
    return readiness("blocked" if reasons else "ready", reasons, ids)


def rail_copper_calculation(
    rail: dict[str, Any],
    context: dict[str, bool],
    branch_records: list[dict[str, Any]],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    rail_name = str(rail.get("rail") or "unknown")
    if rail.get("role") in GROUND_ROLES:
        return readiness("not_required", [], [], ["copper calculation is not required for return rails in PR 15"])
    power_branches = [row for row in branch_records if row.get("is_power_branch")]
    if not power_branches:
        return readiness("not_required", [], [], ["rail has no power branch records to calculate"])

    reasons: list[str] = []
    ids: list[str] = []
    for branch in power_branches:
        copper = as_dict(branch.get("copper_calculation_readiness"))
        if copper.get("status") == "blocked":
            for reason in as_list(copper.get("blocking_reasons")):
                if isinstance(reason, str):
                    reasons.append(reason)
            for missing_id in as_list(copper.get("required_missing_data_ids")):
                if isinstance(missing_id, str):
                    ids.append(missing_id)
    if not context["has_voltage"]:
        reasons.append("voltage_unknown")
        ids.append(add_missing(missing, missing_data_item(
            "voltage_unknown",
            "rail",
            rail_name,
            "Rail voltage is unknown for later voltage-drop readiness.",
            scope="rail",
        )))
    return readiness("blocked" if reasons else "ready", reasons, ids)


def rail_readiness_record(
    rail: dict[str, Any],
    branch_records: list[dict[str, Any]],
    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]],
) -> dict[str, Any]:
    context = rail_available_context(rail, branch_records)
    allocation = rail_current_allocation(rail, context, missing)
    copper = rail_copper_calculation(rail, context, branch_records, missing)
    missing_ids = sorted(set(as_list(allocation.get("required_missing_data_ids")) + as_list(copper.get("required_missing_data_ids"))))
    return {
        "rail": rail.get("rail"),
        "role": rail.get("role", "unknown"),
        "voltage": rail.get("voltage"),
        "parent_rails": sorted(as_list(rail.get("parent_rails"))),
        "child_rails": sorted(as_list(rail.get("child_rails"))),
        "branch_ids": sorted(as_list(rail.get("branch_ids"))),
        "current_allocation_readiness": allocation,
        "copper_calculation_readiness": copper,
        "available_context": context,
        "missing_data_ids": missing_ids,
        "unresolved": [item for item in as_list(rail.get("unresolved")) if isinstance(item, dict)],
    }


def collect_unresolved(branch_records: list[dict[str, Any]], rail_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for record in branch_records:
        for item in as_list(record.get("unresolved")):
            if isinstance(item, dict):
                rows[str(item.get("id") or f"branch_{record.get('branch_id')}_{item.get('category')}")] = item
    for record in rail_records:
        for item in as_list(record.get("unresolved")):
            if isinstance(item, dict):
                rows[str(item.get("id") or f"rail_{record.get('rail')}_{item.get('category')}")] = item
    return [rows[key] for key in sorted(rows)]


def build_inventory(
    project: str,
    branch_topology_enriched_path: Path,
    role_resolution_path: Path | None,
    rail_relationships_path: Path | None,
    geometry_review_path: Path | None,
) -> dict[str, Any]:
    enriched = load_json(branch_topology_enriched_path)
    if not isinstance(enriched, dict):
        raise ValueError(f"branch-topology-enriched artifact must be a JSON object: {branch_topology_enriched_path}")
    _, role_warnings = load_optional_json(role_resolution_path, "role-resolution")
    _, rail_warnings = load_optional_json(rail_relationships_path, "rail-relationships")
    _, geometry_warnings = load_optional_json(geometry_review_path, "geometry-review")
    warnings = role_warnings + rail_warnings + geometry_warnings
    errors: list[str] = []

    missing: dict[tuple[str, str, str, tuple[str, ...]], dict[str, Any]] = {}
    source_branches = [row for row in as_list(enriched.get("branches")) if isinstance(row, dict)]
    branch_records = [branch_readiness_record(branch, missing) for branch in sorted(source_branches, key=lambda row: str(row.get("branch_id") or ""))]
    branches_by_rail: dict[str, list[dict[str, Any]]] = {}
    for record in branch_records:
        rail_name = record.get("rail_name")
        if isinstance(rail_name, str):
            branches_by_rail.setdefault(rail_name, []).append(record)

    source_rails = [row for row in as_list(enriched.get("rail_context")) if isinstance(row, dict)]
    rail_records = [
        rail_readiness_record(rail, branches_by_rail.get(str(rail.get("rail")), []), missing)
        for rail in sorted(source_rails, key=lambda row: str(row.get("rail") or ""))
    ]
    unresolved = collect_unresolved(branch_records, rail_records)
    missing_data_items = [missing[key] for key in sorted(missing, key=lambda item: (safe_id(item[0]), safe_id(item[1]), safe_id(item[2]), "_".join(item[3])))]

    branch_count = len(branch_records)
    power_branch_count = sum(1 for row in branch_records if row["is_power_branch"])
    ground_branch_count = sum(1 for row in branch_records if row["is_ground_branch"] or row.get("rail_role") == "return")
    signal_branch_count = branch_count - power_branch_count - ground_branch_count
    summary = {
        "branch_count": branch_count,
        "power_branch_count": power_branch_count,
        "ground_branch_count": ground_branch_count,
        "signal_branch_count": signal_branch_count,
        "branches_ready_for_current_allocation_attempt": sum(1 for row in branch_records if row["current_allocation_readiness"]["status"] == "ready"),
        "branches_blocked_from_current_allocation_attempt": sum(1 for row in branch_records if row["current_allocation_readiness"]["status"] == "blocked"),
        "branches_ready_for_copper_calculation": sum(1 for row in branch_records if row["copper_calculation_readiness"]["status"] == "ready"),
        "branches_blocked_from_copper_calculation": sum(1 for row in branch_records if row["copper_calculation_readiness"]["status"] == "blocked"),
        "rails_ready_for_current_allocation_attempt": sum(1 for row in rail_records if row["current_allocation_readiness"]["status"] == "ready"),
        "rails_blocked_from_current_allocation_attempt": sum(1 for row in rail_records if row["current_allocation_readiness"]["status"] == "blocked"),
        "rails_ready_for_copper_calculation": sum(1 for row in rail_records if row["copper_calculation_readiness"]["status"] == "ready"),
        "rails_blocked_from_copper_calculation": sum(1 for row in rail_records if row["copper_calculation_readiness"]["status"] == "blocked"),
        "missing_data_item_count": len(missing_data_items),
        "unresolved_count": len(unresolved),
        "warning_count": len(warnings),
        "error_count": len(errors),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "branch_topology_enriched": str(branch_topology_enriched_path),
            "role_resolution": str(role_resolution_path) if role_resolution_path else None,
            "rail_relationships": str(rail_relationships_path) if rail_relationships_path else None,
            "geometry_review": str(geometry_review_path) if geometry_review_path else None,
        },
        "summary": summary,
        "branch_readiness": branch_records,
        "rail_readiness": rail_records,
        "missing_data_items": missing_data_items,
        "unresolved": unresolved,
        "warnings": warnings,
        "errors": errors,
        "execution_pass": True,
        "calculation_readiness_pass": not errors,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory deterministic calculation readiness.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--branch-topology-enriched", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--rail-relationships", default=None)
    parser.add_argument("--geometry-review", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    branch_path = Path(args.branch_topology_enriched or default_path("exports/{project}-branch-topology-enriched.json", project))
    role_path = Path(args.role_resolution) if args.role_resolution else None
    rail_path = Path(args.rail_relationships) if args.rail_relationships else None
    geometry_path = Path(args.geometry_review) if args.geometry_review else None
    out_path = Path(args.out or default_path("exports/{project}-calculation-readiness-inventory.json", project))

    try:
        if not branch_path.exists():
            raise FileNotFoundError(f"missing branch-topology-enriched JSON: {branch_path}")
        artifact = build_inventory(project, branch_path, role_path, rail_path, geometry_path)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "calculation readiness inventory: "
        f"branches={summary['branch_count']} "
        f"power={summary['power_branch_count']} "
        f"alloc_ready={summary['branches_ready_for_current_allocation_attempt']} "
        f"copper_ready={summary['branches_ready_for_copper_calculation']} "
        f"missing={summary['missing_data_item_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["calculation_readiness_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
