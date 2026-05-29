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
        if isinstance(row, dict) and row.get("branch_type") in TRACE_TYPES and isinstance(row.get("branch_id"), str)
    ]


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

    if width_missing or thickness_missing:
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
    else:
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
    if length_missing or area_m2 is None:
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
    else:
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

    current_row = current_by_branch.get(branch_id)
    current_a = number_or_none(current_row.get("branch_current_a")) if current_row else None
    current_evidence = [str(ref) for ref in as_list(current_row.get("evidence_refs"))] if current_row else []
    current_sources = list(sources)
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

    if resistance_ohm is None or current_a is None:
        missing = []
        if resistance_ohm is None:
            missing.append(missing_input("trace_resistance", "Trace resistance is not available.", ["voltage_drop"], geom_blockers[0] if geom_blockers else None))
        if current_a is None:
            missing.append(missing_input("branch_current_a", "Explicit branch current is missing; PR18 does not infer current.", ["voltage_drop"], current_blockers[0] if current_blockers else None))
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
            },
            input_refs=[],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[resistance_assumption] if resistance_ohm is not None else [],
            missing_inputs=missing,
            linkage=manifest_linkage(blockers, manifest_path) if blockers else None,
            confidence=0.5,
            human_review_needed=True,
        ))
    else:
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
                "power_loss_w": value_unit(power_loss_w, "W"),
            },
            input_refs=[f"calc_trace_resistance_{safe_id(branch_id)}"],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[],
            missing_inputs=[],
            confidence=0.84,
        ))

    if area_m2 is None or current_a is None:
        missing = []
        if area_m2 is None:
            missing.append(missing_input("cross_section_area", "Trace cross-section is unavailable.", ["current_density"], geom_blockers[0] if geom_blockers else None))
        if current_a is None:
            missing.append(missing_input("branch_current_a", "Explicit branch current is missing; PR18 does not infer current.", ["current_density"], current_blockers[0] if current_blockers else None))
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
            },
            input_refs=[],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[],
            missing_inputs=missing,
            linkage=manifest_linkage(blockers, manifest_path) if blockers else None,
            confidence=0.5,
            human_review_needed=True,
        ))
    else:
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
            },
            input_refs=[f"calc_trace_cross_section_{safe_id(branch_id)}"],
            source_artifacts=current_sources,
            evidence_refs=evidence_refs + current_evidence,
            assumptions=[],
            missing_inputs=[],
            confidence=0.84,
        ))
    return results


def build_artifact(
    project: str,
    geometry_review_path: Path,
    calculation_readiness_path: Path,
    missing_data_manifest_path: Path,
    current_model_path: Path | None,
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

    readiness_by_branch = branch_readiness_index(readiness)
    current_by_branch = current_model_index(current_model)
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
            resistivity_ohm_m=copper_resistivity_ohm_m,
            resistivity_explicit=resistivity_explicit,
            review=review,
        ))

    blocked_calculations = [row for row in calculation_results if row.get("status") == "blocked"]
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
        "missing_current_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") == "branch_current_a" for item in as_list(row.get("missing_inputs")))),
        "missing_copper_thickness_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") == "copper_thickness" for item in as_list(row.get("missing_inputs")))),
        "missing_geometry_blocked_count": sum(1 for row in blocked_calculations if any(item.get("field") in {"trace_width", "trace_length", "cross_section_area"} for item in as_list(row.get("missing_inputs")))),
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
        ] + ([source_artifact("manual", current_model_path, None, "Explicit branch current model.")] if current_model_path else []),
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
        artifact = build_artifact(
            project,
            geometry_path,
            readiness_path,
            manifest_path,
            current_model_path,
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
