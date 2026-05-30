#!/usr/bin/env python3
"""Validate saved AI extraction responses for PR26 packets.

PR 27 scope only: validate raw_response.json artifacts against schema and
packet-aware semantic rules. This script does not call AI, generate prompts,
apply patches, mutate topology/current/rating/copper/margin artifacts, create
findings, or make compliance judgments.
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

import jsonschema


SCHEMA_VERSION = "ai_extraction_validation_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_extraction_result_schema.json"

SUPPORTED_TARGET_TYPES = {
    "component_current_model",
    "rail_current_model",
    "branch_current_model",
    "fuse_rating",
    "connector_pin_rating",
    "connector_rating",
    "regulator_rating",
    "load_switch_rating",
    "ferrite_rating",
    "capacitor_support_data",
    "component_role",
    "pin_role",
    "rail_relationship_hint",
    "pass_through_role",
    "human_review_note",
}

CURRENT_FIELDS = {
    "typ_current_a",
    "max_current_a",
    "idle_current_a",
    "sleep_current_a",
    "standby_current_a",
    "input_current_a",
    "output_current_a",
}
RATING_FIELDS = {
    "current_max",
    "pin_current_max",
    "output_current_max",
    "input_current_max",
    "continuous_current_max",
    "hold_current",
    "trip_current",
    "thermal_current_limit",
    "package_current_limit",
    "voltage_rating",
    "ripple_current",
    "esr",
    "impedance",
    "capacitance",
}
ROLE_FIELDS = {
    "component_role",
    "role_subtype",
    "pin_role",
    "pin_direction",
    "input_pin",
    "output_pin",
    "ground_pin",
    "feedback_pin",
    "enable_pin",
    "rail_relationship",
}
SUPPORTED_FIELD_NAMES = CURRENT_FIELDS | RATING_FIELDS | ROLE_FIELDS

SUPPORTED_UNITS = {
    "A",
    "mA",
    "uA",
    "µA",
    "V",
    "mV",
    "ohm",
    "mOhm",
    "Ω",
    "mΩ",
    "F",
    "uF",
    "µF",
    "nF",
    "pF",
    "Hz",
    "kHz",
    "MHz",
    "C",
    "degC",
    "ratio",
    "text",
}

FORBIDDEN_FIELDS = {
    "finding_id",
    "issue_id",
    "violation",
    "severity",
    "compliance_pass",
    "compliance_fail",
    "pass_fail",
    "margin_pass",
    "margin_fail",
    "acceptable",
    "unacceptable",
    "final_finding",
    "recommendation_severity",
}

FINAL_CALCULATION_KEYS = {
    "final_calculation",
    "calculation_result",
    "voltage_drop",
    "current_density",
    "margin_ratio",
    "utilization_ratio",
}
TOPOLOGY_MUTATION_KEYS = {
    "patch",
    "patches",
    "topology_patch",
    "mutate_topology",
    "current_model_patch",
    "rating_model_patch",
    "copper_patch",
    "margin_patch",
}

ACCEPTED_CONFIDENCE = 0.80
REVIEW_CONFIDENCE = 0.50


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    return value


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def stable_id(prefix: str, packet_id: str, source_id: Any, index: int) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(source_id or index)).strip("_") or f"{index:06d}"
    return f"{prefix}_{packet_id}_{text}"


def source_artifact(artifact_type: str, path: Path | None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path) if path else None}


def packet_index(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(packet.get("packet_id")): packet for packet in as_list(queue.get("packets")) if isinstance(packet, dict)}


def packet_missing_ids(packet_dir: Path, packet: dict[str, Any]) -> set[str]:
    ids = {str(value) for value in as_list(packet.get("missing_data_item_ids"))}
    context_path = packet_dir / str(packet.get("context_path") or f"packets/{packet['packet_id']}/context.json")
    if context_path.exists():
        context = load_json(context_path)
        if isinstance(context, dict):
            for item in as_list(context.get("missing_data_items")):
                if isinstance(item, dict):
                    value = item.get("manifest_id") or item.get("id") or item.get("source_missing_data_id")
                    if value:
                        ids.add(str(value))
    return ids


def walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(walk_keys(child))
    return keys


def first_forbidden_reason(value: Any) -> str | None:
    keys = walk_keys(value)
    if keys.intersection(FORBIDDEN_FIELDS):
        return "forbidden_output_field"
    if keys.intersection(FINAL_CALCULATION_KEYS):
        return "final_calculation_not_allowed"
    if keys.intersection(TOPOLOGY_MUTATION_KEYS):
        return "topology_mutation_not_allowed"
    return None


def normalize_unit(field_name: str, value: Any, unit: Any) -> tuple[Any, str | None, str | None]:
    if not isinstance(unit, str) or not unit:
        return None, None, "missing_unit"
    if unit not in SUPPORTED_UNITS:
        return None, None, "unsupported_unit"
    if field_name in CURRENT_FIELDS or field_name in {"current_max", "pin_current_max", "output_current_max", "input_current_max", "continuous_current_max", "hold_current", "trip_current", "thermal_current_limit", "package_current_limit", "ripple_current"}:
        factors = {"A": 1.0, "mA": 1e-3, "uA": 1e-6, "µA": 1e-6}
        if unit not in factors:
            return None, None, "unsupported_unit"
        return round(float(value) * factors[unit], 12) if is_number(value) else None, "A", None
    if field_name == "voltage_rating":
        factors = {"V": 1.0, "mV": 1e-3}
        if unit not in factors:
            return None, None, "unsupported_unit"
        return round(float(value) * factors[unit], 12) if is_number(value) else None, "V", None
    if field_name in {"esr", "impedance"}:
        factors = {"ohm": 1.0, "Ω": 1.0, "mOhm": 1e-3, "mΩ": 1e-3}
        if unit not in factors:
            return None, None, "unsupported_unit"
        return round(float(value) * factors[unit], 12) if is_number(value) else None, "ohm", None
    if field_name == "capacitance":
        if unit not in {"F", "uF", "µF", "nF", "pF"}:
            return None, None, "unsupported_unit"
        factors = {"F": 1.0, "uF": 1e-6, "µF": 1e-6, "nF": 1e-9, "pF": 1e-12}
        return round(float(value) * factors[unit], 12) if is_number(value) else None, "F", None
    if unit == "text":
        return str(value) if value is not None else "", "text", None
    return value, unit, None


def reject(packet_id: str, source_id: Any, reason_code: str, detail: str, original: Any, index: int) -> dict[str, Any]:
    return {
        "rejected_item_id": stable_id("rejected", packet_id, source_id, index),
        "packet_id": packet_id,
        "source_item_id": str(source_id or ""),
        "reason_code": reason_code,
        "detail": detail,
        "original_item": original,
    }


def human(packet_id: str, source_id: Any, reason_code: str, detail: str, candidate: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "human_review_item_id": stable_id("human", packet_id, source_id, index),
        "packet_id": packet_id,
        "source_item_id": str(source_id or ""),
        "reason_code": reason_code,
        "detail": detail,
        "candidate_item": candidate,
    }


def accepted(packet_id: str, source_id: Any, item: dict[str, Any], normalized_value: Any, normalized_unit: str, index: int) -> dict[str, Any]:
    return {
        "accepted_item_id": stable_id("accepted", packet_id, source_id, index),
        "packet_id": packet_id,
        "source_item_id": str(source_id or ""),
        "target_type": item.get("target_type"),
        "target_refdes": item.get("target_refdes"),
        "target_mpn": item.get("target_mpn"),
        "field_name": item.get("field_name"),
        "value": item.get("value"),
        "unit": item.get("unit"),
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "condition": item.get("condition"),
        "basis": item.get("basis"),
        "source_file": item.get("source_file"),
        "source_page": item.get("source_page"),
        "evidence_quote": item.get("evidence_quote") or item.get("evidence_ref"),
        "confidence": item.get("confidence"),
        "missing_data_item_ids": [str(value) for value in as_list(item.get("missing_data_item_ids"))],
        "usable_for_patch": True,
        "human_review_needed": False,
    }


def validate_item(packet_id: str, item: dict[str, Any], valid_missing_ids: set[str], strict: bool, index: int) -> tuple[str, dict[str, Any]]:
    source_id = item.get("item_id") or f"item_{index:06d}"
    forbidden_reason = first_forbidden_reason(item)
    if forbidden_reason:
        return "rejected", reject(packet_id, source_id, forbidden_reason, "AI output contains a forbidden field", item, index)
    ids = {str(value) for value in as_list(item.get("missing_data_item_ids"))}
    if not ids or not ids.issubset(valid_missing_ids):
        return "rejected", reject(packet_id, source_id, "unknown_missing_data_item", "item references missing-data IDs outside the packet", item, index)
    target_type = item.get("target_type")
    if target_type not in SUPPORTED_TARGET_TYPES:
        return "rejected", reject(packet_id, source_id, "unsupported_target_type", f"unsupported target_type: {target_type}", item, index)
    field_name = item.get("field_name")
    if field_name not in SUPPORTED_FIELD_NAMES:
        return "rejected", reject(packet_id, source_id, "unsupported_field_name", f"unsupported field_name: {field_name}", item, index)
    value = item.get("value")
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    if numeric and not math.isfinite(float(value)):
        return "rejected", reject(packet_id, source_id, "invalid_numeric_value", "numeric value is NaN or Infinity", item, index)
    normalized_value, normalized_unit, unit_error = normalize_unit(str(field_name), value, item.get("unit"))
    if unit_error:
        return "rejected", reject(packet_id, source_id, unit_error, unit_error.replace("_", " "), item, index)
    if is_number(value) and float(value) < 0 and (field_name in CURRENT_FIELDS or field_name in RATING_FIELDS):
        return "rejected", reject(packet_id, source_id, "negative_current_or_rating", "current/rating value must not be negative", item, index)
    basis = str(item.get("basis") or "")
    if basis == "datasheet" and not item.get("source_file"):
        return "rejected", reject(packet_id, source_id, "missing_source_file", "datasheet-sourced item must include source_file", item, index)
    evidence = item.get("evidence_quote") or item.get("evidence_ref")
    if not evidence:
        if strict or numeric:
            return "rejected", reject(packet_id, source_id, "missing_evidence", "item must include evidence_quote or evidence_ref", item, index)
        return "human", human(packet_id, source_id, "ambiguous_source", "item lacks evidence quote/ref", item, index)
    confidence = item.get("confidence")
    if not is_number(confidence):
        return "rejected", reject(packet_id, source_id, "schema_validation_failed", "confidence must be a finite number", item, index)
    if float(confidence) < REVIEW_CONFIDENCE:
        return "rejected", reject(packet_id, source_id, "confidence_too_low", "confidence is below rejection threshold", item, index)
    if item.get("multiple_candidate_values"):
        return "human", human(packet_id, source_id, "multiple_candidate_values", "multiple candidate values require review", item, index)
    current_related = field_name in CURRENT_FIELDS
    simple_rating = field_name in {"current_max", "pin_current_max", "hold_current", "trip_current", "continuous_current_max", "thermal_current_limit", "package_current_limit", "voltage_rating", "ripple_current"}
    if current_related and not item.get("condition"):
        return "human", human(packet_id, source_id, "ambiguous_condition", "current extraction lacks operating condition", item, index)
    if is_number(value) and not item.get("source_page"):
        return "human", human(packet_id, source_id, "source_page_missing", "numeric value has source_file/evidence but no source_page", item, index)
    if normalized_unit == "text" and field_name in ROLE_FIELDS:
        if float(confidence) >= ACCEPTED_CONFIDENCE and evidence:
            return "accepted", accepted(packet_id, source_id, item, normalized_value, normalized_unit, index)
        return "human", human(packet_id, source_id, "role_requires_confirmation", "role/pin text extraction requires confirmation", item, index)
    if normalized_unit == "text":
        return "human", human(packet_id, source_id, "text_value_requires_review", "text value cannot be used directly for patching", item, index)
    if float(confidence) < ACCEPTED_CONFIDENCE:
        return "human", human(packet_id, source_id, "medium_confidence", "confidence is below acceptance threshold", item, index)
    if current_related and not item.get("condition"):
        return "human", human(packet_id, source_id, "ambiguous_condition", "current extraction lacks operating condition", item, index)
    if not simple_rating and field_name in RATING_FIELDS and not item.get("condition") and field_name in {"input_current_a", "output_current_a"}:
        return "human", human(packet_id, source_id, "ambiguous_condition", "rating condition is ambiguous", item, index)
    return "accepted", accepted(packet_id, source_id, item, normalized_value, normalized_unit or str(item.get("unit")), index)


def packet_status(packet_result: dict[str, Any], has_response: bool, strict: bool) -> str:
    if not has_response:
        return "validation_failed" if strict else "pending"
    if packet_result["errors"]:
        return "validation_failed"
    if packet_result["rejected_item_ids"]:
        return "rejected"
    if packet_result["human_review_item_ids"]:
        return "human_review_needed"
    return "accepted"


def validate_packet(packet_dir: Path, packet: dict[str, Any], schema: dict[str, Any], strict: bool) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    packet_id = str(packet["packet_id"])
    raw_path = packet_dir / "packets" / packet_id / "raw_response.json"
    result = {
        "packet_id": packet_id,
        "stage_id": packet.get("stage_id"),
        "packet_type": packet.get("packet_type"),
        "target_type": packet.get("target_type"),
        "status": "pending",
        "raw_response_path": str(raw_path),
        "validated_result_path": None,
        "accepted_item_ids": [],
        "rejected_item_ids": [],
        "human_review_item_ids": [],
        "errors": [],
        "warnings": [],
    }
    accepted_items: list[dict[str, Any]] = []
    rejected_items: list[dict[str, Any]] = []
    human_items: list[dict[str, Any]] = []
    unknown_items: list[dict[str, Any]] = []
    if not raw_path.exists():
        result["warnings"].append("raw_response_missing")
        if strict:
            result["errors"].append("raw_response_missing")
        result["status"] = packet_status(result, False, strict)
        return result, accepted_items, rejected_items, human_items, unknown_items

    try:
        response = load_json(raw_path)
    except Exception as exc:
        result["errors"].append(f"malformed_json: {exc}")
        rejected_items.append(reject(packet_id, "raw_response", "malformed_json", "raw_response.json is not valid JSON", {}, 0))
        result["rejected_item_ids"] = [rejected_items[-1]["rejected_item_id"]]
        result["status"] = "validation_failed"
        return result, accepted_items, rejected_items, human_items, unknown_items
    if not isinstance(response, dict):
        result["errors"].append("schema_validation_failed: raw response must be a JSON object")
        result["status"] = "validation_failed"
        return result, accepted_items, rejected_items, human_items, unknown_items
    forbidden_reason = first_forbidden_reason(response)
    if forbidden_reason:
        result["errors"].append(forbidden_reason)
        rejected_items.append(reject(packet_id, "raw_response", forbidden_reason, "AI response contains a forbidden field", response, 0))
    try:
        jsonschema.validate(instance=response, schema=schema)
    except jsonschema.ValidationError as exc:
        result["errors"].append(f"schema_validation_failed: {exc.message}")
    if response.get("packet_id") != packet_id:
        result["errors"].append("packet_id_mismatch")
        rejected_items.append(reject(packet_id, response.get("packet_id"), "packet_id_mismatch", "response packet_id does not match packet directory", response, 0))
    valid_missing_ids = packet_missing_ids(packet_dir, packet)
    for index, item in enumerate(as_list(response.get("extracted_items")), start=1):
        if not isinstance(item, dict):
            rejected_items.append(reject(packet_id, f"item_{index}", "schema_validation_failed", "extracted item must be an object", item, index))
            continue
        bucket, row = validate_item(packet_id, item, valid_missing_ids, strict, index)
        if bucket == "accepted":
            accepted_items.append(row)
        elif bucket == "human":
            human_items.append(row)
        else:
            rejected_items.append(row)
    for index, item in enumerate(as_list(response.get("unknown_items")), start=1):
        if isinstance(item, dict):
            unknown_items.append({"packet_id": packet_id, **item})
    result["accepted_item_ids"] = [row["accepted_item_id"] for row in accepted_items]
    result["rejected_item_ids"] = [row["rejected_item_id"] for row in rejected_items]
    result["human_review_item_ids"] = [row["human_review_item_id"] for row in human_items]
    result["status"] = packet_status(result, True, strict)
    return result, accepted_items, rejected_items, human_items, unknown_items


def classify_item(row: dict[str, Any]) -> str:
    target_type = str(row.get("target_type") or "")
    field_name = str(row.get("field_name") or "")
    if field_name in CURRENT_FIELDS or target_type.endswith("current_model"):
        return "current"
    if field_name in ROLE_FIELDS or target_type in {"component_role", "pin_role", "rail_relationship_hint", "pass_through_role"}:
        return "role"
    if target_type == "capacitor_support_data" or field_name in {"esr", "impedance", "ripple_current", "voltage_rating", "capacitance"}:
        return "passive"
    if field_name in RATING_FIELDS or "rating" in target_type:
        return "rating"
    return "other"


def build_summary(packet_results: list[dict[str, Any]], accepted_items: list[dict[str, Any]], rejected_items: list[dict[str, Any]], human_items: list[dict[str, Any]], unknown_items: list[dict[str, Any]], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    reject_reasons = [row.get("reason_code") for row in rejected_items]
    human_reasons = [row.get("reason_code") for row in human_items]
    accepted_kinds = [classify_item(row) for row in accepted_items]
    return {
        "packet_count": len(packet_results),
        "packet_with_response_count": sum(1 for row in packet_results if Path(str(row["raw_response_path"])).exists()),
        "pending_packet_count": sum(1 for row in packet_results if row["status"] == "pending"),
        "accepted_packet_count": sum(1 for row in packet_results if row["status"] == "accepted"),
        "rejected_packet_count": sum(1 for row in packet_results if row["status"] == "rejected"),
        "human_review_packet_count": sum(1 for row in packet_results if row["status"] == "human_review_needed"),
        "validation_failed_packet_count": sum(1 for row in packet_results if row["status"] == "validation_failed"),
        "accepted_item_count": len(accepted_items),
        "rejected_item_count": len(rejected_items),
        "human_review_item_count": len(human_items),
        "unknown_item_count": len(unknown_items),
        "current_model_item_count": accepted_kinds.count("current"),
        "rating_item_count": accepted_kinds.count("rating"),
        "role_pin_item_count": accepted_kinds.count("role"),
        "passive_support_item_count": accepted_kinds.count("passive"),
        "forbidden_output_count": reject_reasons.count("forbidden_output_field"),
        "missing_evidence_count": reject_reasons.count("missing_evidence") + human_reasons.count("ambiguous_source"),
        "unsupported_unit_count": reject_reasons.count("unsupported_unit"),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def update_packet_status(packet_dir: Path, packet_result: dict[str, Any], out_path: Path) -> None:
    status_path = packet_dir / "packets" / packet_result["packet_id"] / "status.json"
    status = load_json(status_path) if status_path.exists() else {"packet_id": packet_result["packet_id"]}
    if not isinstance(status, dict):
        status = {"packet_id": packet_result["packet_id"]}
    status["status"] = packet_result["status"]
    status["raw_response_path"] = packet_result["raw_response_path"] if Path(str(packet_result["raw_response_path"])).exists() else None
    status["validated_result_path"] = str(out_path)
    status["errors"] = packet_result["errors"]
    status["warnings"] = packet_result["warnings"]
    write_json(status_path, status)


def validate_all(project: str, packet_dir: Path, out_path: Path, schema_path: Path, packet_id: str | None, strict: bool, update_status: bool) -> dict[str, Any]:
    if not packet_dir.exists():
        raise FileNotFoundError(f"missing packet directory: {packet_dir}")
    queue_path = packet_dir / "packet_queue.json"
    if not queue_path.exists():
        raise FileNotFoundError(f"missing packet_queue.json: {queue_path}")
    queue = load_json(queue_path)
    if not isinstance(queue, dict):
        raise ValueError(f"packet_queue.json must be a JSON object: {queue_path}")
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    packets = packet_index(queue)
    if packet_id and packet_id not in packets:
        raise ValueError(f"unknown packet-id: {packet_id}")
    selected = [packets[packet_id]] if packet_id else [packets[key] for key in sorted(packets)]

    packet_results: list[dict[str, Any]] = []
    accepted_items: list[dict[str, Any]] = []
    rejected_items: list[dict[str, Any]] = []
    human_items: list[dict[str, Any]] = []
    unknown_items: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for packet in selected:
        result, accepted_rows, rejected_rows, human_rows, unknown_rows = validate_packet(packet_dir, packet, schema, strict)
        packet_results.append(result)
        accepted_items.extend(accepted_rows)
        rejected_items.extend(rejected_rows)
        human_items.extend(human_rows)
        unknown_items.extend(unknown_rows)
        errors.extend(f"{result['packet_id']}: {error}" for error in result["errors"])
        warnings.extend(f"{result['packet_id']}: {warning}" for warning in result["warnings"])
        if update_status:
            update_packet_status(packet_dir, result, out_path)

    summary = build_summary(packet_results, accepted_items, rejected_items, human_items, unknown_items, errors, warnings)
    artifact = {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": [
            source_artifact("packet_queue", queue_path),
            source_artifact("ai_extraction_result_schema", schema_path),
        ],
        "packet_dir": str(packet_dir),
        "validation_pass": not errors and (not strict or summary["pending_packet_count"] == 0),
        "packet_results": packet_results,
        "accepted_items": accepted_items,
        "rejected_items": rejected_items,
        "human_review_items": human_items,
        "pending_packets": [
            {
                "packet_id": row["packet_id"],
                "reason_code": "raw_response_missing" if "raw_response_missing" in row["warnings"] else "packet_not_run",
                "detail": "raw_response.json is not present",
            }
            for row in packet_results
            if row["status"] == "pending"
        ],
        "unknown_items": unknown_items,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    return artifact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate saved AI extraction responses for packetized data completion.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--packet-id", default=None)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-packet-status", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        artifact = validate_all(
            project=args.project,
            packet_dir=Path(args.packet_dir),
            out_path=Path(args.out),
            schema_path=Path(args.schema),
            packet_id=args.packet_id,
            strict=args.strict,
            update_status=args.update_packet_status,
        )
        write_json(Path(args.out), artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = artifact["summary"]
    print(
        "ai extraction validate: "
        f"project={artifact['project']} packets={summary['packet_count']} "
        f"responses={summary['packet_with_response_count']} accepted={summary['accepted_item_count']} "
        f"rejected={summary['rejected_item_count']} human={summary['human_review_item_count']} "
        f"pending={summary['pending_packet_count']} errors={summary['error_count']} warnings={summary['warning_count']} "
        f"out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
