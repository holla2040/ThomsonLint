#!/usr/bin/env python3
"""Validate topology-aware geometry review artifacts.

PR 11 scope only: validate the deterministic review artifact produced by
topology_geometry_review.py. This script does not calculate ampacity, current
density, thermal rise, voltage drop, compliance, or findings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
DEFAULT_PROJECT = "example"
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "project",
    "generated_at_utc",
    "sources",
    "summary",
    "review_records",
    "evidence_records",
    "unresolved",
    "warnings",
    "errors",
    "execution_pass",
    "geometry_review_pass",
}
REVIEW_STATUSES = {
    "evidence_only",
    "needs_current_model",
    "geometry_incomplete",
    "ready_for_later_calculation",
}
EVIDENCE_SOURCES = {"branch_topology", "copper_association", "stackup", "topology"}
FORBIDDEN_EVIDENCE_CLAIMS = {
    "ampacity",
    "current_density",
    "thermal_rise",
    "voltage_drop",
    "compliance_pass",
    "compliance_fail",
}
GEOMETRY_UNRESOLVED_TYPES = {
    "missing_width",
    "missing_length",
    "missing_area",
    "missing_bbox",
    "missing_geometry",
    "missing_diameter",
    "mixed_unknown",
}
DRILL_VIA_SPAN_RE = re.compile(r"^(DRILL|VIA)[_-]?(\d+)[-_](\d+)$", re.IGNORECASE)


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


def check_row(name: str, errors: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    errors = errors or []
    warnings = warnings or []
    return {"check": name, "passed": not errors, "errors": errors, "warnings": warnings}


def id_values(rows: Any, key: str) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [row.get(key) for row in rows if isinstance(row, dict) and isinstance(row.get(key), str)]


def duplicate_values(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def normalized_claim(value: Any) -> str:
    return str(value or "").strip().lower()


def parse_drill_or_via_span(layer_name: Any) -> dict[str, Any] | None:
    if not isinstance(layer_name, str):
        return None
    match = DRILL_VIA_SPAN_RE.match(layer_name.strip())
    if not match:
        return None
    start = int(match.group(2))
    end = int(match.group(3))
    return {
        "drill_or_via_type": match.group(1).upper(),
        "start_layer_index": start,
        "end_layer_index": end,
        "span_label": f"{start}-{end}",
        "layer_span_count": abs(end - start) + 1,
    }


def rows_for_branch(rows: Any, branch_id: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("branch_id") == branch_id]


def unresolved_type_set(review: dict[str, Any], branch_id: Any) -> set[str]:
    types: set[str] = set()
    for item in rows_for_branch(review.get("unresolved"), branch_id):
        item_type = item.get("type")
        if isinstance(item_type, str):
            types.add(item_type)
    for record in rows_for_branch(review.get("review_records"), branch_id):
        flags = record.get("unresolved_flags")
        if isinstance(flags, list):
            types.update(flag for flag in flags if isinstance(flag, str))
    return types


def evidence_type_set(review: dict[str, Any], branch_id: Any) -> set[str]:
    types: set[str] = set()
    for item in rows_for_branch(review.get("evidence_records"), branch_id):
        evidence_type = item.get("evidence_type")
        if isinstance(evidence_type, str):
            types.add(evidence_type)
    return types


def has_drill_or_via_span_context(record: dict[str, Any], review: dict[str, Any]) -> bool:
    if record.get("branch_type") != "via_cluster":
        return False
    stackup = record.get("stackup") if isinstance(record.get("stackup"), dict) else {}
    if stackup.get("is_drill_layer") is True or isinstance(stackup.get("via_span"), dict):
        return True
    function = str(stackup.get("layer_function") or "").upper()
    if function == "DRILL":
        return True
    layer_name = record.get("layer") or stackup.get("primary_layer")
    if parse_drill_or_via_span(layer_name) is not None:
        return True
    return bool(evidence_type_set(review, record.get("branch_id")).intersection({"via_drill_span", "drill_layer_context"}))


def has_unresolved(review: dict[str, Any], branch_id: Any, expected: set[str]) -> bool:
    return bool(unresolved_type_set(review, branch_id).intersection(expected))


def has_width_geometry(record: dict[str, Any], review: dict[str, Any]) -> bool:
    geometry = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    return bool(
        geometry.get("known_width_count")
        or geometry.get("min_width") is not None
        or geometry.get("max_width") is not None
        or "width" in evidence_type_set(review, record.get("branch_id"))
    )


def has_length_geometry(record: dict[str, Any], review: dict[str, Any]) -> bool:
    geometry = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    return bool(geometry.get("total_length") is not None or "length" in evidence_type_set(review, record.get("branch_id")))


def has_area_or_bbox_geometry(record: dict[str, Any], review: dict[str, Any]) -> bool:
    geometry = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    evidence_types = evidence_type_set(review, record.get("branch_id"))
    return bool(
        geometry.get("total_area") is not None
        or geometry.get("bbox") is not None
        or "area" in evidence_types
        or "bbox" in evidence_types
    )


def check_artifact_shape(review: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(review, dict):
        return ["review JSON must be an object"], warnings

    for key in sorted(REQUIRED_TOP_LEVEL - set(review)):
        errors.append(f"missing top-level key: {key}")

    typed_arrays = ("review_records", "evidence_records", "unresolved", "warnings", "errors")
    for key in typed_arrays:
        if key in review and not isinstance(review.get(key), list):
            errors.append(f"{key} must be an array")
    if "summary" in review and not isinstance(review.get("summary"), dict):
        errors.append("summary must be an object")
    if "sources" in review and not isinstance(review.get("sources"), dict):
        errors.append("sources must be an object")
    return errors, warnings


def check_review_records(review: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    review_ids = id_values(records, "review_id")
    for duplicate in duplicate_values(review_ids):
        errors.append(f"duplicate review_id: {duplicate}")

    required = {
        "review_id",
        "branch_id",
        "net_name",
        "topology_net_type",
        "branch_type",
        "geometry",
        "stackup",
        "current_context",
        "review_status",
    }
    for idx, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"review_records[{idx}] must be an object")
            continue
        label = record.get("review_id") or record.get("branch_id") or idx
        for key in sorted(required - set(record)):
            errors.append(f"review_records[{label}] missing required key: {key}")

        branch_id = record.get("branch_id")
        status = record.get("review_status")
        if status not in REVIEW_STATUSES:
            errors.append(f"review_records[{label}].review_status invalid: {status}")

        geometry = record.get("geometry")
        stackup = record.get("stackup")
        context = record.get("current_context")
        if "geometry" in record and not isinstance(geometry, dict):
            errors.append(f"review_records[{label}].geometry must be an object")
            geometry = {}
        if "stackup" in record and not isinstance(stackup, dict):
            errors.append(f"review_records[{label}].stackup must be an object")
            stackup = {}
        if "current_context" in record and not isinstance(context, dict):
            errors.append(f"review_records[{label}].current_context must be an object")
            context = {}

        context = context if isinstance(context, dict) else {}
        if context.get("estimated_current_a") is None and context.get("current_known") is not False:
            errors.append(f"review_records[{label}].current_known must be false when estimated_current_a is null")
        if context.get("current_known") is True and not context.get("current_model_ref"):
            errors.append(f"review_records[{label}].current_known requires current_model_ref")

        if record.get("topology_net_type") == "power":
            current_unresolved = context.get("current_basis") == "unresolved" or context.get("estimated_current_a") is None
            if current_unresolved and status != "needs_current_model" and not has_unresolved(review, branch_id, {"current_unknown"}):
                errors.append(f"review_records[{label}] power current unresolved without needs_current_model or current_unknown")

        branch_type = record.get("branch_type")
        if branch_type == "trace_group":
            if not has_width_geometry(record, review) and not has_unresolved(review, branch_id, {"missing_width"}):
                errors.append(f"review_records[{label}] trace_group missing width without missing_width unresolved")
            if not has_length_geometry(record, review) and not has_unresolved(review, branch_id, {"missing_length"}):
                errors.append(f"review_records[{label}] trace_group missing length without missing_length unresolved")
        elif branch_type == "plane_region":
            if not has_area_or_bbox_geometry(record, review) and not has_unresolved(review, branch_id, {"missing_area"}):
                errors.append(f"review_records[{label}] plane_region missing area/bbox without missing_area unresolved")
        elif branch_type == "via_cluster":
            if not has_width_geometry(record, review) and not has_unresolved(review, branch_id, {"missing_width", "missing_diameter", "missing_geometry"}):
                errors.append(f"review_records[{label}] via_cluster missing diameter/width without missing geometry unresolved")
        elif branch_type == "pad_group":
            if not has_area_or_bbox_geometry(record, review) and not has_unresolved(review, branch_id, {"missing_area", "missing_bbox", "missing_geometry"}):
                errors.append(f"review_records[{label}] pad_group missing bbox/area without missing geometry unresolved")

        stackup = stackup if isinstance(stackup, dict) else {}
        layer = record.get("layer") or stackup.get("primary_layer")
        drill_span_context = has_drill_or_via_span_context(record, review)
        missing_layer_marked = has_unresolved(review, branch_id, {"missing_layer"})
        if not layer and not missing_layer_marked and not drill_span_context:
            errors.append(f"review_records[{label}] branch layer missing without missing_layer unresolved")
        if layer and stackup.get("is_copper_layer") is False and not missing_layer_marked and not drill_span_context and not has_unresolved(review, branch_id, {"non_copper_layer"}):
            errors.append(f"review_records[{label}] non-copper layer without non_copper_layer unresolved")

    return errors, warnings


def check_evidence_records(review: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    evidence = review.get("evidence_records") if isinstance(review.get("evidence_records"), list) else []
    evidence_ids = id_values(evidence, "evidence_id")
    for duplicate in duplicate_values(evidence_ids):
        errors.append(f"duplicate evidence_id: {duplicate}")

    required = {"evidence_id", "branch_id", "net_name", "evidence_type", "source"}
    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence_records[{idx}] must be an object")
            continue
        label = item.get("evidence_id") or idx
        for key in sorted(required - set(item)):
            errors.append(f"evidence_records[{label}] missing required key: {key}")
        if item.get("source") not in EVIDENCE_SOURCES:
            errors.append(f"evidence_records[{label}].source invalid: {item.get('source')}")
        evidence_type = normalized_claim(item.get("evidence_type"))
        if evidence_type in FORBIDDEN_EVIDENCE_CLAIMS:
            errors.append(f"evidence_records[{label}] forbidden evidence claim: {evidence_type}")
        value = item.get("value")
        if isinstance(value, dict):
            for key in value:
                if normalized_claim(key) in FORBIDDEN_EVIDENCE_CLAIMS:
                    errors.append(f"evidence_records[{label}] forbidden evidence value key: {key}")

    return errors, warnings


def check_reference_integrity(review: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    evidence = review.get("evidence_records") if isinstance(review.get("evidence_records"), list) else []
    unresolved = review.get("unresolved") if isinstance(review.get("unresolved"), list) else []
    branch_ids = set(id_values(records, "branch_id"))
    evidence_ids = set(id_values(evidence, "evidence_id"))

    for item in evidence:
        if not isinstance(item, dict):
            continue
        branch_id = item.get("branch_id")
        if isinstance(branch_id, str) and branch_id not in branch_ids:
            errors.append(f"evidence_records[{item.get('evidence_id')}].branch_id dangling: {branch_id}")

    unresolved_ids = id_values(unresolved, "id")
    for duplicate in duplicate_values(unresolved_ids):
        warnings.append(f"duplicate unresolved id: {duplicate}")
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        branch_id = item.get("branch_id")
        if isinstance(branch_id, str) and branch_id not in branch_ids:
            errors.append(f"unresolved[{item.get('id')}].branch_id dangling: {branch_id}")

    for record in records:
        if not isinstance(record, dict):
            continue
        refs = record.get("evidence")
        if refs is None:
            continue
        if not isinstance(refs, list):
            errors.append(f"review_records[{record.get('review_id')}].evidence must be an array")
            continue
        for ref in refs:
            if isinstance(ref, str) and ref not in evidence_ids:
                errors.append(f"review_records[{record.get('review_id')}].evidence dangling: {ref}")

    return errors, warnings


def expected_geometry_incomplete_count(review: dict[str, Any]) -> int:
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    count = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        unresolved_types = unresolved_type_set(review, record.get("branch_id"))
        if record.get("review_status") == "geometry_incomplete" or unresolved_types.intersection(GEOMETRY_UNRESOLVED_TYPES):
            count += 1
    return count


def check_summary_consistency(review: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    evidence = review.get("evidence_records") if isinstance(review.get("evidence_records"), list) else []
    unresolved = review.get("unresolved") if isinstance(review.get("unresolved"), list) else []
    artifact_errors = review.get("errors") if isinstance(review.get("errors"), list) else []
    artifact_warnings = review.get("warnings") if isinstance(review.get("warnings"), list) else []

    checks = [
        ("review_record_count", len(records)),
        ("evidence_record_count", len(evidence)),
        ("unresolved_count", len(unresolved)),
        ("error_count", len(artifact_errors)),
        ("warning_count", len(artifact_warnings)),
        ("power_review_count", sum(1 for row in records if isinstance(row, dict) and row.get("topology_net_type") == "power")),
        ("power_branch_review_count", sum(1 for row in records if isinstance(row, dict) and row.get("topology_net_type") == "power")),
        (
            "current_unknown_power_count",
            sum(
                1
                for row in records
                if isinstance(row, dict)
                and row.get("topology_net_type") == "power"
                and isinstance(row.get("current_context"), dict)
                and row["current_context"].get("current_known") is False
            ),
        ),
        ("geometry_incomplete_count", expected_geometry_incomplete_count(review)),
        ("geometry_incomplete_branch_count", sum(1 for row in records if isinstance(row, dict) and row.get("review_status") == "geometry_incomplete")),
        ("missing_stackup_count", sum(1 for item in unresolved if isinstance(item, dict) and item.get("type") == "missing_layer")),
        ("non_copper_layer_count", sum(1 for item in unresolved if isinstance(item, dict) and item.get("type") == "non_copper_layer")),
    ]
    for key, expected in checks:
        if key in summary and summary.get(key) != expected:
            errors.append(f"summary.{key}={summary.get(key)} does not match expected {expected}")
    return errors, warnings


def add_human_review_item(items: dict[str, dict[str, Any]], record: dict[str, Any], item_type: str, notes: str) -> None:
    branch_id = str(record.get("branch_id") or "unknown")
    item_id = f"hr_{branch_id}_{item_type}"
    items[item_id] = {
        "id": item_id,
        "branch_id": record.get("branch_id"),
        "net_name": record.get("net_name"),
        "type": item_type,
        "notes": notes,
    }


def collect_human_review(review: dict[str, Any]) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    for record in records:
        if not isinstance(record, dict):
            continue
        branch_id = record.get("branch_id")
        branch_type = record.get("branch_type")
        context = record.get("current_context") if isinstance(record.get("current_context"), dict) else {}
        stackup = record.get("stackup") if isinstance(record.get("stackup"), dict) else {}
        unresolved_types = unresolved_type_set(review, branch_id)

        if record.get("topology_net_type") == "power" and context.get("current_known") is False:
            add_human_review_item(items, record, "current_unknown", "Power branch current is unknown.")
        if branch_type == "trace_group":
            if not has_width_geometry(record, review) or "missing_width" in unresolved_types:
                add_human_review_item(items, record, "missing_width", "Trace branch width evidence is missing.")
            if not has_length_geometry(record, review) or "missing_length" in unresolved_types:
                add_human_review_item(items, record, "missing_length", "Trace branch length evidence is missing.")
        elif branch_type == "plane_region":
            if not has_area_or_bbox_geometry(record, review) or "missing_area" in unresolved_types:
                add_human_review_item(items, record, "missing_area", "Plane branch area or bbox evidence is missing.")
        elif branch_type == "via_cluster":
            if not has_width_geometry(record, review) or unresolved_types.intersection({"missing_width", "missing_diameter", "missing_geometry"}):
                add_human_review_item(items, record, "missing_via_diameter", "Via cluster diameter or width evidence is missing.")
        elif branch_type == "pad_group":
            if not has_area_or_bbox_geometry(record, review) or unresolved_types.intersection({"missing_area", "missing_bbox", "missing_geometry"}):
                add_human_review_item(items, record, "missing_pad_geometry", "Pad group bbox or area evidence is missing.")
        elif branch_type in {"mixed_net_group", "unknown"}:
            add_human_review_item(items, record, "mixed_unknown_branch_type", "Branch type is mixed or unknown.")

        layer = record.get("layer") or stackup.get("primary_layer")
        drill_span_context = has_drill_or_via_span_context(record, review)
        missing_layer_marked = "missing_layer" in unresolved_types
        if (not layer or missing_layer_marked) and not drill_span_context:
            add_human_review_item(items, record, "missing_layer", "Stackup layer evidence is missing.")
        if layer and not missing_layer_marked and not drill_span_context and (stackup.get("is_copper_layer") is False or "non_copper_layer" in unresolved_types):
            add_human_review_item(items, record, "non_copper_layer", "Branch primary layer is not classified as copper.")

        flags = record.get("unresolved_flags")
        if isinstance(flags, list):
            for flag in sorted(flag for flag in flags if isinstance(flag, str) and flag.startswith("upstream_")):
                add_human_review_item(items, record, flag, f"Upstream unresolved flag is present: {flag}.")

    for item in review.get("unresolved", []) if isinstance(review.get("unresolved"), list) else []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if not isinstance(item_type, str) or not item_type.startswith("upstream_"):
            continue
        record = next((row for row in records if isinstance(row, dict) and row.get("branch_id") == item.get("branch_id")), {})
        if isinstance(record, dict):
            add_human_review_item(items, record, item_type, item.get("notes") or f"Upstream unresolved flag is present: {item_type}.")

    return [items[key] for key in sorted(items)]


def collect_strict_errors(review: dict[str, Any], human_review_needed: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    for record in records:
        if not isinstance(record, dict) or record.get("topology_net_type") != "power":
            continue
        branch_id = record.get("branch_id")
        context = record.get("current_context") if isinstance(record.get("current_context"), dict) else {}
        stackup = record.get("stackup") if isinstance(record.get("stackup"), dict) else {}
        branch_type = record.get("branch_type")
        if context.get("current_known") is False:
            errors.append(f"strict_mode: power branch current unknown: {branch_id}")
        if branch_type == "trace_group":
            if not has_width_geometry(record, review):
                errors.append(f"strict_mode: power trace branch missing width: {branch_id}")
            if not has_length_geometry(record, review):
                errors.append(f"strict_mode: power trace branch missing length: {branch_id}")
        elif branch_type == "plane_region":
            if not has_area_or_bbox_geometry(record, review):
                errors.append(f"strict_mode: power plane branch missing area/bbox: {branch_id}")
        elif branch_type == "via_cluster":
            if not has_width_geometry(record, review):
                errors.append(f"strict_mode: power via cluster missing diameter/width: {branch_id}")

        layer = record.get("layer") or stackup.get("primary_layer")
        drill_span_context = has_drill_or_via_span_context(record, review)
        if (not layer or has_unresolved(review, branch_id, {"missing_layer"})) and not drill_span_context:
            errors.append(f"strict_mode: power branch missing stackup layer: {branch_id}")
        elif stackup.get("is_copper_layer") is False and not drill_span_context:
            errors.append(f"strict_mode: power branch on non-copper layer: {branch_id}")

    human_types = {item.get("type") for item in human_review_needed}
    for required_type in sorted({"missing_layer", "non_copper_layer"} & human_types):
        if not any(required_type in error for error in errors):
            errors.append(f"strict_mode: {required_type} human review item present")
    return sorted(set(errors))


def build_summary(
    review: dict[str, Any],
    *,
    schema_error_count: int,
    consistency_error_count: int,
    warning_count: int,
    human_review_count: int,
) -> dict[str, int]:
    records = review.get("review_records") if isinstance(review.get("review_records"), list) else []
    evidence = review.get("evidence_records") if isinstance(review.get("evidence_records"), list) else []
    unresolved = review.get("unresolved") if isinstance(review.get("unresolved"), list) else []
    return {
        "review_record_count": len(records),
        "evidence_record_count": len(evidence),
        "unresolved_count": len(unresolved),
        "schema_error_count": schema_error_count,
        "consistency_error_count": consistency_error_count,
        "warning_count": warning_count,
        "human_review_item_count": human_review_count,
        "power_review_count": sum(1 for row in records if isinstance(row, dict) and row.get("topology_net_type") == "power"),
        "current_unknown_power_count": sum(
            1
            for row in records
            if isinstance(row, dict)
            and row.get("topology_net_type") == "power"
            and isinstance(row.get("current_context"), dict)
            and row["current_context"].get("current_known") is False
        ),
        "geometry_incomplete_count": expected_geometry_incomplete_count(review),
        "missing_stackup_count": sum(1 for item in unresolved if isinstance(item, dict) and item.get("type") == "missing_layer"),
        "non_copper_layer_count": sum(1 for item in unresolved if isinstance(item, dict) and item.get("type") == "non_copper_layer"),
    }


def validate_review(project: str, review_path: Path, *, strict: bool) -> dict[str, Any]:
    raw_review = load_json(review_path)
    review = raw_review if isinstance(raw_review, dict) else {}

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    shape_errors, shape_warnings = check_artifact_shape(raw_review)
    checks.append(check_row("artifact_shape", shape_errors, shape_warnings))
    errors.extend(f"artifact_shape: {error}" for error in shape_errors)
    warnings.extend(f"artifact_shape: {warning}" for warning in shape_warnings)

    review_errors, review_warnings = check_review_records(review)
    checks.append(check_row("review_records", review_errors, review_warnings))
    errors.extend(f"review_records: {error}" for error in review_errors)
    warnings.extend(f"review_records: {warning}" for warning in review_warnings)

    evidence_errors, evidence_warnings = check_evidence_records(review)
    checks.append(check_row("evidence_records", evidence_errors, evidence_warnings))
    errors.extend(f"evidence_records: {error}" for error in evidence_errors)
    warnings.extend(f"evidence_records: {warning}" for warning in evidence_warnings)

    reference_errors, reference_warnings = check_reference_integrity(review)
    checks.append(check_row("reference_integrity", reference_errors, reference_warnings))
    errors.extend(f"reference_integrity: {error}" for error in reference_errors)
    warnings.extend(f"reference_integrity: {warning}" for warning in reference_warnings)

    summary_errors, summary_warnings = check_summary_consistency(review)
    checks.append(check_row("summary_consistency", summary_errors, summary_warnings))
    errors.extend(f"summary_consistency: {error}" for error in summary_errors)
    warnings.extend(f"summary_consistency: {warning}" for warning in summary_warnings)

    human_review_needed = collect_human_review(review)
    checks.append(check_row("human_review", warnings=[f"{len(human_review_needed)} human review item(s)"]))

    deterministic_error_count = len(review_errors) + len(evidence_errors) + len(reference_errors) + len(summary_errors)
    artifact_validation_pass = not shape_errors
    geometry_consistency_pass = deterministic_error_count == 0
    unresolved_items_present = bool(review.get("unresolved")) or any(
        isinstance(row, dict) and bool(row.get("unresolved_flags"))
        for row in review.get("review_records", [])
        if isinstance(row, dict)
    )

    strict_errors = collect_strict_errors(review, human_review_needed) if strict else []
    if strict_errors:
        checks.append(check_row("strict_completeness", strict_errors))
        errors.extend(strict_errors)
    elif strict:
        checks.append(check_row("strict_completeness"))

    phase_gate_passed = artifact_validation_pass and geometry_consistency_pass and not strict_errors
    overall_pass = phase_gate_passed

    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "generated_at_utc": utc_now(),
        "sources": {
            "review": str(review_path),
        },
        "summary": build_summary(
            review,
            schema_error_count=len(shape_errors),
            consistency_error_count=deterministic_error_count,
            warning_count=len(warnings),
            human_review_count=len(human_review_needed),
        ),
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "human_review_needed": human_review_needed,
        "execution_pass": True,
        "artifact_validation_pass": artifact_validation_pass,
        "geometry_consistency_pass": geometry_consistency_pass,
        "unresolved_items_present": unresolved_items_present,
        "phase_gate_passed": phase_gate_passed,
        "overall_pass": overall_pass,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a topology-aware geometry review artifact.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--review", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = args.project
    review_path = Path(args.review or default_path("exports/{project}-topology-geometry-review.json", project))
    out_path = Path(args.out or default_path("exports/{project}-topology-geometry-validation.json", project))

    try:
        if not review_path.exists():
            raise FileNotFoundError(f"missing topology geometry review artifact: {review_path}")
        artifact = validate_review(project, review_path, strict=args.strict)
        write_json(out_path, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = artifact["summary"]
    print(
        "topology geometry validation: "
        f"artifact_pass={artifact['artifact_validation_pass']} "
        f"consistency_pass={artifact['geometry_consistency_pass']} "
        f"unresolved={summary['unresolved_count']} "
        f"human_review={summary['human_review_item_count']} "
        f"errors={len(artifact['errors'])} warnings={len(artifact['warnings'])} "
        f"out={out_path}"
    )
    return 0 if artifact["phase_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
