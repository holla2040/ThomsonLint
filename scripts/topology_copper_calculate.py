#!/usr/bin/env python3
"""Run basic deterministic copper calculations from topology artifacts.

PR 18 scope only: emit schema-valid calculation result artifacts for basic
copper geometry/resistance/current-dependent calculations. This script does not
infer current, infer ratings, create findings, or make pass/fail/compliance
judgments.
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
DEFAULT_COPPER_RESISTIVITY_OHM_M = 1.724e-8
TRACE_TYPES = {"trace_group"}
VIA_TYPES = {"via", "via_cluster"}
VIA_ID_TOKENS = ("via", "drill", "via_cluster")


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


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def number_or_none(value: Any) -> float | None:
    if is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def source_artifact(artifact_type: str, path: Path | None, record_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "path": str(path) if path else None,
        "record_id": record_id,
        "notes": notes,
    }


def assumption(assumption_id: str, description: str, basis: str, confidence: float = 1.0) -> dict[str, Any]:
    return {
        "id": assumption_id,
        "description": description,
        "basis": basis,
        "evidence_refs": [],
        "confidence": confidence,
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


def length_factor_to_m(unit: str | None) -> float | None:
    normalized = str(unit or "").strip().lower()
    factors = {
        "m": 1.0,
        "meter": 1.0,
        "meters": 1.0,
        "mm": 1e-3,
        "millimeter": 1e-3,
        "millimeters": 1e-3,
        "um": 1e-6,
        "micrometer": 1e-6,
        "micrometers": 1e-6,
        "in": 0.0254,
        "inch": 0.0254,
        "inches": 0.0254,
        "mil": 0.0000254,
        "mils": 0.0000254,
    }
    return factors.get(normalized)


def to_m(value: float, unit: str | None) -> float | None:
    factor = length_factor_to_m(unit)
    return value * factor if factor is not None else None


def to_mm(value: float, unit: str | None) -> float | None:
    meters = to_m(value, unit)
    return meters * 1000.0 if meters is not None else None


def geometry_review_records(review: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in as_list(review.get("review_records"))
        if isinstance(row, dict) and isinstance(row.get("branch_id"), str) and (is_trace_record(row) or is_via_record(row))
    ]


def is_trace_record(record: dict[str, Any]) -> bool:
    return record.get("branch_type") in TRACE_TYPES


def is_via_record(record: dict[str, Any]) -> bool:
    branch_id = str(record.get("branch_id") or "").lower()
    geometry = as_dict(record.get("geometry"))
    type_values = {
        str(record.get("target_type") or "").lower(),
        str(record.get("geometry_type") or "").lower(),
        str(record.get("branch_type") or "").lower(),
        str(geometry.get("target_type") or "").lower(),
        str(geometry.get("geometry_type") or "").lower(),
        str(geometry.get("branch_type") or "").lower(),
    }
    if type_values.intersection(VIA_TYPES):
        return True
    if any(token in branch_id for token in VIA_ID_TOKENS):
        return True
    via_fields = {
        "via_count",
        "hole_count",
        "drill_diameter_mm",
        "finished_hole_diameter_mm",
        "plated_hole_diameter_mm",
        "via_diameter_mm",
        "via_barrel_plating_thickness_mm",
        "plating_thickness_mm",
        "copper_thickness_mm",
        "copper_thickness_um",
    }
    return bool(via_fields.intersection(record.keys()) or via_fields.intersection(geometry.keys()))


def evidence_refs_for_record(record: dict[str, Any], review: dict[str, Any]) -> list[str]:
    refs = [str(ref) for ref in as_list(record.get("evidence")) if isinstance(ref, str)]
    if refs:
        return refs
    branch_id = record.get("branch_id")
    return [
        row["evidence_id"]
        for row in as_list(review.get("evidence_records"))
        if isinstance(row, dict) and row.get("branch_id") == branch_id and isinstance(row.get("evidence_id"), str)
    ]


def branch_readiness_index(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["branch_id"]: row
        for row in as_list(readiness.get("branch_readiness"))
        if isinstance(row, dict) and isinstance(row.get("branch_id"), str)
    }


def current_model_index(current_model: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(current_model, dict):
        return index
    for row in as_list(current_model.get("branch_currents")):
        if not isinstance(row, dict) or not isinstance(row.get("branch_id"), str):
            continue
        current = number_or_none(row.get("branch_current_a"))
        if current is None:
            continue
        index[row["branch_id"]] = row
    return index


ALLOCATION_TYPES_USABLE_FOR_COPPER = {
    "explicit_branch_current",
    "deterministic_branch_sum",
    "deterministic_passthrough_current",
    "deterministic_single_path_rail_current",
}


def material_current_match(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12)


def current_allocation_records(current_allocation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(current_allocation, dict):
        return []
    return [row for row in as_list(current_allocation.get("allocation_records")) if isinstance(row, dict)]


def unresolved_allocation_records(current_allocation: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(current_allocation, dict):
        return []
    return [row for row in as_list(current_allocation.get("unresolved_allocations")) if isinstance(row, dict)]


def usable_allocation_record(row: dict[str, Any]) -> bool:
    return (
        row.get("allocation_type") in ALLOCATION_TYPES_USABLE_FOR_COPPER
        and row.get("usable_for_calculation") is True
        and isinstance(row.get("branch_id"), str)
        and is_number(row.get("allocated_current_a"))
    )


def allocation_source_key(row: dict[str, Any]) -> tuple[str, ...]:
    source_ids = tuple(sorted(str(value) for value in as_list(row.get("source_current_record_ids")) if isinstance(value, str)))
    if source_ids:
        return source_ids
    allocation_id = row.get("allocation_id")
    return (str(allocation_id),) if isinstance(allocation_id, str) else (safe_id(row.get("branch_id")), safe_id(row.get("allocation_type")))


def preferred_allocation(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    sorted_rows = sorted(rows, key=lambda row: (
        0 if row.get("allocation_type") == "deterministic_branch_sum" else 1,
        str(row.get("allocation_id") or ""),
    ))
    return sorted_rows[0]


def allocation_index(current_allocation: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], int]:
    by_branch: dict[str, list[dict[str, Any]]] = {}
    source_count = 0
    for row in current_allocation_records(current_allocation):
        if not usable_allocation_record(row):
            continue
        branch_id = str(row["branch_id"])
        by_branch.setdefault(branch_id, []).append(row)
        source_count += 1

    chosen: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    for branch_id, rows in by_branch.items():
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(allocation_source_key(row), []).append(row)

        deduped: list[dict[str, Any]] = []
        conflict_rows: list[dict[str, Any]] = []
        for group_rows in grouped.values():
            values = [float(row["allocated_current_a"]) for row in group_rows]
            if any(not material_current_match(values[0], value) for value in values[1:]):
                conflict_rows.extend(group_rows)
                continue
            preferred = preferred_allocation(group_rows)
            if preferred is not None:
                deduped.append(preferred)

        if conflict_rows:
            conflicts[branch_id] = conflict_rows
            continue

        sum_rows = [row for row in deduped if row.get("allocation_type") == "deterministic_branch_sum"]
        if sum_rows:
            if len(sum_rows) > 1:
                conflicts[branch_id] = sum_rows
            else:
                chosen[branch_id] = sum_rows[0]
            continue

        if len(deduped) == 1:
            chosen[branch_id] = deduped[0]
        elif len(deduped) > 1:
            conflicts[branch_id] = deduped
    return chosen, conflicts, source_count


def unresolved_allocations_for_branch(
    branch_id: str,
    rail_name: str | None,
    net_name: str | None,
    current_allocation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in unresolved_allocation_records(current_allocation):
        row_branch = row.get("branch_id")
        row_rail = row.get("rail_name")
        branch_match = row_branch == branch_id
        rail_match = bool(rail_name and row_rail == rail_name) or bool(net_name and row_rail == net_name)
        if branch_match or rail_match:
            matches.append(row)
    return sorted(matches, key=lambda row: str(row.get("unresolved_id") or ""))


def allocation_linkage(rows: list[dict[str, Any]], manifest_path: Path | None = None) -> dict[str, Any]:
    item_ids = sorted({str(value) for row in rows for value in as_list(row.get("missing_data_manifest_item_ids")) if isinstance(value, str)})
    group_ids = sorted({str(value) for row in rows for value in as_list(row.get("missing_data_group_ids")) if isinstance(value, str)})
    categories = sorted({str(value) for row in rows for value in as_list(row.get("blocked_by_categories")) if isinstance(value, str)})
    calculations = sorted({str(value) for row in rows for value in as_list(row.get("blocked_by_calculations")) if isinstance(value, str)})
    paths = sorted({str(row.get("resolution_path")) for row in rows if isinstance(row.get("resolution_path"), str)})
    queues = sorted({str(row.get("resolution_queue") or row.get("resolution_path")) for row in rows if isinstance(row.get("resolution_queue") or row.get("resolution_path"), str)})
    linkage: dict[str, Any] = {
        "blocked_by_manifest_items": item_ids,
        "missing_data_manifest_item_ids": item_ids,
        "missing_data_group_ids": group_ids,
        "resolution_path": paths[0] if paths else None,
        "resolution_queue": queues[0] if queues else paths[0] if paths else None,
        "blocked_by_categories": categories,
        "blocked_by_calculations": calculations,
    }
    if manifest_path is not None:
        linkage["missing_data_manifest_ref"] = str(manifest_path)
    return linkage


def normalize_allocation_assumptions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        for item in as_list(row.get("assumptions")):
            if not isinstance(item, dict):
                continue
            basis = item.get("basis") if item.get("basis") in {"explicit_input", "source_artifact", "standard_formula", "manual", "not_used"} else "source_artifact"
            normalized.append({
                "id": str(item.get("id") or "allocation_assumption"),
                "description": str(item.get("description") or "Allocation artifact assumption."),
                "basis": basis,
                "evidence_refs": [str(ref) for ref in as_list(item.get("evidence_refs")) if isinstance(ref, str)],
                "confidence": float(item.get("confidence")) if is_number(item.get("confidence")) else 0.8,
            })
    return normalized


def allocation_source_current_ids(row: dict[str, Any] | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    return sorted({str(value) for value in as_list(row.get("source_current_record_ids")) if isinstance(value, str)})


def allocation_evidence_refs(row: dict[str, Any] | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    return sorted({str(value) for value in as_list(row.get("evidence_refs")) if isinstance(value, str)})


def merge_linkages(*rows: dict[str, Any] | None) -> dict[str, Any] | None:
    present = [row for row in rows if isinstance(row, dict)]
    if not present:
        return None
    merged: dict[str, Any] = {}
    for key in (
        "blocked_by_manifest_items",
        "missing_data_manifest_item_ids",
        "missing_data_group_ids",
        "blocked_by_categories",
        "blocked_by_calculations",
    ):
        merged[key] = sorted({str(value) for row in present for value in as_list(row.get(key)) if isinstance(value, str)})
    for key in ("missing_data_manifest_ref", "resolution_path", "resolution_queue"):
        values = sorted({str(row.get(key)) for row in present if isinstance(row.get(key), str)})
        if values:
            merged[key] = values[0]
    return merged


def manifest_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_list(manifest.get("manifest_items")) if isinstance(row, dict)]


def manifest_blockers_for_branch(
    branch_id: str,
    rail_name: str | None,
    net_name: str | None,
    manifest: dict[str, Any],
    categories: set[str] | None = None,
    blocks: set[str] | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in manifest_items(manifest):
        category = item.get("category")
        if categories is not None and category not in categories:
            continue
        item_blocks = {str(block) for block in as_list(item.get("blocks"))}
        if blocks is not None and item_blocks.isdisjoint(blocks):
            continue
        target_id = item.get("target_id")
        affected_branches = set(str(value) for value in as_list(item.get("affected_branches")))
        affected_rails = set(str(value) for value in as_list(item.get("affected_rails")))
        branch_match = target_id == branch_id or branch_id in affected_branches
        rail_match = bool(rail_name and (target_id == rail_name or rail_name in affected_rails))
        net_match = bool(net_name and (target_id == net_name or net_name in affected_rails))
        if branch_match or rail_match or net_match:
            matches.append(item)
    return sorted(matches, key=lambda row: str(row.get("manifest_id") or row.get("source_missing_data_id") or ""))


def manifest_linkage(items: list[dict[str, Any]], manifest_path: Path) -> dict[str, Any]:
    manifest_ids = sorted({
        str(item.get("manifest_id"))
        for item in items
        if isinstance(item.get("manifest_id"), str)
    })
    group_ids = sorted({
        str(item.get("group_id"))
        for item in items
        if isinstance(item.get("group_id"), str)
    })
    categories = sorted({
        str(item.get("category"))
        for item in items
        if isinstance(item.get("category"), str)
    })
    calculations = sorted({
        str(block)
        for item in items
        for block in as_list(item.get("blocks"))
        if isinstance(block, str)
    })
    resolution_paths = sorted({str(item.get("resolution_path")) for item in items if isinstance(item.get("resolution_path"), str)})
    resolution_path = resolution_paths[0] if len(resolution_paths) == 1 else resolution_paths[0] if resolution_paths else None
    return {
        "blocked_by_manifest_items": manifest_ids,
        "missing_data_manifest_ref": str(manifest_path),
        "missing_data_manifest_item_ids": manifest_ids,
        "missing_data_group_ids": group_ids,
        "resolution_path": resolution_path,
        "resolution_queue": resolution_path,
        "blocked_by_categories": categories,
        "blocked_by_calculations": calculations,
    }


def missing_input(field: str, reason: str, required_for: list[str], manifest_item: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "field": field,
        "reason": reason,
        "required_for": required_for,
        "manifest_item_id": manifest_item.get("manifest_id") if isinstance(manifest_item, dict) else None,
        "recommended_resolution": manifest_item.get("resolution_path") if isinstance(manifest_item, dict) else "deterministic_rule",
    }


def result_record(
    *,
    project: str,
    calculation_family: str,
    branch: dict[str, Any],
    status: str,
    result: dict[str, Any],
    intermediate_values: dict[str, Any],
    input_refs: list[str],
    source_artifacts: list[dict[str, Any]],
    evidence_refs: list[str],
    assumptions: list[dict[str, Any]],
    missing_inputs: list[dict[str, Any]],
    linkage: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    confidence: float = 0.8,
    human_review_needed: bool = False,
    source_current_record_ids: list[str] | None = None,
) -> dict[str, Any]:
    branch_id = str(branch.get("branch_id"))
    calculation_id = f"calc_{safe_id(calculation_family)}_{safe_id(branch_id)}"
    row = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project,
        "calculation_run_id": f"run_{safe_id(project)}_topology_copper_calculations",
        "calculation_id": calculation_id,
        "calculation_family": calculation_family,
        "target_type": "branch",
        "target_id": branch_id,
        "status": status,
        "result": result,
        "intermediate_values": intermediate_values,
        "input_refs": input_refs,
        "source_artifacts": source_artifacts,
        "evidence_refs": evidence_refs,
        "assumptions": assumptions,
        "missing_inputs": missing_inputs,
        "blocked_by_manifest_items": [],
        "warnings": warnings or [],
        "errors": errors or [],
        "confidence": confidence,
        "human_review_needed": human_review_needed,
    }
    if source_current_record_ids:
        row["source_current_record_ids"] = source_current_record_ids
    if linkage:
        row.update(linkage)
    return row


def extract_geometry(record: dict[str, Any]) -> dict[str, Any]:
    geometry = as_dict(record.get("geometry"))
    stackup = as_dict(record.get("stackup"))
    units = geometry.get("units") or "mm"
    width = number_or_none(geometry.get("min_width") if geometry.get("min_width") is not None else geometry.get("max_width"))
    length = number_or_none(geometry.get("total_length"))
    thickness_raw = stackup.get("copper_thickness")
    thickness_unit = stackup.get("copper_thickness_unit") or stackup.get("thickness_unit") or "mm"
    if isinstance(thickness_raw, dict):
        thickness = number_or_none(thickness_raw.get("value"))
        thickness_unit = thickness_raw.get("unit") or thickness_unit
    else:
        thickness = number_or_none(thickness_raw)
    width_mm = to_mm(width, units) if width is not None else None
    length_m = to_m(length, units) if length is not None else None
    thickness_mm = to_mm(thickness, thickness_unit) if thickness is not None else None
    return {
        "geometry_units": units,
        "width": width,
        "width_mm": width_mm,
        "length": length,
        "length_m": length_m,
        "copper_thickness": thickness,
        "copper_thickness_unit": thickness_unit,
        "copper_thickness_mm": thickness_mm,
    }


def first_number_from_contexts(contexts: list[dict[str, Any]], keys: list[str]) -> float | None:
    for context in contexts:
        for key in keys:
            value = context.get(key)
            if isinstance(value, dict):
                parsed = number_or_none(value.get("value"))
            else:
                parsed = number_or_none(value)
            if parsed is not None:
                return parsed
    return None


def explicit_single_via(record: dict[str, Any]) -> bool:
    geometry = as_dict(record.get("geometry"))
    type_values = {
        str(record.get("target_type") or "").lower(),
        str(record.get("geometry_type") or "").lower(),
        str(record.get("branch_type") or "").lower(),
        str(geometry.get("target_type") or "").lower(),
        str(geometry.get("geometry_type") or "").lower(),
        str(geometry.get("branch_type") or "").lower(),
    }
    return record.get("single_via") is True or geometry.get("single_via") is True or "via" in type_values


def extract_via_geometry(record: dict[str, Any]) -> dict[str, Any]:
    geometry = as_dict(record.get("geometry"))
    stackup = as_dict(record.get("stackup"))
    contexts = [record, geometry, stackup]
    via_count_raw = first_number_from_contexts(contexts, ["via_count", "hole_count"])
    via_count_explicit = via_count_raw is not None
    via_count = via_count_raw
    if via_count is None and explicit_single_via(record):
        via_count = 1.0

    diameter_mm = first_number_from_contexts(contexts, [
        "finished_hole_diameter_mm",
        "drill_diameter_mm",
        "plated_hole_diameter_mm",
        "via_diameter_mm",
    ])
    plating_mm = first_number_from_contexts(contexts, [
        "via_barrel_plating_thickness_mm",
        "plating_thickness_mm",
        "copper_thickness_mm",
    ])
    plating_um = first_number_from_contexts(contexts, ["copper_thickness_um"])
    if plating_mm is None and plating_um is not None:
        plating_mm = plating_um * 1e-3
    barrel_length_mm = first_number_from_contexts(contexts, ["barrel_length_mm", "board_thickness_mm"])
    return {
        "via_count": via_count,
        "via_count_explicit": via_count_explicit,
        "single_via_explicit": explicit_single_via(record),
        "finished_hole_diameter_mm": diameter_mm,
        "plating_thickness_mm": plating_mm,
        "barrel_length_mm": barrel_length_mm,
    }


def resistivity_assumption(value: float, explicit: bool) -> dict[str, Any]:
    if explicit:
        return assumption(
            "explicit_copper_resistivity",
            f"Copper resistivity was provided explicitly as {value:g} ohm*m.",
            "explicit_input",
            1.0,
        )
    return assumption(
        "default_copper_resistivity_20c",
        "Copper resistivity uses the explicit PR18 default of 1.724e-8 ohm*m at 20C.",
        "standard_formula",
        0.75,
    )


def calculate_for_branch(
    *,
    project: str,
    record: dict[str, Any],
    readiness_branch: dict[str, Any] | None,
    review_path: Path,
    readiness_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    current_by_branch: dict[str, dict[str, Any]],
    current_model_path: Path | None,
    allocation_by_branch: dict[str, dict[str, Any]],
    allocation_conflicts_by_branch: dict[str, list[dict[str, Any]]],
    current_allocation: dict[str, Any] | None,
    current_allocation_path: Path | None,
    resistivity_ohm_m: float,
    resistivity_explicit: bool,
    review: dict[str, Any],
) -> list[dict[str, Any]]:
    branch_id = str(record.get("branch_id"))
    rail_name = record.get("net_name") if not readiness_branch else readiness_branch.get("rail_name") or record.get("net_name")
    net_name = record.get("net_name")
    geom = extract_geometry(record)
    evidence_refs = evidence_refs_for_record(record, review)
    sources = [
        source_artifact("topology_geometry_review", review_path, f"geo_{branch_id}", "Geometry review record."),
        source_artifact("calculation_readiness", readiness_path, branch_id, "Calculation readiness context."),
        source_artifact("missing_data_manifest", manifest_path, None, "Missing data blocker context."),
    ]
    results: list[dict[str, Any]] = []
    base_branch = {"branch_id": branch_id}
    is_trace = is_trace_record(record)

    width_missing = geom["width_mm"] is None
    thickness_missing = geom["copper_thickness_mm"] is None
    length_missing = geom["length_m"] is None
    geom_blockers = manifest_blockers_for_branch(
        branch_id,
        str(rail_name) if rail_name else None,
        str(net_name) if net_name else None,
        manifest,
        {"copper_thickness_missing", "geometry_width_missing", "geometry_length_missing", "geometry_area_missing"},
        {"copper_calculation", "thermal_calculation", "voltage_drop_calculation"},
    )
    area_mm2: float | None = None
    area_m2: float | None = None

    if is_trace and (width_missing or thickness_missing):
        missing: list[dict[str, Any]] = []
        if width_missing:
            missing.append(missing_input("trace_width", "Trace width is missing.", ["trace_cross_section"], geom_blockers[0] if geom_blockers else None))
        if thickness_missing:
            thickness_item = next((item for item in geom_blockers if item.get("category") == "copper_thickness_missing"), geom_blockers[0] if geom_blockers else None)
            missing.append(missing_input("copper_thickness", "Copper thickness is missing.", ["trace_cross_section", "trace_resistance"], thickness_item))
        results.append(result_record(
            project=project,
            calculation_family="trace_cross_section",
            branch=base_branch,
            status="blocked",
            result={"cross_section_area": None},
            intermediate_values={
                "trace_width": value_unit(geom["width_mm"], "mm"),
                "copper_thickness": value_unit(geom["copper_thickness_mm"], "mm"),
            },
            input_refs=[],
            source_artifacts=sources,
            evidence_refs=evidence_refs,
            assumptions=[],
            missing_inputs=missing,
            linkage=manifest_linkage(geom_blockers, manifest_path) if geom_blockers else None,
            confidence=0.5,
            human_review_needed=True,
        ))
    elif is_trace:
        area_mm2 = float(geom["width_mm"]) * float(geom["copper_thickness_mm"])
        area_m2 = area_mm2 * 1e-6
        results.append(result_record(
            project=project,
            calculation_family="trace_cross_section",
            branch=base_branch,
            status="calculated",
            result={"cross_section_area": value_unit(area_mm2, "mm^2", "standard_formula", 0.9, evidence_refs)},
            intermediate_values={
                "trace_width": value_unit(float(geom["width_mm"]), "mm"),
                "copper_thickness": value_unit(float(geom["copper_thickness_mm"]), "mm"),
                "area_m2": value_unit(area_m2, "m^2"),
            },
            input_refs=[],
            source_artifacts=sources,
            evidence_refs=evidence_refs,
            assumptions=[assumption("rectangular_trace_cross_section", "Cross-section area is width multiplied by copper thickness.", "standard_formula", 0.9)],
            missing_inputs=[],
            confidence=0.9,
        ))

    resistance_ohm: float | None = None
    resistance_assumption = resistivity_assumption(resistivity_ohm_m, resistivity_explicit)
    if is_trace and (length_missing or area_m2 is None):
        missing = []
        if length_missing:
            missing.append(missing_input("trace_length", "Trace length is missing.", ["trace_resistance"], geom_blockers[0] if geom_blockers else None))
        if area_m2 is None:
            missing.append(missing_input("cross_section_area", "Trace cross-section is unavailable.", ["trace_resistance"], geom_blockers[0] if geom_blockers else None))
        results.append(result_record(
            project=project,
            calculation_family="trace_resistance",
            branch=base_branch,
            status="blocked",
            result={"trace_resistance": None},
            intermediate_values={
                "length_m": value_unit(geom["length_m"], "m"),
                "area_m2": value_unit(area_m2, "m^2"),
                "copper_resistivity": value_unit(resistivity_ohm_m, "ohm*m"),
            },
            input_refs=[],
            source_artifacts=sources,
            evidence_refs=evidence_refs,
            assumptions=[resistance_assumption],
            missing_inputs=missing,
            linkage=manifest_linkage(geom_blockers, manifest_path) if geom_blockers else None,
            confidence=0.5,
            human_review_needed=True,
        ))
    elif is_trace:
        resistance_ohm = resistivity_ohm_m * float(geom["length_m"]) / area_m2
        results.append(result_record(
            project=project,
            calculation_family="trace_resistance",
            branch=base_branch,
            status="calculated",
            result={"trace_resistance": value_unit(resistance_ohm, "ohm", "standard_formula", 0.86, evidence_refs)},
            intermediate_values={
                "length_m": value_unit(float(geom["length_m"]), "m"),
                "area_m2": value_unit(area_m2, "m^2"),
                "copper_resistivity": value_unit(resistivity_ohm_m, "ohm*m"),
            },
            input_refs=[f"calc_trace_cross_section_{safe_id(branch_id)}"],
            source_artifacts=sources,
            evidence_refs=evidence_refs,
            assumptions=[resistance_assumption],
            missing_inputs=[],
            confidence=0.86,
        ))

    legacy_current_row = current_by_branch.get(branch_id)
    legacy_current_a = number_or_none(legacy_current_row.get("branch_current_a")) if legacy_current_row else None
    allocation_row = allocation_by_branch.get(branch_id)
    allocation_conflict_rows = allocation_conflicts_by_branch.get(branch_id, [])
    unresolved_allocation_rows = unresolved_allocations_for_branch(
        branch_id,
        str(rail_name) if rail_name else None,
        str(net_name) if net_name else None,
        current_allocation,
    )

    current_a: float | None = None
    current_source_mode: str | None = None
    current_evidence: list[str] = []
    current_assumptions: list[dict[str, Any]] = []
    current_sources = list(sources)
    current_input_refs: list[str] = []
    current_warnings: list[str] = []
    source_current_ids: list[str] = []
    allocation_current_linkage: dict[str, Any] | None = None
    current_missing_field = "branch_current_a"
    current_missing_reason = "Explicit branch current is missing; PR18 does not infer current."
    current_source_conflict = False

    if current_allocation_path is not None:
        current_missing_field = "allocated_current_a"
        current_missing_reason = "Usable allocated branch current is missing; PR21 does not infer current."
        current_sources.append(source_artifact(
            "topology_current_allocation",
            current_allocation_path,
            allocation_row.get("allocation_id") if isinstance(allocation_row, dict) else None,
            "PR20 topology current allocation.",
        ))
        if allocation_conflict_rows:
            current_source_conflict = True
            current_warnings.append("current_source_conflict: multiple usable allocation records for this branch are not deduplicable")
            allocation_current_linkage = allocation_linkage(allocation_conflict_rows, manifest_path)
        elif allocation_row is not None:
            allocation_current_a = number_or_none(allocation_row.get("allocated_current_a"))
            if legacy_current_a is not None and allocation_current_a is not None and not material_current_match(allocation_current_a, legacy_current_a):
                current_source_conflict = True
                current_warnings.append("current_source_conflict: current allocation and legacy current model differ")
            elif allocation_current_a is not None:
                current_a = allocation_current_a
                current_source_mode = "allocation"
                allocation_id = allocation_row.get("allocation_id")
                if isinstance(allocation_id, str):
                    current_input_refs.append(allocation_id)
                current_evidence.extend(allocation_evidence_refs(allocation_row))
                current_assumptions.extend(normalize_allocation_assumptions([allocation_row]))
                source_current_ids = allocation_source_current_ids(allocation_row)
                allocation_current_linkage = allocation_linkage([allocation_row], manifest_path)
                if legacy_current_a is not None and current_model_path is not None:
                    current_sources.append(source_artifact("manual", current_model_path, branch_id, "Legacy current model matched PR20 allocation."))
                    current_evidence.extend([str(ref) for ref in as_list(legacy_current_row.get("evidence_refs")) if isinstance(ref, str)])
            else:
                allocation_current_linkage = allocation_linkage(unresolved_allocation_rows, manifest_path) if unresolved_allocation_rows else None
        else:
            allocation_current_linkage = allocation_linkage(unresolved_allocation_rows, manifest_path) if unresolved_allocation_rows else None
    else:
        current_a = legacy_current_a
        current_source_mode = "legacy" if current_a is not None else None
        current_evidence = [str(ref) for ref in as_list(legacy_current_row.get("evidence_refs")) if isinstance(ref, str)] if legacy_current_row else []
        if current_model_path is not None:
            current_sources.append(source_artifact("manual", current_model_path, branch_id, "Explicit branch current model."))

    current_blockers = manifest_blockers_for_branch(
        branch_id,
        str(rail_name) if rail_name else None,
        str(net_name) if net_name else None,
        manifest,
        {"branch_current_unknown", "current_model_missing"},
        {"copper_calculation", "voltage_drop_calculation", "thermal_calculation"},
    )
    current_linkage = allocation_current_linkage if allocation_current_linkage else manifest_linkage(current_blockers, manifest_path) if current_blockers else None
    current_human_review_needed = bool(current_source_conflict or unresolved_allocation_rows)

    if is_trace and (resistance_ohm is None or current_a is None or current_source_conflict):
        missing = []
        if resistance_ohm is None:
            missing.append(missing_input("trace_resistance", "Trace resistance is not available.", ["voltage_drop"], geom_blockers[0] if geom_blockers else None))
        if current_a is None:
            missing.append(missing_input(current_missing_field, current_missing_reason, ["voltage_drop", "current_allocation"], current_blockers[0] if current_blockers else None))
        if current_source_conflict:
            missing.append(missing_input("current_source_conflict", "Current allocation and legacy or duplicate allocation sources conflict.", ["voltage_drop"], current_blockers[0] if current_blockers else None))
        blockers = current_blockers + ([] if resistance_ohm is not None else geom_blockers)
        results.append(result_record(
            project=project,
            calculation_family="voltage_drop",
            branch=base_branch,
            status="blocked",
            result={"voltage_drop": None},
            intermediate_values={
                "trace_resistance": value_unit(resistance_ohm, "ohm"),
                "branch_current_a": value_unit(current_a, "A"),
                "allocated_current_a": value_unit(current_a, "A") if current_allocation_path is not None else None,
                "current_source": current_source_mode,
                "source_current_record_ids": source_current_ids,
            },
            input_refs=[],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[resistance_assumption] if resistance_ohm is not None else [],
            missing_inputs=missing,
            linkage=current_linkage if current_linkage else manifest_linkage(blockers, manifest_path) if blockers else None,
            warnings=current_warnings,
            confidence=0.5,
            human_review_needed=True or current_human_review_needed,
            source_current_record_ids=source_current_ids,
        ))
    elif is_trace:
        voltage_drop_v = current_a * resistance_ohm
        power_loss_w = current_a * current_a * resistance_ohm
        results.append(result_record(
            project=project,
            calculation_family="voltage_drop",
            branch=base_branch,
            status="calculated",
            result={"voltage_drop": value_unit(voltage_drop_v, "V", "standard_formula", 0.84, evidence_refs + current_evidence)},
            intermediate_values={
                "trace_resistance": value_unit(resistance_ohm, "ohm"),
                "branch_current_a": value_unit(current_a, "A"),
                "allocated_current_a": value_unit(current_a, "A") if current_allocation_path is not None else None,
                "power_loss_w": value_unit(power_loss_w, "W"),
                "current_source": current_source_mode,
                "source_current_record_ids": source_current_ids,
            },
            input_refs=[f"calc_trace_resistance_{safe_id(branch_id)}"] + current_input_refs,
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=current_assumptions,
            missing_inputs=[],
            linkage=allocation_current_linkage,
            warnings=current_warnings,
            confidence=0.84,
            source_current_record_ids=source_current_ids,
        ))

    if is_trace and (area_m2 is None or current_a is None or current_source_conflict):
        missing = []
        if area_m2 is None:
            missing.append(missing_input("cross_section_area", "Trace cross-section is unavailable.", ["current_density"], geom_blockers[0] if geom_blockers else None))
        if current_a is None:
            missing.append(missing_input(current_missing_field, current_missing_reason, ["current_density", "current_allocation"], current_blockers[0] if current_blockers else None))
        if current_source_conflict:
            missing.append(missing_input("current_source_conflict", "Current allocation and legacy or duplicate allocation sources conflict.", ["current_density"], current_blockers[0] if current_blockers else None))
        blockers = current_blockers + ([] if area_m2 is not None else geom_blockers)
        results.append(result_record(
            project=project,
            calculation_family="current_density",
            branch=base_branch,
            status="blocked",
            result={"current_density": None},
            intermediate_values={
                "cross_section_area": value_unit(area_mm2, "mm^2"),
                "branch_current_a": value_unit(current_a, "A"),
                "allocated_current_a": value_unit(current_a, "A") if current_allocation_path is not None else None,
                "current_source": current_source_mode,
                "source_current_record_ids": source_current_ids,
            },
            input_refs=[],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[],
            missing_inputs=missing,
            linkage=current_linkage if current_linkage else manifest_linkage(blockers, manifest_path) if blockers else None,
            warnings=current_warnings,
            confidence=0.5,
            human_review_needed=True or current_human_review_needed,
            source_current_record_ids=source_current_ids,
        ))
    elif is_trace:
        current_density_a_per_mm2 = current_a / (area_m2 * 1e6)
        results.append(result_record(
            project=project,
            calculation_family="current_density",
            branch=base_branch,
            status="calculated",
            result={"current_density": value_unit(current_density_a_per_mm2, "A/mm^2", "standard_formula", 0.84, evidence_refs + current_evidence)},
            intermediate_values={
                "cross_section_area": value_unit(area_mm2, "mm^2"),
                "area_m2": value_unit(area_m2, "m^2"),
                "branch_current_a": value_unit(current_a, "A"),
                "allocated_current_a": value_unit(current_a, "A") if current_allocation_path is not None else None,
                "current_source": current_source_mode,
                "source_current_record_ids": source_current_ids,
            },
            input_refs=[f"calc_trace_cross_section_{safe_id(branch_id)}"] + current_input_refs,
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=current_assumptions,
            missing_inputs=[],
            linkage=allocation_current_linkage,
            warnings=current_warnings,
            confidence=0.84,
            source_current_record_ids=source_current_ids,
        ))
    if is_via_record(record):
        via = extract_via_geometry(record)
        via_blockers = manifest_blockers_for_branch(
            branch_id,
            str(rail_name) if rail_name else None,
            str(net_name) if net_name else None,
            manifest,
            {"copper_thickness_missing", "geometry_missing", "geometry_width_missing", "geometry_area_missing", "branch_current_unknown", "current_model_missing", "source_sink_not_resolved"},
            {"copper_calculation", "thermal_calculation", "voltage_drop_calculation", "current_allocation", "calculation_readiness"},
        )
        via_linkage = manifest_linkage(via_blockers, manifest_path) if via_blockers else None
        missing = []
        via_count = via["via_count"]
        diameter_mm = via["finished_hole_diameter_mm"]
        plating_mm = via["plating_thickness_mm"]
        if current_a is None:
            missing.append(missing_input(current_missing_field, current_missing_reason, ["via_current_density", "current_allocation"], current_blockers[0] if current_blockers else None))
        if current_source_conflict:
            missing.append(missing_input("current_source_conflict", "Current allocation and legacy or duplicate allocation sources conflict.", ["via_current_density"], current_blockers[0] if current_blockers else None))
        if via_count is None:
            missing.append(missing_input("via_count", "Via count is missing; PR22 does not infer via count from branch names.", ["via_current_density"], via_blockers[0] if via_blockers else None))
        if diameter_mm is None:
            missing.append(missing_input("finished_hole_diameter_mm", "Finished hole or drill diameter is missing.", ["via_current_density"], via_blockers[0] if via_blockers else None))
        if plating_mm is None:
            missing.append(missing_input("via_barrel_plating_thickness_mm", "Via barrel plating thickness is missing.", ["via_current_density"], via_blockers[0] if via_blockers else None))
        if via_count is not None and via_count <= 0:
            missing.append(missing_input("via_count", "Via count must be positive.", ["via_current_density"], via_blockers[0] if via_blockers else None))
        if diameter_mm is not None and diameter_mm <= 0:
            missing.append(missing_input("finished_hole_diameter_mm", "Finished hole or drill diameter must be positive.", ["via_current_density"], via_blockers[0] if via_blockers else None))
        if plating_mm is not None and plating_mm <= 0:
            missing.append(missing_input("via_barrel_plating_thickness_mm", "Via barrel plating thickness must be positive.", ["via_current_density"], via_blockers[0] if via_blockers else None))

        via_sources = list(current_sources)
        via_input_refs = list(current_input_refs)
        via_assumptions = [
            assumption(
                "via_barrel_area_approximation",
                "Via barrel cross-section area is approximated as pi times finished hole diameter times plating thickness.",
                "standard_formula",
                0.8,
            )
        ] + current_assumptions
        if via_count is not None and via_count > 1:
            via_assumptions.append(assumption(
                "parallel_via_barrel_area",
                "Explicit via count is evaluated as total parallel via barrel area; this is not a pass/fail current-sharing conclusion.",
                "standard_formula",
                0.75,
            ))
        if missing:
            results.append(result_record(
                project=project,
                calculation_family="via_current_density",
                branch=base_branch,
                status="blocked",
                result={"via_current_density": None},
                intermediate_values={
                    "allocated_current_a": value_unit(current_a, "A"),
                    "branch_current_a": value_unit(current_a, "A"),
                    "via_count": value_unit(via_count, "count"),
                    "finished_hole_diameter_mm": value_unit(diameter_mm, "mm"),
                    "plating_thickness_mm": value_unit(plating_mm, "mm"),
                    "barrel_length_mm": value_unit(via["barrel_length_mm"], "mm"),
                    "current_source": current_source_mode,
                    "source_current_record_ids": source_current_ids,
                },
                input_refs=via_input_refs,
                source_artifacts=via_sources,
                evidence_refs=evidence_refs + current_evidence,
                assumptions=via_assumptions,
                missing_inputs=missing,
                linkage=merge_linkages(current_linkage, via_linkage),
                warnings=current_warnings,
                confidence=0.5,
                human_review_needed=True,
                source_current_record_ids=source_current_ids,
            ))
        else:
            via_count_float = float(via_count)
            diameter_float = float(diameter_mm)
            plating_float = float(plating_mm)
            area_per_via_mm2 = math.pi * diameter_float * plating_float
            total_area_mm2 = area_per_via_mm2 * via_count_float
            via_density = float(current_a) / total_area_mm2
            intermediate_values = {
                "allocated_current_a": value_unit(float(current_a), "A"),
                "branch_current_a": value_unit(float(current_a), "A"),
                "via_count": value_unit(via_count_float, "count"),
                "finished_hole_diameter_mm": value_unit(diameter_float, "mm"),
                "plating_thickness_mm": value_unit(plating_float, "mm"),
                "area_per_via_mm2": value_unit(area_per_via_mm2, "mm^2"),
                "total_barrel_area_mm2": value_unit(total_area_mm2, "mm^2"),
                "barrel_length_mm": value_unit(via["barrel_length_mm"], "mm"),
                "current_source": current_source_mode,
                "source_current_record_ids": source_current_ids,
            }
            if via_count_float > 1:
                intermediate_values["current_per_via_a"] = value_unit(float(current_a) / via_count_float, "A")
            results.append(result_record(
                project=project,
                calculation_family="via_current_density",
                branch=base_branch,
                status="calculated",
                result={"via_current_density": value_unit(via_density, "A/mm^2", "standard_formula", 0.78, evidence_refs + current_evidence)},
                intermediate_values=intermediate_values,
                input_refs=via_input_refs,
                source_artifacts=via_sources,
                evidence_refs=evidence_refs + current_evidence,
                assumptions=via_assumptions,
                missing_inputs=[],
                linkage=allocation_current_linkage,
                warnings=current_warnings,
                confidence=0.78,
                human_review_needed=False,
                source_current_record_ids=source_current_ids,
            ))
    return results


def build_artifact(
    project: str,
    geometry_review_path: Path,
    calculation_readiness_path: Path,
    missing_data_manifest_path: Path,
    current_model_path: Path | None,
    current_allocation_path: Path | None,
    copper_resistivity_ohm_m: float,
    resistivity_explicit: bool,
) -> dict[str, Any]:
    review = load_json(geometry_review_path)
    readiness = load_json(calculation_readiness_path)
    manifest = load_json(missing_data_manifest_path)
    if not isinstance(review, dict):
        raise ValueError(f"geometry-review artifact must be a JSON object: {geometry_review_path}")
    if not isinstance(readiness, dict):
        raise ValueError(f"calculation-readiness artifact must be a JSON object: {calculation_readiness_path}")
    if not isinstance(manifest, dict):
        raise ValueError(f"missing-data-manifest artifact must be a JSON object: {missing_data_manifest_path}")
    current_model = None
    if current_model_path is not None:
        current_model = load_json(current_model_path)
        if not isinstance(current_model, dict):
            raise ValueError(f"current model artifact must be a JSON object: {current_model_path}")
    current_allocation = None
    if current_allocation_path is not None:
        current_allocation = load_json(current_allocation_path)
        if not isinstance(current_allocation, dict):
            raise ValueError(f"current allocation artifact must be a JSON object: {current_allocation_path}")

    readiness_by_branch = branch_readiness_index(readiness)
    current_by_branch = current_model_index(current_model)
    allocation_by_branch, allocation_conflicts_by_branch, allocation_source_count = allocation_index(current_allocation)
    calculation_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    for record in sorted(geometry_review_records(review), key=lambda row: str(row.get("branch_id"))):
        calculation_results.extend(calculate_for_branch(
            project=project,
            record=record,
            readiness_branch=readiness_by_branch.get(str(record.get("branch_id"))),
            review_path=geometry_review_path,
            readiness_path=calculation_readiness_path,
            manifest_path=missing_data_manifest_path,
            manifest=manifest,
            current_by_branch=current_by_branch,
            current_model_path=current_model_path,
            allocation_by_branch=allocation_by_branch,
            allocation_conflicts_by_branch=allocation_conflicts_by_branch,
            current_allocation=current_allocation,
            current_allocation_path=current_allocation_path,
            resistivity_ohm_m=copper_resistivity_ohm_m,
            resistivity_explicit=resistivity_explicit,
            review=review,
        ))

    blocked_calculations = [row for row in calculation_results if row.get("status") == "blocked"]
    calculated_current_results = [
        row for row in calculation_results
        if row.get("status") == "calculated" and row.get("calculation_family") in {"voltage_drop", "current_density", "via_current_density"}
    ]
    summary = {
        "calculation_result_count": len(calculation_results),
        "calculated_count": sum(1 for row in calculation_results if row.get("status") == "calculated"),
        "blocked_count": len(blocked_calculations),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "trace_cross_section_calculated_count": sum(1 for row in calculation_results if row.get("calculation_family") == "trace_cross_section" and row.get("status") == "calculated"),
        "trace_resistance_calculated_count": sum(1 for row in calculation_results if row.get("calculation_family") == "trace_resistance" and row.get("status") == "calculated"),
        "voltage_drop_calculated_count": sum(1 for row in calculation_results if row.get("calculation_family") == "voltage_drop" and row.get("status") == "calculated"),
        "current_density_calculated_count": sum(1 for row in calculation_results if row.get("calculation_family") == "current_density" and row.get("status") == "calculated"),
        "via_current_density_calculated_count": sum(1 for row in calculation_results if row.get("calculation_family") == "via_current_density" and row.get("status") == "calculated"),
        "via_current_density_blocked_count": sum(1 for row in calculation_results if row.get("calculation_family") == "via_current_density" and row.get("status") == "blocked"),
        "missing_current_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") == "branch_current_a" for item in as_list(row.get("missing_inputs")))),
        "missing_copper_thickness_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") == "copper_thickness" for item in as_list(row.get("missing_inputs")))),
        "missing_geometry_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") in {"trace_width", "trace_length", "cross_section_area"} for item in as_list(row.get("missing_inputs")))),
        "missing_via_geometry_blocked_count": sum(1 for row in blocked_calculations if row.get("calculation_family") == "via_current_density" and any(item.get("field") in {"finished_hole_diameter_mm", "drill_diameter_mm"} for item in as_list(row.get("missing_inputs")))),
        "missing_via_plating_blocked_count": sum(1 for row in blocked_calculations if row.get("calculation_family") == "via_current_density" and any(item.get("field") in {"via_barrel_plating_thickness_mm", "plating_thickness_mm"} for item in as_list(row.get("missing_inputs")))),
        "missing_via_count_blocked_count": sum(1 for row in blocked_calculations if row.get("calculation_family") == "via_current_density" and any(item.get("field") == "via_count" for item in as_list(row.get("missing_inputs")))),
        "current_allocation_source_count": allocation_source_count,
        "allocated_current_used_count": sum(1 for row in calculated_current_results if row.get("intermediate_values", {}).get("current_source") == "allocation"),
        "legacy_current_model_used_count": sum(1 for row in calculated_current_results if row.get("intermediate_values", {}).get("current_source") == "legacy"),
        "current_source_conflict_count": sum(1 for row in blocked_calculations if any(item.get("field") == "current_source_conflict" for item in as_list(row.get("missing_inputs")))),
        "unresolved_allocation_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") == "allocated_current_a" for item in as_list(row.get("missing_inputs")))),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "execution_pass": True,
        "topology_copper_calculation_pass": not errors,
        "summary": summary,
        "source_artifacts": [
            source_artifact("topology_geometry_review", geometry_review_path, None, None),
            source_artifact("calculation_readiness", calculation_readiness_path, None, None),
            source_artifact("missing_data_manifest", missing_data_manifest_path, None, None),
        ] + ([source_artifact("topology_current_allocation", current_allocation_path, None, "PR20 topology current allocation.")] if current_allocation_path else [])
        + ([source_artifact("manual", current_model_path, None, "Explicit branch current model.")] if current_model_path else []),
        "calculation_results": calculation_results,
        "blocked_calculations": blocked_calculations,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic topology copper calculations.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--geometry-review", default=None)
    parser.add_argument("--calculation-readiness", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--current-model", default=None)
    parser.add_argument("--current-allocation", default=None)
    parser.add_argument("--copper-resistivity-ohm-m", type=float, default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    geometry_path = Path(args.geometry_review or default_path("exports/{project}-topology-geometry-review.json", project))
    readiness_path = Path(args.calculation_readiness or default_path("exports/{project}-calculation-readiness-inventory.json", project))
    manifest_path = Path(args.missing_data_manifest or default_path("exports/{project}-missing-data-manifest.json", project))
    current_model_path = Path(args.current_model) if args.current_model else None
    current_allocation_path = Path(args.current_allocation) if args.current_allocation else None
    out_path = Path(args.out or default_path("exports/{project}-topology-copper-calculations.json", project))
    resistivity_explicit = args.copper_resistivity_ohm_m is not None
    resistivity = args.copper_resistivity_ohm_m if resistivity_explicit else DEFAULT_COPPER_RESISTIVITY_OHM_M
    try:
        for label, path in (
            ("geometry-review", geometry_path),
            ("calculation-readiness", readiness_path),
            ("missing-data-manifest", manifest_path),
        ):
            if not path.exists():
                raise FileNotFoundError(f"missing {label} JSON: {path}")
        if current_model_path is not None and not current_model_path.exists():
            raise FileNotFoundError(f"missing current-model JSON: {current_model_path}")
        if current_allocation_path is not None and not current_allocation_path.exists():
            raise FileNotFoundError(f"missing current-allocation JSON: {current_allocation_path}")
        artifact = build_artifact(
            project,
            geometry_path,
            readiness_path,
            manifest_path,
            current_model_path,
            current_allocation_path,
            float(resistivity),
            resistivity_explicit,
        )
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology copper calculations: "
        f"results={summary['calculation_result_count']} "
        f"calculated={summary['calculated_count']} "
        f"blocked={summary['blocked_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={out_path}"
    )
    return 0 if artifact["execution_pass"] and artifact["topology_copper_calculation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
