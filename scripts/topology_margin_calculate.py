#!/usr/bin/env python3
"""Calculate deterministic topology margin results.

PR 24/25 scope only: calculate fuse and connector-pin current margins when
explicit allocated current, explicit rating, and deterministic topology linkage
are available. This script does not calculate regulator margins, infer ratings,
infer current, create findings, or make compliance judgments.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
ALLOCATION_TYPES = {
    "explicit_branch_current",
    "deterministic_branch_sum",
    "deterministic_passthrough_current",
    "deterministic_single_path_rail_current",
}
FUSE_TARGET_TYPES = {"fuse", "fuse_pin"}
FUSE_ROLE_TARGET_TYPES = {"fuse", "fuse_pin", "pass_through_component"}
FUSE_MARGIN_RATING_NAMES = {
    "hold_current",
    "current_max",
    "continuous_current_max",
    "package_current_limit",
    "thermal_current_limit",
}
CONNECTOR_TARGET_TYPES = {"connector_pin", "connector"}
CONNECTOR_ROLE_TARGET_TYPES = {"connector_pin", "connector", "component"}
CONNECTOR_MARGIN_RATING_NAMES = {"pin_current_max", "current_max"}
MANIFEST_CATEGORIES = {
    "rating_missing",
    "current_model_missing",
    "branch_current_unknown",
    "component_role_unknown",
    "source_sink_not_resolved",
    "relationship_direction_unknown",
}
MANIFEST_BLOCKS = {
    "current_allocation",
    "calculation_readiness",
    "copper_calculation",
    "voltage_drop_calculation",
    "thermal_calculation",
    "fuse_margin",
    "connector_pin_current_margin",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def default_path(template: str, project: str) -> str:
    return template.format(project=project)


def safe_id(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return text or "unknown"


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def number_or_none(value: Any) -> float | None:
    if is_number(value):
        return float(value)
    return None


def source_artifact(artifact_type: str, path: Path | None, record_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "path": str(path) if path else None,
        "record_id": record_id,
        "notes": notes,
    }


def value_unit(value: float | None, unit: str, source: str | None = None, confidence: float | None = None, evidence_refs: list[str] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"value": value, "unit": unit}
    if source is not None:
        row["source"] = source
    if confidence is not None:
        row["confidence"] = confidence
    if evidence_refs is not None:
        row["evidence_refs"] = evidence_refs
    return row


def missing_input(field: str, reason: str, required_for: list[str], manifest_item: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "field": field,
        "reason": reason,
        "required_for": required_for,
        "manifest_item_id": manifest_item_id(manifest_item),
        "recommended_resolution": manifest_item.get("resolution_path") if isinstance(manifest_item, dict) and manifest_item.get("resolution_path") in {
            "deterministic_rule",
            "datasheet_extraction",
            "ai_rule_packet",
            "human_review",
            "not_required",
        } else "deterministic_rule",
    }


def item_values(item: dict[str, Any]) -> set[str]:
    values = {
        str(item.get("target_id") or ""),
        str(item.get("normalized_target") or ""),
        str(item.get("refdes") or ""),
        str(item.get("pin") or ""),
        str(item.get("rail_name") or ""),
        str(item.get("branch_id") or ""),
    }
    for key in ("affected_rails", "affected_branches", "affected_components", "blocks"):
        values.update(str(value) for value in as_list(item.get(key)) if value not in (None, ""))
    return {value for value in values if value}


def manifest_item_id(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get("manifest_id") or item.get("id") or item.get("source_missing_data_id")
    return str(value) if value not in (None, "") else None


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(manifest.get("manifest_items")) if isinstance(row, dict)]


def manifest_matches(
    manifest: dict[str, Any],
    *,
    refdes: str | None = None,
    pin: str | None = None,
    branch_id: str | None = None,
    rail_name: str | None = None,
    categories: set[str] | None = None,
    blocks: set[str] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in manifest_items(manifest):
        category = str(item.get("category") or "")
        if categories is not None and category not in categories:
            continue
        item_blocks = {str(value) for value in as_list(item.get("blocks"))}
        if blocks is not None and item_blocks.isdisjoint(blocks):
            continue
        values = item_values(item)
        identity_match = (
            (refdes is not None and refdes in values)
            or (branch_id is not None and branch_id in values)
            or (rail_name is not None and rail_name in values)
        )
        pin_match = pin is not None and str(item.get("pin") or "") == pin
        if identity_match and (pin is None or not item.get("pin") or pin_match):
            matches.append(item)
    deduped = {manifest_item_id(item): item for item in matches if manifest_item_id(item)}
    return [deduped[key] for key in sorted(deduped)]


def linkage(items: list[dict[str, Any]], manifest_path: Path | None) -> dict[str, Any]:
    ids = sorted({str(manifest_item_id(item)) for item in items if manifest_item_id(item)})
    groups = sorted({str(item.get("group_id")) for item in items if isinstance(item.get("group_id"), str)})
    categories = sorted({str(item.get("category")) for item in items if isinstance(item.get("category"), str)})
    calculations = sorted({str(block) for item in items for block in as_list(item.get("blocks")) if isinstance(block, str)})
    paths = sorted({str(item.get("resolution_path")) for item in items if isinstance(item.get("resolution_path"), str)})
    queues = sorted({str(item.get("resolution_queue") or item.get("resolution_path")) for item in items if isinstance(item.get("resolution_queue") or item.get("resolution_path"), str)})
    row: dict[str, Any] = {
        "blocked_by_manifest_items": ids,
        "missing_data_manifest_item_ids": ids,
        "missing_data_group_ids": groups,
        "blocked_by_categories": categories,
        "blocked_by_calculations": calculations,
        "resolution_path": paths[0] if paths else None,
        "resolution_queue": queues[0] if queues else None,
    }
    if manifest_path is not None:
        row["missing_data_manifest_ref"] = str(manifest_path)
    return row


def merge_linkages(*rows: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [row for row in rows if isinstance(row, dict)]
    if not present:
        return None
    merged: dict[str, Any] = {}
    for key in ("blocked_by_manifest_items", "missing_data_manifest_item_ids", "missing_data_group_ids", "blocked_by_categories", "blocked_by_calculations"):
        merged[key] = sorted({str(value) for row in present for value in as_list(row.get(key)) if isinstance(value, str)})
    for key in ("missing_data_manifest_ref", "resolution_path", "resolution_queue"):
        values = sorted({str(row.get(key)) for row in present if isinstance(row.get(key), str)})
        if values:
            merged[key] = values[0]
    return merged


def result_record(
    *,
    project: str,
    calculation_family: str,
    target_type: str,
    target_id: str,
    status: str,
    result: dict[str, Any],
    intermediate_values: dict[str, Any],
    input_refs: list[str],
    source_artifacts: list[dict[str, Any]],
    evidence_refs: list[str],
    missing_inputs: list[dict[str, Any]],
    linkage_row: dict[str, Any] | None = None,
    branch_id: str | None = None,
    refdes: str | None = None,
    pin: str | None = None,
    warnings: list[str] | None = None,
    confidence: float = 0.8,
    human_review_needed: bool = False,
) -> dict[str, Any]:
    calculation_id = f"calc_{safe_id(calculation_family)}_{safe_id(target_id)}_{safe_id(branch_id)}"
    row = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project,
        "calculation_run_id": f"run_{safe_id(project)}_topology_margin_calculations",
        "calculation_id": calculation_id,
        "calculation_family": calculation_family,
        "target_type": target_type,
        "target_id": target_id,
        "status": status,
        "result": result,
        "intermediate_values": intermediate_values,
        "input_refs": input_refs,
        "source_artifacts": source_artifacts,
        "evidence_refs": sorted(set(evidence_refs)),
        "assumptions": [],
        "missing_inputs": missing_inputs,
        "blocked_by_manifest_items": [],
        "warnings": sorted(set(warnings or [])),
        "errors": [],
        "confidence": confidence,
        "human_review_needed": human_review_needed,
    }
    if branch_id:
        row["branch_id"] = branch_id
    if refdes:
        row["refdes"] = refdes
    if pin:
        row["pin"] = pin
    if linkage_row:
        row.update(linkage_row)
    return row


def allocation_records(current_allocation: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(current_allocation.get("allocation_records")) if isinstance(row, dict)]


def usable_allocation(row: dict[str, Any]) -> bool:
    return (
        row.get("allocation_type") in ALLOCATION_TYPES
        and row.get("usable_for_calculation") is True
        and isinstance(row.get("branch_id"), str)
        and is_number(row.get("allocated_current_a"))
    )


def allocation_index(current_allocation: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    usable_by_branch: dict[str, list[dict[str, Any]]] = {}
    for row in allocation_records(current_allocation):
        if usable_allocation(row):
            usable_by_branch.setdefault(str(row["branch_id"]), []).append(row)
    chosen: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    for branch_id, rows in usable_by_branch.items():
        rows = sorted(rows, key=lambda row: str(row.get("allocation_id") or ""))
        values = {float(row["allocated_current_a"]) for row in rows}
        if len(rows) == 1 or len(values) == 1:
            chosen[branch_id] = rows[0]
        else:
            conflicts[branch_id] = rows
    return chosen, conflicts


def branch_rows(branch_topology: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("branches", "branch_records", "branch_topology", "records"):
        rows = branch_topology.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def strings_from(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, str) and value:
        values.add(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                values.add(item)
            elif isinstance(item, dict) and isinstance(item.get("refdes"), str):
                values.add(item["refdes"])
    return values


def branch_refdeses(row: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("refdes", "component_refdes", "pass_through_refdes", "fuse_refdes", "connector_refdes"):
        refs.update(strings_from(row.get(key)))
    for key in ("refdeses", "component_refdeses", "components", "affected_components", "pass_through_refdeses", "fuse_refdeses", "connector_refdeses"):
        refs.update(strings_from(row.get(key)))
    return refs


def branch_pins(row: dict[str, Any]) -> set[str]:
    pins: set[str] = set()
    for key in ("pin", "connector_pin"):
        value = row.get(key)
        if isinstance(value, str) and value:
            pins.add(value)
    for key in ("pins", "connector_pins"):
        for value in as_list(row.get(key)):
            if isinstance(value, str) and value:
                pins.add(value)
            elif isinstance(value, dict):
                for pin_key in ("pin", "pin_number", "connector_pin"):
                    if isinstance(value.get(pin_key), str) and value.get(pin_key):
                        pins.add(str(value[pin_key]))
    return pins


def branch_ids_for_refdes(branch_topology: dict[str, Any], refdes: str) -> list[str]:
    ids = {
        str(row.get("branch_id"))
        for row in branch_rows(branch_topology)
        if isinstance(row.get("branch_id"), str) and refdes in branch_refdeses(row)
    }
    return sorted(ids)


def branch_ids_for_refdes_pin(branch_topology: dict[str, Any], refdes: str, pin: str) -> list[str]:
    ids = {
        str(row.get("branch_id"))
        for row in branch_rows(branch_topology)
        if isinstance(row.get("branch_id"), str) and refdes in branch_refdeses(row) and pin in branch_pins(row)
    }
    return sorted(ids)


def component_roles(role_resolution: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(role_resolution.get("component_roles")) if isinstance(row, dict)]


def role_rows_for_refdes(role_resolution: dict[str, Any], refdes: str | None) -> list[dict[str, Any]]:
    if not refdes:
        return []
    return [row for row in component_roles(role_resolution) if row.get("refdes") == refdes]


def role_confirms_fuse(role_resolution: dict[str, Any], refdes: str | None) -> bool:
    rows = role_rows_for_refdes(role_resolution, refdes)
    if not rows:
        return False
    for row in rows:
        role = str(row.get("role") or "").lower()
        subtype = str(row.get("role_subtype") or row.get("component_role") or row.get("component_type") or "").lower()
        if "fuse" in subtype or (role == "pass_through" and subtype in {"fuse", "polyfuse", "resettable_fuse"}):
            return True
    return False


def role_confirms_connector(role_resolution: dict[str, Any], refdes: str | None) -> bool:
    rows = role_rows_for_refdes(role_resolution, refdes)
    if not rows:
        return False
    for row in rows:
        subtype = str(row.get("role_subtype") or row.get("component_role") or row.get("component_type") or "").lower()
        if "connector" in subtype:
            return True
    return False


def role_branch_ids(role_resolution: dict[str, Any], refdes: str | None) -> list[str]:
    ids: set[str] = set()
    for row in role_rows_for_refdes(role_resolution, refdes):
        for key in ("branch_id", "current_path_branch_id"):
            if isinstance(row.get(key), str):
                ids.add(row[key])
        for key in ("branch_ids", "input_branch_ids", "output_branch_ids", "current_path_branch_ids"):
            ids.update(str(value) for value in as_list(row.get(key)) if isinstance(value, str))
    return sorted(ids)


def role_branch_ids_for_pin(role_resolution: dict[str, Any], refdes: str | None, pin: str | None) -> list[str]:
    if not pin:
        return role_branch_ids(role_resolution, refdes)
    ids: set[str] = set()
    for row in role_rows_for_refdes(role_resolution, refdes):
        for key in ("pin_branch_map", "connector_pin_branch_map", "pin_to_branch"):
            mapping = row.get(key)
            if isinstance(mapping, dict) and isinstance(mapping.get(pin), str):
                ids.add(mapping[pin])
        for item in as_list(row.get("pin_branches")):
            if isinstance(item, dict) and str(item.get("pin") or "") == pin and isinstance(item.get("branch_id"), str):
                ids.add(item["branch_id"])
    return sorted(ids) or role_branch_ids(role_resolution, refdes)


def target_id_for_rating(rating: dict[str, Any], branch_id: str | None = None) -> str:
    refdes = rating.get("refdes")
    pin = rating.get("pin")
    if isinstance(refdes, str) and isinstance(pin, str):
        return f"{refdes}:{pin}"
    if isinstance(refdes, str):
        return refdes
    if isinstance(rating.get("branch_id"), str):
        return str(rating["branch_id"])
    return branch_id or str(rating.get("rating_id") or "unknown")


def fuse_result_target_type(rating: dict[str, Any]) -> str:
    return "fuse_pin" if isinstance(rating.get("pin"), str) or rating.get("normalized_target_type") == "fuse_pin" else "fuse"


def connector_result_target_type(rating: dict[str, Any]) -> str:
    return "connector_pin" if isinstance(rating.get("pin"), str) or rating.get("normalized_target_type") == "connector_pin" else "connector"


def rating_fuse_relevant(rating: dict[str, Any]) -> bool:
    target_type = rating.get("normalized_target_type")
    families = {str(value) for value in as_list(rating.get("applies_to_calculation_families"))}
    return target_type in FUSE_ROLE_TARGET_TYPES or "fuse_margin" in families or rating.get("normalized_rating_name") == "trip_current"


def rating_connector_relevant(rating: dict[str, Any]) -> bool:
    target_type = rating.get("normalized_target_type")
    families = {str(value) for value in as_list(rating.get("applies_to_calculation_families"))}
    return target_type in CONNECTOR_TARGET_TYPES or "connector_pin_current_margin" in families


def rating_usable_for_pr24(rating: dict[str, Any], role_resolution: dict[str, Any]) -> tuple[bool, str | None]:
    target_type = rating.get("normalized_target_type")
    if target_type == "pass_through_component" and not role_confirms_fuse(role_resolution, rating.get("refdes")):
        return False, "target_role_unknown"
    if target_type not in FUSE_ROLE_TARGET_TYPES:
        return False, "target_role_unknown"
    if rating.get("usable_for_margin_calculation") is not True:
        return False, "rating_unusable"
    return True, None


def rating_scope(rating: dict[str, Any]) -> str | None:
    scope = rating.get("rating_scope")
    if isinstance(scope, str) and scope:
        return scope
    for key in ("is_per_pin", "per_pin", "applies_to_all_pins", "connector_wide"):
        if rating.get(key) is True:
            return "per_pin" if key in {"is_per_pin", "per_pin"} else "connector"
    return None


def connector_rating_is_global(rating: dict[str, Any]) -> bool:
    scope = str(rating_scope(rating) or "").lower()
    return scope in {"pin", "per_pin", "connector", "global"} or any(rating.get(key) is True for key in ("is_per_pin", "per_pin", "applies_to_all_pins", "connector_wide"))


def rating_usable_for_pr25_connector(rating: dict[str, Any], role_resolution: dict[str, Any]) -> tuple[bool, str | None]:
    target_type = rating.get("normalized_target_type")
    if target_type == "component" and not role_confirms_connector(role_resolution, rating.get("refdes")):
        return False, "target_role_unknown"
    if target_type not in CONNECTOR_ROLE_TARGET_TYPES:
        return False, "target_role_unknown"
    if rating.get("usable_for_margin_calculation") is not True:
        return False, "rating_unusable"
    return True, None


def candidate_branches_for_rating(rating: dict[str, Any], role_resolution: dict[str, Any], branch_topology: dict[str, Any]) -> tuple[list[str], str, bool]:
    if isinstance(rating.get("branch_id"), str):
        return [str(rating["branch_id"])], "rating_branch_id", False
    refdes = rating.get("refdes") if isinstance(rating.get("refdes"), str) else None
    if refdes:
        branch_ids = branch_ids_for_refdes(branch_topology, refdes)
        if branch_ids:
            return branch_ids, "branch_topology_enriched", len(branch_ids) > 1
        role_ids = role_branch_ids(role_resolution, refdes)
        if role_ids:
            return role_ids, "topology_role_resolution", len(role_ids) > 1
    return [], "unresolved", False


def candidate_branches_for_connector_rating(rating: dict[str, Any], role_resolution: dict[str, Any], branch_topology: dict[str, Any]) -> tuple[list[str], str, bool]:
    if isinstance(rating.get("branch_id"), str):
        return [str(rating["branch_id"])], "rating_branch_id", False
    refdes = rating.get("refdes") if isinstance(rating.get("refdes"), str) else None
    pin = rating.get("pin") if isinstance(rating.get("pin"), str) else None
    if refdes and pin:
        branch_ids = branch_ids_for_refdes_pin(branch_topology, refdes, pin)
        if branch_ids:
            return branch_ids, "branch_topology_enriched", len(branch_ids) > 1
        role_ids = role_branch_ids_for_pin(role_resolution, refdes, pin)
        if role_ids:
            return role_ids, "topology_role_resolution", len(role_ids) > 1
    if refdes and connector_rating_is_global(rating):
        branch_ids = branch_ids_for_refdes(branch_topology, refdes)
        if branch_ids:
            return branch_ids, "branch_topology_enriched", len(branch_ids) > 1
        role_ids = role_branch_ids(role_resolution, refdes)
        if role_ids:
            return role_ids, "topology_role_resolution", len(role_ids) > 1
    return [], "unresolved", False


def evidence_refs(*rows: dict[str, Any] | None) -> list[str]:
    refs: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            refs.update(str(value) for value in as_list(row.get("evidence_refs")) if isinstance(value, str))
    return sorted(refs)


def confidence(*rows: dict[str, Any] | None) -> float:
    values = [float(row["confidence"]) for row in rows if isinstance(row, dict) and is_number(row.get("confidence"))]
    return min(values) if values else 0.8


def human_review_needed(*rows: dict[str, Any] | None) -> bool:
    return any(isinstance(row, dict) and row.get("human_review_needed") is True for row in rows)


def rating_linkage(rating: dict[str, Any], manifest_path: Path | None = None) -> dict[str, Any]:
    row = {
        "blocked_by_manifest_items": [str(value) for value in as_list(rating.get("missing_data_manifest_item_ids")) if isinstance(value, str)],
        "missing_data_manifest_item_ids": [str(value) for value in as_list(rating.get("missing_data_manifest_item_ids")) if isinstance(value, str)],
        "missing_data_group_ids": [str(value) for value in as_list(rating.get("missing_data_group_ids")) if isinstance(value, str)],
        "blocked_by_categories": [],
        "blocked_by_calculations": [],
        "resolution_path": rating.get("resolution_path") if isinstance(rating.get("resolution_path"), str) else None,
        "resolution_queue": rating.get("resolution_queue") if isinstance(rating.get("resolution_queue"), str) else None,
    }
    if manifest_path is not None:
        row["missing_data_manifest_ref"] = str(manifest_path)
    return row


def allocation_linkage(allocation: dict[str, Any], manifest_path: Path | None = None) -> dict[str, Any]:
    row = {
        "blocked_by_manifest_items": [str(value) for value in as_list(allocation.get("missing_data_manifest_item_ids")) if isinstance(value, str)],
        "missing_data_manifest_item_ids": [str(value) for value in as_list(allocation.get("missing_data_manifest_item_ids")) if isinstance(value, str)],
        "missing_data_group_ids": [str(value) for value in as_list(allocation.get("missing_data_group_ids")) if isinstance(value, str)],
        "blocked_by_categories": [str(value) for value in as_list(allocation.get("blocked_by_categories")) if isinstance(value, str)],
        "blocked_by_calculations": [str(value) for value in as_list(allocation.get("blocked_by_calculations")) if isinstance(value, str)],
        "resolution_path": allocation.get("resolution_path") if isinstance(allocation.get("resolution_path"), str) else None,
        "resolution_queue": allocation.get("resolution_queue") if isinstance(allocation.get("resolution_queue"), str) else None,
    }
    if manifest_path is not None:
        row["missing_data_manifest_ref"] = str(manifest_path)
    return row


def unresolved_input(
    *,
    reason_code: str,
    detail: str,
    rating: dict[str, Any] | None = None,
    allocation: dict[str, Any] | None = None,
    branch_id: str | None = None,
    manifest_linkage: dict[str, Any] | None = None,
    missing_inputs: list[dict[str, Any]] | None = None,
    source_artifacts: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    rating_ids = [str(rating.get("rating_id"))] if isinstance(rating, dict) and isinstance(rating.get("rating_id"), str) else []
    allocation_ids = [str(allocation.get("allocation_id"))] if isinstance(allocation, dict) and isinstance(allocation.get("allocation_id"), str) else []
    link = manifest_linkage or {}
    return {
        "unresolved_id": f"unresolved_margin_{safe_id(reason_code)}_{safe_id(rating_ids[0] if rating_ids else branch_id)}",
        "reason_code": reason_code,
        "refdes": rating.get("refdes") if isinstance(rating, dict) else None,
        "pin": rating.get("pin") if isinstance(rating, dict) else None,
        "branch_id": branch_id or (allocation.get("branch_id") if isinstance(allocation, dict) else None),
        "rail_name": rating.get("rail_name") if isinstance(rating, dict) else allocation.get("rail_name") if isinstance(allocation, dict) else None,
        "allocation_ids": allocation_ids,
        "rating_ids": rating_ids,
        "missing_inputs": missing_inputs or [],
        "missing_data_manifest_item_ids": [str(value) for value in as_list(link.get("missing_data_manifest_item_ids")) if isinstance(value, str)],
        "missing_data_group_ids": [str(value) for value in as_list(link.get("missing_data_group_ids")) if isinstance(value, str)],
        "resolution_path": link.get("resolution_path"),
        "resolution_queue": link.get("resolution_queue"),
        "human_review_needed": True,
        "detail": detail,
        "source_artifacts": source_artifacts or [],
        "evidence_refs": evidence_refs(rating, allocation),
        "warnings": warnings or [],
    }


def result_sources(paths: dict[str, Path | None], allocation: dict[str, Any] | None, rating: dict[str, Any] | None, link_method: str | None = None) -> list[dict[str, Any]]:
    sources = [
        source_artifact("topology_current_allocation", paths["current_allocation"], allocation.get("allocation_id") if isinstance(allocation, dict) else None, "PR20 allocated branch current."),
        source_artifact("rating_models_normalized", paths["rating_models"], rating.get("rating_id") if isinstance(rating, dict) else None, "PR23 normalized rating record."),
    ]
    if link_method == "branch_topology_enriched":
        sources.append(source_artifact("branch_topology_enriched", paths.get("branch_topology"), None, "Deterministic rating-to-branch linkage."))
    elif link_method == "topology_role_resolution":
        sources.append(source_artifact("topology_role_resolution", paths.get("role_resolution"), None, "Deterministic fuse role/path linkage."))
    return sources


def blocked_result(
    *,
    project: str,
    rating: dict[str, Any] | None,
    allocation: dict[str, Any] | None,
    branch_id: str | None,
    missing: list[dict[str, Any]],
    paths: dict[str, Path | None],
    linkage_row: dict[str, Any] | None,
    link_method: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    target_id = target_id_for_rating(rating or {}, branch_id)
    return result_record(
        project=project,
        calculation_family="fuse_margin",
        target_type=fuse_result_target_type(rating or {}) if rating else "fuse",
        target_id=target_id,
        branch_id=branch_id,
        refdes=rating.get("refdes") if isinstance(rating, dict) and isinstance(rating.get("refdes"), str) else None,
        pin=rating.get("pin") if isinstance(rating, dict) and isinstance(rating.get("pin"), str) else None,
        status="blocked",
        result={"fuse_margin_a": None, "fuse_utilization_ratio": None},
        intermediate_values={
            "allocated_current_a": value_unit(number_or_none(allocation.get("allocated_current_a")) if isinstance(allocation, dict) else None, "A"),
            "rating_current_a": value_unit(number_or_none(rating.get("value_a")) if isinstance(rating, dict) else None, "A"),
            "rating_name": rating.get("normalized_rating_name") if isinstance(rating, dict) else None,
        },
        input_refs=([str(allocation.get("allocation_id"))] if isinstance(allocation, dict) and isinstance(allocation.get("allocation_id"), str) else [])
        + ([str(rating.get("rating_id"))] if isinstance(rating, dict) and isinstance(rating.get("rating_id"), str) else []),
        source_artifacts=result_sources(paths, allocation, rating, link_method),
        evidence_refs=evidence_refs(rating, allocation),
        missing_inputs=missing,
        linkage_row=linkage_row,
        warnings=warnings,
        confidence=confidence(rating, allocation),
        human_review_needed=True,
    )


def connector_blocked_result(
    *,
    project: str,
    rating: dict[str, Any] | None,
    allocation: dict[str, Any] | None,
    branch_id: str | None,
    missing: list[dict[str, Any]],
    paths: dict[str, Path | None],
    linkage_row: dict[str, Any] | None,
    link_method: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    target_id = target_id_for_rating(rating or {}, branch_id)
    return result_record(
        project=project,
        calculation_family="connector_pin_current_margin",
        target_type=connector_result_target_type(rating or {}) if rating else "connector_pin",
        target_id=target_id,
        branch_id=branch_id,
        refdes=rating.get("refdes") if isinstance(rating, dict) and isinstance(rating.get("refdes"), str) else None,
        pin=rating.get("pin") if isinstance(rating, dict) and isinstance(rating.get("pin"), str) else None,
        status="blocked",
        result={"connector_pin_margin_a": None, "connector_pin_utilization_ratio": None},
        intermediate_values={
            "allocated_current_a": value_unit(number_or_none(allocation.get("allocated_current_a")) if isinstance(allocation, dict) else None, "A"),
            "rating_current_a": value_unit(number_or_none(rating.get("value_a")) if isinstance(rating, dict) else None, "A"),
            "rating_name": rating.get("normalized_rating_name") if isinstance(rating, dict) else None,
            "rating_scope": rating_scope(rating) if isinstance(rating, dict) else None,
        },
        input_refs=([str(allocation.get("allocation_id"))] if isinstance(allocation, dict) and isinstance(allocation.get("allocation_id"), str) else [])
        + ([str(rating.get("rating_id"))] if isinstance(rating, dict) and isinstance(rating.get("rating_id"), str) else []),
        source_artifacts=result_sources(paths, allocation, rating, link_method),
        evidence_refs=evidence_refs(rating, allocation),
        missing_inputs=missing,
        linkage_row=linkage_row,
        warnings=warnings,
        confidence=confidence(rating, allocation),
        human_review_needed=True,
    )


def calculate_result(
    *,
    project: str,
    rating: dict[str, Any],
    allocation: dict[str, Any],
    branch_id: str,
    paths: dict[str, Path | None],
    linkage_row: dict[str, Any] | None,
    link_method: str,
) -> dict[str, Any]:
    current_a = float(allocation["allocated_current_a"])
    rating_a = float(rating["value_a"])
    margin_a = rating_a - current_a
    utilization = current_a / rating_a
    target_id = target_id_for_rating(rating, branch_id)
    return result_record(
        project=project,
        calculation_family="fuse_margin",
        target_type=fuse_result_target_type(rating),
        target_id=target_id,
        branch_id=branch_id,
        refdes=rating.get("refdes") if isinstance(rating.get("refdes"), str) else None,
        pin=rating.get("pin") if isinstance(rating.get("pin"), str) else None,
        status="calculated",
        result={
            "fuse_margin_a": value_unit(margin_a, "A", "standard_formula", confidence(rating, allocation), evidence_refs(rating, allocation)),
            "fuse_utilization_ratio": value_unit(utilization, "ratio", "standard_formula", confidence(rating, allocation), evidence_refs(rating, allocation)),
        },
        intermediate_values={
            "allocated_current_a": value_unit(current_a, "A"),
            "rating_current_a": value_unit(rating_a, "A"),
            "rating_name": rating.get("normalized_rating_name"),
        },
        input_refs=[str(allocation.get("allocation_id")), str(rating.get("rating_id"))],
        source_artifacts=result_sources(paths, allocation, rating, link_method),
        evidence_refs=evidence_refs(rating, allocation),
        missing_inputs=[],
        linkage_row=linkage_row,
        confidence=confidence(rating, allocation),
        human_review_needed=human_review_needed(rating, allocation),
    )


def calculate_connector_result(
    *,
    project: str,
    rating: dict[str, Any],
    allocation: dict[str, Any],
    branch_id: str,
    paths: dict[str, Path | None],
    linkage_row: dict[str, Any] | None,
    link_method: str,
) -> dict[str, Any]:
    current_a = float(allocation["allocated_current_a"])
    rating_a = float(rating["value_a"])
    margin_a = rating_a - current_a
    utilization = current_a / rating_a
    target_id = target_id_for_rating(rating, branch_id)
    return result_record(
        project=project,
        calculation_family="connector_pin_current_margin",
        target_type=connector_result_target_type(rating),
        target_id=target_id,
        branch_id=branch_id,
        refdes=rating.get("refdes") if isinstance(rating.get("refdes"), str) else None,
        pin=rating.get("pin") if isinstance(rating.get("pin"), str) else None,
        status="calculated",
        result={
            "connector_pin_margin_a": value_unit(margin_a, "A", "standard_formula", confidence(rating, allocation), evidence_refs(rating, allocation)),
            "connector_pin_utilization_ratio": value_unit(utilization, "ratio", "standard_formula", confidence(rating, allocation), evidence_refs(rating, allocation)),
        },
        intermediate_values={
            "allocated_current_a": value_unit(current_a, "A"),
            "rating_current_a": value_unit(rating_a, "A"),
            "rating_name": rating.get("normalized_rating_name"),
            "rating_scope": rating_scope(rating),
        },
        input_refs=[str(allocation.get("allocation_id")), str(rating.get("rating_id"))],
        source_artifacts=result_sources(paths, allocation, rating, link_method),
        evidence_refs=evidence_refs(rating, allocation),
        missing_inputs=[],
        linkage_row=linkage_row,
        confidence=confidence(rating, allocation),
        human_review_needed=human_review_needed(rating, allocation),
    )


def source_artifacts_for(paths: dict[str, Path | None]) -> list[dict[str, Any]]:
    artifacts = [
        source_artifact("topology_current_allocation", paths["current_allocation"], None, "PR20 topology current allocation artifact."),
        source_artifact("rating_models_normalized", paths["rating_models"], None, "PR23 normalized rating artifact."),
    ]
    optional = (
        ("missing_data_manifest", "missing_data_manifest", "Optional PR16 blocker context."),
        ("role_resolution", "topology_role_resolution", "Optional role context for fuse confirmation."),
        ("branch_topology", "branch_topology_enriched", "Optional branch context for deterministic linkage."),
        ("rail_relationships", "rail_relationships", "Optional rail relationship context."),
    )
    for key, artifact_type, notes in optional:
        if paths.get(key):
            artifacts.append(source_artifact(artifact_type, paths[key], None, notes))
    return artifacts


def eligible_fuse_branches(branch_topology: dict[str, Any], role_resolution: dict[str, Any], manifest: dict[str, Any]) -> set[str]:
    eligible: set[str] = set()
    for row in branch_rows(branch_topology):
        branch_id = row.get("branch_id")
        if not isinstance(branch_id, str):
            continue
        refs = branch_refdeses(row)
        if any(role_confirms_fuse(role_resolution, refdes) for refdes in refs):
            eligible.add(branch_id)
        text = " ".join(str(row.get(key) or "").lower() for key in ("target_type", "branch_type", "role_subtype", "component_role"))
        if "fuse" in text:
            eligible.add(branch_id)
    for item in manifest_items(manifest):
        if item.get("category") == "rating_missing":
            eligible.update(str(value) for value in as_list(item.get("affected_branches")) if isinstance(value, str))
    return eligible


def eligible_connector_branches(branch_topology: dict[str, Any], role_resolution: dict[str, Any], manifest: dict[str, Any]) -> set[str]:
    eligible: set[str] = set()
    for row in branch_rows(branch_topology):
        branch_id = row.get("branch_id")
        if not isinstance(branch_id, str):
            continue
        refs = branch_refdeses(row)
        if any(role_confirms_connector(role_resolution, refdes) for refdes in refs):
            eligible.add(branch_id)
        text = " ".join(str(row.get(key) or "").lower() for key in ("target_type", "branch_type", "role_subtype", "component_role"))
        if "connector" in text:
            eligible.add(branch_id)
    for item in manifest_items(manifest):
        if item.get("category") == "rating_missing":
            values = " ".join(item_values(item)).lower()
            if "connector" in values:
                eligible.update(str(value) for value in as_list(item.get("affected_branches")) if isinstance(value, str))
    return eligible


def build_artifact(
    *,
    project: str,
    paths: dict[str, Path | None],
    current_allocation: dict[str, Any],
    rating_models: dict[str, Any],
    manifest: dict[str, Any],
    role_resolution: dict[str, Any],
    branch_topology: dict[str, Any],
    rail_relationships: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    del rail_relationships
    allocation_by_branch, allocation_conflicts = allocation_index(current_allocation)
    normalized_ratings = [row for row in as_list(rating_models.get("normalized_ratings")) if isinstance(row, dict)]
    fuse_ratings = [row for row in normalized_ratings if rating_fuse_relevant(row)]
    connector_ratings = [row for row in normalized_ratings if rating_connector_relevant(row)]
    calculation_results: list[dict[str, Any]] = []
    unresolved_inputs: list[dict[str, Any]] = []
    consumed_branches: set[str] = set()
    consumed_connector_branches: set[str] = set()

    for rating in sorted(fuse_ratings, key=lambda row: str(row.get("rating_id") or "")):
        refdes = rating.get("refdes") if isinstance(rating.get("refdes"), str) else None
        pin = rating.get("pin") if isinstance(rating.get("pin"), str) else None
        rating_matches = manifest_matches(manifest, refdes=refdes, pin=pin, branch_id=rating.get("branch_id") if isinstance(rating.get("branch_id"), str) else None, categories=MANIFEST_CATEGORIES, blocks=None)
        rating_link = merge_linkages(rating_linkage(rating, paths.get("missing_data_manifest")), linkage(rating_matches, paths.get("missing_data_manifest")) if rating_matches else None)

        usable, unusable_reason = rating_usable_for_pr24(rating, role_resolution)
        branch_ids, link_method, ambiguous = candidate_branches_for_rating(rating, role_resolution, branch_topology)
        if ambiguous:
            unresolved_inputs.append(unresolved_input(
                reason_code="ambiguous_target_mapping",
                detail="rating target maps to multiple candidate branches",
                rating=rating,
                manifest_linkage=rating_link,
                missing_inputs=[missing_input("target_current_link", "Rating target maps to multiple candidate branches.", ["fuse_margin"], rating_matches[0] if rating_matches else None)],
                source_artifacts=result_sources(paths, None, rating, link_method),
            ))
            continue
        if not branch_ids:
            reason = "target_role_unknown" if unusable_reason == "target_role_unknown" else "target_current_link_unknown"
            unresolved_inputs.append(unresolved_input(
                reason_code=reason,
                detail="rating target cannot be linked to exactly one allocated branch",
                rating=rating,
                manifest_linkage=rating_link,
                missing_inputs=[missing_input("target_current_link", "A deterministic rating-to-current branch link is required.", ["fuse_margin"], rating_matches[0] if rating_matches else None)],
                source_artifacts=result_sources(paths, None, rating, link_method),
            ))
            continue

        branch_id = branch_ids[0]
        consumed_branches.add(branch_id)
        allocation = allocation_by_branch.get(branch_id)
        allocation_conflict_rows = allocation_conflicts.get(branch_id, [])
        allocation_matches = manifest_matches(manifest, refdes=refdes, pin=pin, branch_id=branch_id, categories=MANIFEST_CATEGORIES, blocks=MANIFEST_BLOCKS)
        combined_link = merge_linkages(
            rating_link,
            linkage(allocation_matches, paths.get("missing_data_manifest")) if allocation_matches else None,
            allocation_linkage(allocation, paths.get("missing_data_manifest")) if allocation else None,
        )

        missing: list[dict[str, Any]] = []
        block_warnings: list[str] = []
        rating_name = rating.get("normalized_rating_name")
        rating_value = number_or_none(rating.get("value_a"))
        if not usable:
            missing.append(missing_input("fuse_rating", f"rating is not usable for PR24 fuse margin: {unusable_reason}", ["fuse_margin"], rating_matches[0] if rating_matches else None))
        if rating_name == "trip_current":
            missing.append(missing_input("rating_name", "trip_current is not a continuous-current margin basis in PR24.", ["fuse_margin"], rating_matches[0] if rating_matches else None))
            block_warnings.append("trip_current_not_continuous_margin_basis")
        elif rating_name not in FUSE_MARGIN_RATING_NAMES:
            missing.append(missing_input("rating_name", "rating name is not supported for PR24 fuse margin.", ["fuse_margin"], rating_matches[0] if rating_matches else None))
            block_warnings.append("unsupported_fuse_margin_rating_name")
        if rating_value is None or rating_value <= 0:
            missing.append(missing_input("rating_current_a", "fuse rating current must be explicit and positive.", ["fuse_margin"], rating_matches[0] if rating_matches else None))
        if allocation_conflict_rows:
            missing.append(missing_input("allocated_current_a", "current allocation records conflict for this branch.", ["fuse_margin"], allocation_matches[0] if allocation_matches else None))
            block_warnings.append("current_source_conflict")
        elif allocation is None:
            missing.append(missing_input("allocated_current_a", "usable allocated branch current is missing.", ["fuse_margin"], allocation_matches[0] if allocation_matches else None))
        if missing:
            calculation_results.append(blocked_result(
                project=project,
                rating=rating,
                allocation=allocation,
                branch_id=branch_id,
                missing=missing,
                paths=paths,
                linkage_row=combined_link,
                link_method=link_method,
                warnings=block_warnings,
            ))
            continue

        assert allocation is not None
        calculation_results.append(calculate_result(
            project=project,
            rating=rating,
            allocation=allocation,
            branch_id=branch_id,
            paths=paths,
            linkage_row=combined_link,
            link_method=link_method,
        ))

    for rating in sorted(connector_ratings, key=lambda row: str(row.get("rating_id") or "")):
        refdes = rating.get("refdes") if isinstance(rating.get("refdes"), str) else None
        pin = rating.get("pin") if isinstance(rating.get("pin"), str) else None
        rating_matches = manifest_matches(manifest, refdes=refdes, pin=pin, branch_id=rating.get("branch_id") if isinstance(rating.get("branch_id"), str) else None, categories=MANIFEST_CATEGORIES, blocks=None)
        rating_link = merge_linkages(rating_linkage(rating, paths.get("missing_data_manifest")), linkage(rating_matches, paths.get("missing_data_manifest")) if rating_matches else None)
        usable, unusable_reason = rating_usable_for_pr25_connector(rating, role_resolution)
        branch_ids, link_method, ambiguous = candidate_branches_for_connector_rating(rating, role_resolution, branch_topology)
        pin_missing = pin is None and not connector_rating_is_global(rating)
        if ambiguous:
            unresolved_inputs.append(unresolved_input(
                reason_code="ambiguous_target_mapping",
                detail="connector rating target maps to multiple candidate branches",
                rating=rating,
                manifest_linkage=rating_link,
                missing_inputs=[missing_input("target_current_link", "Connector rating target maps to multiple candidate branches.", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None)],
                source_artifacts=result_sources(paths, None, rating, link_method),
            ))
            continue
        if not branch_ids:
            reason = "missing_connector_pin" if pin_missing else "target_role_unknown" if unusable_reason == "target_role_unknown" else "target_current_link_unknown"
            unresolved_inputs.append(unresolved_input(
                reason_code=reason,
                detail="connector rating target cannot be linked to exactly one allocated branch",
                rating=rating,
                manifest_linkage=rating_link,
                missing_inputs=[missing_input("connector_pin" if pin_missing else "target_current_link", "A deterministic connector-pin rating-to-current branch link is required.", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None)],
                source_artifacts=result_sources(paths, None, rating, link_method),
                warnings=["connector_wide_rating_not_expanded"] if pin_missing else [],
            ))
            continue

        branch_id = branch_ids[0]
        consumed_connector_branches.add(branch_id)
        allocation = allocation_by_branch.get(branch_id)
        allocation_conflict_rows = allocation_conflicts.get(branch_id, [])
        allocation_matches = manifest_matches(manifest, refdes=refdes, pin=pin, branch_id=branch_id, categories=MANIFEST_CATEGORIES, blocks=MANIFEST_BLOCKS)
        combined_link = merge_linkages(
            rating_link,
            linkage(allocation_matches, paths.get("missing_data_manifest")) if allocation_matches else None,
            allocation_linkage(allocation, paths.get("missing_data_manifest")) if allocation else None,
        )
        missing: list[dict[str, Any]] = []
        block_warnings: list[str] = []
        rating_name = rating.get("normalized_rating_name")
        rating_value = number_or_none(rating.get("value_a"))
        if not usable:
            missing.append(missing_input("connector_pin_rating", f"rating is not usable for PR25 connector pin margin: {unusable_reason}", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None))
        if pin_missing:
            missing.append(missing_input("connector_pin", "connector pin is missing and rating is not explicitly per-pin, global, or connector-wide.", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None))
            block_warnings.append("connector_wide_rating_not_expanded")
        if rating_name not in CONNECTOR_MARGIN_RATING_NAMES:
            missing.append(missing_input("rating_name", "rating name is not supported for PR25 connector pin margin.", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None))
            block_warnings.append("unsupported_connector_margin_rating_name")
        if rating_value is None or rating_value <= 0:
            missing.append(missing_input("rating_current_a", "connector pin rating current must be explicit and positive.", ["connector_pin_current_margin"], rating_matches[0] if rating_matches else None))
        if allocation_conflict_rows:
            missing.append(missing_input("allocated_current_a", "current allocation records conflict for this branch.", ["connector_pin_current_margin"], allocation_matches[0] if allocation_matches else None))
            block_warnings.append("current_source_conflict")
        elif allocation is None:
            missing.append(missing_input("allocated_current_a", "usable allocated branch current is missing.", ["connector_pin_current_margin"], allocation_matches[0] if allocation_matches else None))
        if missing:
            calculation_results.append(connector_blocked_result(
                project=project,
                rating=rating,
                allocation=allocation,
                branch_id=branch_id,
                missing=missing,
                paths=paths,
                linkage_row=combined_link,
                link_method=link_method,
                warnings=block_warnings,
            ))
            continue

        assert allocation is not None
        calculation_results.append(calculate_connector_result(
            project=project,
            rating=rating,
            allocation=allocation,
            branch_id=branch_id,
            paths=paths,
            linkage_row=combined_link,
            link_method=link_method,
        ))

    eligible_branches = eligible_fuse_branches(branch_topology, role_resolution, manifest)
    for branch_id in sorted(eligible_branches - consumed_branches):
        allocation = allocation_by_branch.get(branch_id)
        branch_matches = manifest_matches(manifest, branch_id=branch_id, categories=MANIFEST_CATEGORIES, blocks=MANIFEST_BLOCKS)
        link = merge_linkages(
            linkage(branch_matches, paths.get("missing_data_manifest")) if branch_matches else None,
            allocation_linkage(allocation, paths.get("missing_data_manifest")) if allocation else None,
        )
        if allocation is None:
            unresolved_inputs.append(unresolved_input(
                reason_code="missing_allocated_current",
                detail="fuse branch has no usable allocated current",
                allocation=None,
                branch_id=branch_id,
                manifest_linkage=link,
                missing_inputs=[missing_input("allocated_current_a", "usable allocated branch current is missing.", ["fuse_margin"], branch_matches[0] if branch_matches else None)],
                source_artifacts=[source_artifact("topology_current_allocation", paths["current_allocation"], None, "PR20 allocated branch current.")],
            ))
            continue
        calculation_results.append(blocked_result(
            project=project,
            rating=None,
            allocation=allocation,
            branch_id=branch_id,
            missing=[missing_input("fuse_rating", "usable fuse rating is missing.", ["fuse_margin"], branch_matches[0] if branch_matches else None)],
            paths=paths,
            linkage_row=link,
            warnings=["missing_fuse_rating"],
        ))

    eligible_connector = eligible_connector_branches(branch_topology, role_resolution, manifest)
    for branch_id in sorted(eligible_connector - consumed_connector_branches):
        allocation = allocation_by_branch.get(branch_id)
        branch_matches = manifest_matches(manifest, branch_id=branch_id, categories=MANIFEST_CATEGORIES, blocks=MANIFEST_BLOCKS)
        link = merge_linkages(
            linkage(branch_matches, paths.get("missing_data_manifest")) if branch_matches else None,
            allocation_linkage(allocation, paths.get("missing_data_manifest")) if allocation else None,
        )
        if allocation is None:
            unresolved_inputs.append(unresolved_input(
                reason_code="missing_allocated_current",
                detail="connector branch has no usable allocated current",
                allocation=None,
                branch_id=branch_id,
                manifest_linkage=link,
                missing_inputs=[missing_input("allocated_current_a", "usable allocated branch current is missing.", ["connector_pin_current_margin"], branch_matches[0] if branch_matches else None)],
                source_artifacts=[source_artifact("topology_current_allocation", paths["current_allocation"], None, "PR20 allocated branch current.")],
            ))
            continue
        calculation_results.append(connector_blocked_result(
            project=project,
            rating=None,
            allocation=allocation,
            branch_id=branch_id,
            missing=[missing_input("connector_pin_rating", "usable connector pin rating is missing.", ["connector_pin_current_margin"], branch_matches[0] if branch_matches else None)],
            paths=paths,
            linkage_row=link,
            warnings=["missing_connector_pin_rating"],
        ))

    if paths.get("missing_data_manifest") and manifest and not any(item.get("category") == "rating_missing" for item in manifest_items(manifest)):
        warnings.append("missing-data manifest did not contain rating_missing items; missing ratings remain unresolved where applicable")

    blocked = [row for row in calculation_results if row.get("status") == "blocked"]
    fuse_results = [row for row in calculation_results if row.get("calculation_family") == "fuse_margin"]
    connector_results = [row for row in calculation_results if row.get("calculation_family") == "connector_pin_current_margin"]
    fuse_blocked = [row for row in fuse_results if row.get("status") == "blocked"]
    connector_blocked = [row for row in connector_results if row.get("status") == "blocked"]
    connector_unresolved = [
        row for row in unresolved_inputs
        if any("connector" in str(item.get("field") or "") for item in as_list(row.get("missing_inputs")))
        or any(str(value).startswith("rating_connector") for value in as_list(row.get("rating_ids")))
        or "connector" in str(row.get("detail") or "").lower()
    ]
    errors: list[str] = []
    summary = {
        "fuse_margin_result_count": len(fuse_results),
        "fuse_margin_calculated_count": sum(1 for row in fuse_results if row.get("status") == "calculated"),
        "fuse_margin_blocked_count": len(fuse_blocked),
        "unresolved_margin_input_count": len(unresolved_inputs),
        "missing_rating_blocked_count": sum(1 for row in fuse_blocked if any(item.get("field") == "fuse_rating" for item in as_list(row.get("missing_inputs")))),
        "missing_current_blocked_count": sum(1 for row in fuse_blocked if any(item.get("field") == "allocated_current_a" for item in as_list(row.get("missing_inputs")))) + sum(1 for row in unresolved_inputs if row.get("reason_code") == "missing_allocated_current" and row not in connector_unresolved),
        "ambiguous_target_mapping_count": sum(1 for row in unresolved_inputs if row.get("reason_code") == "ambiguous_target_mapping"),
        "unsupported_rating_name_count": sum(1 for row in fuse_blocked if "unsupported_fuse_margin_rating_name" in as_list(row.get("warnings"))) + sum(1 for row in unresolved_inputs if row.get("reason_code") == "unsupported_fuse_margin_rating_name"),
        "trip_current_blocked_count": sum(1 for row in fuse_blocked if "trip_current_not_continuous_margin_basis" in as_list(row.get("warnings"))) + sum(1 for row in unresolved_inputs if row.get("reason_code") == "trip_current_not_continuous_margin_basis"),
        "negative_margin_numeric_result_count": sum(1 for row in fuse_results if row.get("status") == "calculated" and number_or_none(row.get("result", {}).get("fuse_margin_a", {}).get("value")) is not None and float(row["result"]["fuse_margin_a"]["value"]) < 0),
        "connector_pin_margin_result_count": len(connector_results),
        "connector_pin_margin_calculated_count": sum(1 for row in connector_results if row.get("status") == "calculated"),
        "connector_pin_margin_blocked_count": len(connector_blocked),
        "connector_pin_unresolved_margin_input_count": len(connector_unresolved),
        "connector_pin_missing_rating_blocked_count": sum(1 for row in connector_blocked if any(item.get("field") == "connector_pin_rating" for item in as_list(row.get("missing_inputs")))),
        "connector_pin_missing_current_blocked_count": sum(1 for row in connector_blocked if any(item.get("field") == "allocated_current_a" for item in as_list(row.get("missing_inputs")))) + sum(1 for row in connector_unresolved if row.get("reason_code") == "missing_allocated_current"),
        "connector_pin_missing_pin_blocked_count": sum(1 for row in connector_blocked if any(item.get("field") == "connector_pin" for item in as_list(row.get("missing_inputs")))) + sum(1 for row in connector_unresolved if row.get("reason_code") == "missing_connector_pin"),
        "connector_pin_ambiguous_target_mapping_count": sum(1 for row in connector_unresolved if row.get("reason_code") == "ambiguous_target_mapping"),
        "connector_pin_unsupported_rating_name_count": sum(1 for row in connector_blocked if "unsupported_connector_margin_rating_name" in as_list(row.get("warnings"))) + sum(1 for row in connector_unresolved if row.get("reason_code") == "unsupported_connector_margin_rating_name"),
        "connector_pin_negative_margin_numeric_result_count": sum(1 for row in connector_results if row.get("status") == "calculated" and number_or_none(row.get("result", {}).get("connector_pin_margin_a", {}).get("value")) is not None and float(row["result"]["connector_pin_margin_a"]["value"]) < 0),
        "error_count": len(errors),
        "warning_count": len(warnings) + sum(len(as_list(row.get("warnings"))) for row in calculation_results) + sum(len(as_list(row.get("warnings"))) for row in unresolved_inputs),
    }
    return {
        "project": project,
        "generated_at_utc": utc_now(),
        "execution_pass": True,
        "topology_margin_calculation_pass": not errors,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts_for(paths),
        "calculation_results": sorted(calculation_results, key=lambda row: row["calculation_id"]),
        "blocked_calculations": sorted(blocked, key=lambda row: row["calculation_id"]),
        "unresolved_margin_inputs": sorted(unresolved_inputs, key=lambda row: row["unresolved_id"]),
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


def load_optional(path: Path | None, label: str, warnings: list[str]) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        warnings.append(f"optional {label} input missing: {path}")
        return {}
    loaded = load_json(path)
    if not isinstance(loaded, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return loaded


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate deterministic topology margin results.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--current-allocation", default=None)
    parser.add_argument("--rating-models-normalized", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--role-resolution", default=None)
    parser.add_argument("--branch-topology-enriched", default=None)
    parser.add_argument("--rail-relationships", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    current_path = Path(args.current_allocation or default_path("exports/{project}-topology-current-allocation.json", project))
    rating_path = Path(args.rating_models_normalized or default_path("exports/{project}-rating-models-normalized.json", project))
    out_path = Path(args.out or default_path("exports/{project}-topology-margin-calculations.json", project))
    paths = {
        "current_allocation": current_path,
        "rating_models": rating_path,
        "missing_data_manifest": Path(args.missing_data_manifest) if args.missing_data_manifest else None,
        "role_resolution": Path(args.role_resolution) if args.role_resolution else None,
        "branch_topology": Path(args.branch_topology_enriched) if args.branch_topology_enriched else None,
        "rail_relationships": Path(args.rail_relationships) if args.rail_relationships else None,
    }

    try:
        if not current_path.exists():
            raise FileNotFoundError(f"missing current-allocation JSON: {current_path}")
        if not rating_path.exists():
            raise FileNotFoundError(f"missing rating-models-normalized JSON: {rating_path}")
        current_allocation = load_json(current_path)
        rating_models = load_json(rating_path)
        if not isinstance(current_allocation, dict):
            raise ValueError(f"current-allocation artifact must be a JSON object: {current_path}")
        if not isinstance(rating_models, dict):
            raise ValueError(f"rating-models-normalized artifact must be a JSON object: {rating_path}")
        warnings: list[str] = []
        manifest = load_optional(paths["missing_data_manifest"], "missing-data-manifest", warnings)
        role_resolution = load_optional(paths["role_resolution"], "role-resolution", warnings)
        branch_topology = load_optional(paths["branch_topology"], "branch-topology-enriched", warnings)
        rail_relationships = load_optional(paths["rail_relationships"], "rail-relationships", warnings)
        artifact = build_artifact(
            project=project,
            paths=paths,
            current_allocation=current_allocation,
            rating_models=rating_models,
            manifest=manifest,
            role_resolution=role_resolution,
            branch_topology=branch_topology,
            rail_relationships=rail_relationships,
            warnings=warnings,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology margin calculate: "
        f"fuse_results={summary['fuse_margin_result_count']} "
        f"connector_results={summary['connector_pin_margin_result_count']} "
        f"calculated={summary['fuse_margin_calculated_count'] + summary['connector_pin_margin_calculated_count']} "
        f"blocked={summary['fuse_margin_blocked_count'] + summary['connector_pin_margin_blocked_count']} "
        f"unresolved={summary['unresolved_margin_input_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["topology_margin_calculation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
