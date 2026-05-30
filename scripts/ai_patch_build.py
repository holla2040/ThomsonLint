#!/usr/bin/env python3
"""Build deterministic candidate patch bundles from AI extraction validation.

PR 28 scope only: convert PR27 accepted_items into reviewable patch candidate
artifacts. This script does not call AI, apply patches, mutate core artifacts,
rerun calculations, create findings, or make pass/fail/compliance judgments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_VERSION = "ai_patch_bundle_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_patch_schema.json"
DEFAULT_SOURCE_PRIORITY = "ai_validated_datasheet"

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
}
PASSIVE_FIELDS = {"ripple_current", "esr", "impedance", "capacitance"}
ROLE_FIELDS = {"component_role", "role_subtype"}
PIN_FIELDS = {"pin_role", "pin_direction", "input_pin", "output_pin", "ground_pin", "feedback_pin", "enable_pin"}
RAIL_FIELDS = {"rail_relationship"}

CURRENT_TARGET_TYPES = {"component_current_model", "rail_current_model", "branch_current_model"}
RATING_TARGET_TYPES = {"fuse_rating", "connector_pin_rating", "connector_rating", "regulator_rating", "load_switch_rating", "ferrite_rating"}
ROLE_TARGET_TYPES = {"component_role", "pass_through_role"}
PIN_TARGET_TYPES = {"pin_role"}
RAIL_TARGET_TYPES = {"rail_relationship_hint"}
PASSIVE_TARGET_TYPES = {"capacitor_support_data"}

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
    "apply_to_artifact",
    "mutate_artifact",
    "overwrite",
    "delete_existing",
    "replace_existing",
}

CORE_ARTIFACT_NAMES = [
    "current-models-normalized",
    "rating-models-normalized",
    "topology-current-allocation",
    "topology-copper-calculations",
    "topology-margin-calculations",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def source_artifact(artifact_type: str, path: Path | None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path) if path else None}


def safe_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_")
    return text or "unknown"


def digest_id(*values: Any) -> str:
    payload = json.dumps([json_safe(value) for value in values], sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def stable_patch_id(item: dict[str, Any], patch_class: str) -> str:
    return "patch_" + "_".join(
        [
            safe_id(patch_class),
            safe_id(item.get("target_type")),
            safe_id(item.get("target_refdes") or item.get("target_mpn")),
            safe_id(item.get("field_name")),
            digest_id(item.get("packet_id"), item.get("source_item_id"), item.get("accepted_item_id") or item.get("human_review_item_id")),
        ]
    )


def stable_skipped_id(item: dict[str, Any], reason: str, index: int) -> str:
    return f"skipped_{safe_id(reason)}_{digest_id(item.get('accepted_item_id'), item.get('human_review_item_id'), index)}"


def stable_conflict_id(key: tuple[Any, ...], reason: str) -> str:
    return f"conflict_{safe_id(reason)}_{digest_id(*key)}"


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


def sanitize_for_output(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize_for_output(child) for key, child in value.items() if str(key) not in FORBIDDEN_FIELDS}
    if isinstance(value, list):
        return [sanitize_for_output(child) for child in value]
    return json_safe(value)


def patch_class_for(item: dict[str, Any], human_review: bool = False) -> str | None:
    if human_review:
        return "human_review_patch_candidate"
    target_type = str(item.get("target_type") or "")
    field_name = str(item.get("field_name") or "")
    if target_type in CURRENT_TARGET_TYPES and field_name in CURRENT_FIELDS:
        return "current_model_patch"
    if target_type == "ferrite_rating" and field_name in {"impedance", "esr"}:
        return "passive_support_data_patch"
    if target_type in RATING_TARGET_TYPES and field_name in RATING_FIELDS:
        return "rating_model_patch"
    if target_type in PASSIVE_TARGET_TYPES and field_name in PASSIVE_FIELDS | {"voltage_rating"}:
        return "passive_support_data_patch"
    if target_type in ROLE_TARGET_TYPES and field_name in ROLE_FIELDS:
        return "role_resolution_addendum"
    if target_type in PIN_TARGET_TYPES and field_name in PIN_FIELDS:
        return "pin_role_addendum"
    if target_type in RAIL_TARGET_TYPES and field_name in RAIL_FIELDS:
        return "rail_relationship_hint"
    if target_type not in CURRENT_TARGET_TYPES | RATING_TARGET_TYPES | ROLE_TARGET_TYPES | PIN_TARGET_TYPES | RAIL_TARGET_TYPES | PASSIVE_TARGET_TYPES:
        return None
    return None


def skip_item(item: dict[str, Any], reason: str, detail: str, index: int) -> dict[str, Any]:
    return {
        "skipped_item_id": stable_skipped_id(item, reason, index),
        "source_accepted_item_id": item.get("accepted_item_id") or item.get("human_review_item_id"),
        "reason_code": reason,
        "detail": detail,
        "original_item": sanitize_for_output(item),
    }


def required_identity_missing(item: dict[str, Any]) -> bool:
    return not (item.get("target_refdes") or item.get("target_mpn"))


def is_numeric_patch(item: dict[str, Any]) -> bool:
    value = item.get("value")
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def source_evidence_missing(item: dict[str, Any]) -> bool:
    return not (item.get("source_file") and (item.get("evidence_quote") or item.get("evidence_ref")))


def item_for_human_review(row: dict[str, Any]) -> dict[str, Any]:
    candidate = row.get("candidate_item")
    if isinstance(candidate, dict):
        item = dict(candidate)
    else:
        item = dict(row)
    item.setdefault("packet_id", row.get("packet_id"))
    item.setdefault("source_item_id", row.get("source_item_id"))
    item["human_review_item_id"] = row.get("human_review_item_id")
    item["human_review_needed"] = True
    item.setdefault("usable_for_patch", False)
    return item


def patch_from_item(item: dict[str, Any], patch_class: str, validation_artifact: Path, source_priority: str, human_review: bool) -> dict[str, Any]:
    accepted_id = str(item.get("accepted_item_id") or item.get("human_review_item_id") or "")
    source_item_id = str(item.get("source_item_id") or "")
    packet_id = str(item.get("packet_id") or "")
    basis = source_priority if not human_review else "human_review_candidate"
    source_page = item.get("source_page")
    if source_page is not None:
        source_page = int(source_page)
    patch = {
        "patch_id": stable_patch_id(item, patch_class),
        "patch_class": patch_class,
        "operation": "add_candidate",
        "target_type": item.get("target_type"),
        "target_refdes": item.get("target_refdes"),
        "target_mpn": item.get("target_mpn"),
        "field_name": item.get("field_name"),
        "value": item.get("value"),
        "unit": item.get("unit"),
        "normalized_value": item.get("normalized_value"),
        "normalized_unit": item.get("normalized_unit"),
        "condition": item.get("condition"),
        "basis": basis,
        "source_packet_id": packet_id,
        "source_item_id": source_item_id,
        "source_accepted_item_id": accepted_id,
        "source_item_ids": [source_item_id] if source_item_id else [],
        "source_accepted_item_ids": [accepted_id] if accepted_id else [],
        "missing_data_item_ids": [str(value) for value in as_list(item.get("missing_data_item_ids"))],
        "source_file": item.get("source_file"),
        "source_page": source_page,
        "evidence_quote": item.get("evidence_quote") or item.get("evidence_ref"),
        "confidence": item.get("confidence"),
        "human_review_needed": bool(human_review or item.get("human_review_needed")),
        "usable_for_ingestion": not human_review,
        "requires_human_approval_before_ingestion": bool(human_review),
        "provenance": {
            "validation_artifact": str(validation_artifact),
            "packet_id": packet_id,
            "source_item_id": source_item_id,
            "source_accepted_item_id": accepted_id,
            "basis": basis,
        },
        "warnings": [],
    }
    return patch


def validate_item_for_patch(item: dict[str, Any], patch_class: str | None, index: int, human_review: bool) -> dict[str, Any] | None:
    if walk_keys(item).intersection(FORBIDDEN_FIELDS):
        return skip_item(item, "unsupported_field_name", "source item contains forbidden output fields", index)
    if not human_review and item.get("usable_for_patch") is False:
        return skip_item(item, "not_usable_for_patch", "source item is not usable for patch", index)
    if patch_class is None:
        target_type = str(item.get("target_type") or "")
        known_targets = CURRENT_TARGET_TYPES | RATING_TARGET_TYPES | ROLE_TARGET_TYPES | PIN_TARGET_TYPES | RAIL_TARGET_TYPES | PASSIVE_TARGET_TYPES
        if target_type not in known_targets:
            return skip_item(item, "unsupported_target_type", f"unsupported target_type: {target_type}", index)
        return skip_item(item, "unsupported_field_name", f"field cannot be mapped to patch class: {item.get('field_name')}", index)
    if required_identity_missing(item):
        return skip_item(item, "missing_target_identity", "target_refdes or target_mpn is required", index)
    if source_evidence_missing(item):
        return skip_item(item, "missing_evidence", "source_file and evidence_quote/evidence_ref are required", index)
    if is_numeric_patch(item) and item.get("normalized_value") is None:
        return skip_item(item, "missing_normalized_value", "numeric patch candidate requires normalized_value", index)
    if is_numeric_patch(item) and item.get("normalized_unit") is None:
        return skip_item(item, "missing_normalized_unit", "numeric patch candidate requires normalized_unit", index)
    return None


def merge_identical_patches(patches: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    warnings: list[str] = []
    for patch in patches:
        key = (
            patch["patch_class"],
            patch["target_type"],
            patch["target_refdes"],
            patch["target_mpn"],
            patch["field_name"],
            patch["normalized_value"],
            patch["normalized_unit"],
            patch["condition"],
            patch["source_file"],
            patch["source_page"],
            patch["evidence_quote"],
        )
        if key not in merged:
            merged[key] = patch
            continue
        existing = merged[key]
        existing["source_item_ids"] = sorted(set(existing["source_item_ids"] + patch["source_item_ids"]))
        existing["source_accepted_item_ids"] = sorted(set(existing["source_accepted_item_ids"] + patch["source_accepted_item_ids"]))
        existing["missing_data_item_ids"] = sorted(set(existing["missing_data_item_ids"] + patch["missing_data_item_ids"]))
        existing["warnings"] = sorted(set(existing["warnings"] + ["duplicate_identical_candidate"]))
        warnings.append(f"duplicate identical candidate deduplicated into {existing['patch_id']}")
    return sorted(merged.values(), key=lambda row: row["patch_id"]), warnings


def conflict_group_key(patch: dict[str, Any]) -> tuple[Any, ...]:
    return (patch["patch_class"], patch["target_type"], patch["target_refdes"], patch["target_mpn"], patch["field_name"])


def conflict_reason(patches: list[dict[str, Any]]) -> str:
    units = {str(patch.get("normalized_unit")) for patch in patches}
    values = {json.dumps(patch.get("normalized_value"), sort_keys=True) for patch in patches}
    conditions = {str(patch.get("condition")) for patch in patches}
    if len(units) > 1:
        return "conflicting_units"
    if len(conditions) > 1:
        return "conflicting_conditions"
    if len(values) > 1:
        return "conflicting_candidate_values"
    return "conflicting_candidate_values"


def mark_conflicts(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for patch in patches:
        if patch["patch_class"] == "human_review_patch_candidate":
            continue
        grouped.setdefault(conflict_group_key(patch), []).append(patch)
    conflicts: list[dict[str, Any]] = []
    by_id = {patch["patch_id"]: patch for patch in patches}
    for key, rows in sorted(grouped.items(), key=lambda item: item[0]):
        if len(rows) <= 1:
            continue
        reason = conflict_reason(rows)
        ids = sorted(row["patch_id"] for row in rows)
        for patch_id in ids:
            by_id[patch_id]["usable_for_ingestion"] = False
            by_id[patch_id]["requires_human_approval_before_ingestion"] = True
            by_id[patch_id]["human_review_needed"] = True
            by_id[patch_id]["warnings"] = sorted(set(by_id[patch_id]["warnings"] + [reason]))
        conflicts.append(
            {
                "conflict_id": stable_conflict_id(key, reason),
                "reason_code": reason,
                "target_type": rows[0]["target_type"],
                "target_refdes": rows[0]["target_refdes"],
                "field_name": rows[0]["field_name"],
                "candidate_patch_ids": ids,
                "detail": f"Conflicting AI patch candidates require human review for {rows[0]['target_type']} {rows[0]['target_refdes']} {rows[0]['field_name']}.",
                "human_review_needed": True,
            }
        )
    return conflicts


def build_summary(validation: dict[str, Any], patches: list[dict[str, Any]], conflicts: list[dict[str, Any]], skipped: list[dict[str, Any]], human_review_items: list[dict[str, Any]], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "source_accepted_item_count": len(as_list(validation.get("accepted_items"))),
        "source_rejected_item_count": len(as_list(validation.get("rejected_items"))),
        "source_human_review_item_count": len(as_list(validation.get("human_review_items"))),
        "patch_count": len(patches),
        "current_model_patch_count": sum(1 for patch in patches if patch["patch_class"] == "current_model_patch"),
        "rating_model_patch_count": sum(1 for patch in patches if patch["patch_class"] == "rating_model_patch"),
        "role_resolution_addendum_count": sum(1 for patch in patches if patch["patch_class"] == "role_resolution_addendum"),
        "pin_role_addendum_count": sum(1 for patch in patches if patch["patch_class"] == "pin_role_addendum"),
        "rail_relationship_hint_count": sum(1 for patch in patches if patch["patch_class"] == "rail_relationship_hint"),
        "passive_support_data_patch_count": sum(1 for patch in patches if patch["patch_class"] == "passive_support_data_patch"),
        "human_review_patch_candidate_count": sum(1 for patch in patches if patch["patch_class"] == "human_review_patch_candidate"),
        "skipped_item_count": len(skipped),
        "conflict_count": len(conflicts),
        "usable_for_ingestion_count": sum(1 for patch in patches if patch["usable_for_ingestion"]),
        "requires_human_approval_count": sum(1 for patch in patches if patch["requires_human_approval_before_ingestion"]),
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


def build_bundle(
    *,
    project: str,
    validation_path: Path,
    source_priority: str,
    include_human_review: bool,
) -> dict[str, Any]:
    validation = load_json(validation_path)
    if not isinstance(validation, dict):
        raise ValueError(f"validation artifact must be a JSON object: {validation_path}")
    errors: list[str] = []
    warnings: list[str] = []
    skipped: list[dict[str, Any]] = []
    human_review_items = as_list(validation.get("human_review_items"))
    patches: list[dict[str, Any]] = []

    for index, item in enumerate(as_list(validation.get("accepted_items")), start=1):
        if not isinstance(item, dict):
            continue
        patch_class = patch_class_for(item)
        skip = validate_item_for_patch(item, patch_class, index, False)
        if skip:
            skipped.append(skip)
            continue
        patches.append(patch_from_item(item, str(patch_class), validation_path, source_priority, False))

    if include_human_review:
        base_index = len(as_list(validation.get("accepted_items"))) + 1
        for offset, row in enumerate(human_review_items):
            if not isinstance(row, dict):
                continue
            item = item_for_human_review(row)
            patch_class = patch_class_for(item, human_review=True)
            skip = validate_item_for_patch(item, patch_class, base_index + offset, True)
            if skip:
                skipped.append(skip)
                continue
            patches.append(patch_from_item(item, str(patch_class), validation_path, source_priority, True))
    else:
        for index, row in enumerate(human_review_items, start=1):
            if isinstance(row, dict):
                skipped.append(skip_item(row, "human_review_not_included", "human review item omitted by default", index))

    patches, dedupe_warnings = merge_identical_patches(patches)
    warnings.extend(dedupe_warnings)
    conflicts = mark_conflicts(patches)
    summary = build_summary(validation, patches, conflicts, skipped, human_review_items, errors, warnings)
    return {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": [
            source_artifact("ai_extraction_validation", validation_path),
            *[source_artifact(str(row.get("artifact_type") or "source"), Path(row["path"]) if row.get("path") else None) for row in as_list(validation.get("source_artifacts")) if isinstance(row, dict)],
        ],
        "source_validation_artifact": str(validation_path),
        "patch_bundle_pass": not errors,
        "patches": patches,
        "conflicts": conflicts,
        "skipped_items": skipped,
        "human_review_items": sanitize_for_output(human_review_items) if include_human_review else [],
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


def validate_bundle_schema(bundle: dict[str, Any], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate(instance=bundle, schema=schema)
    keys = walk_keys(bundle)
    forbidden = sorted(keys.intersection(FORBIDDEN_FIELDS))
    if forbidden:
        raise ValueError(f"patch bundle contains forbidden field(s): {', '.join(forbidden)}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic AI patch candidate bundle.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-human-review", action="store_true")
    parser.add_argument("--source-priority", default=DEFAULT_SOURCE_PRIORITY)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validation_path = Path(args.validation)
    out_path = Path(args.out)
    try:
        if not validation_path.exists():
            raise FileNotFoundError(f"missing validation artifact: {validation_path}")
        bundle = build_bundle(
            project=args.project,
            validation_path=validation_path,
            source_priority=args.source_priority,
            include_human_review=args.include_human_review,
        )
        if args.strict and bundle["skipped_items"]:
            bundle["errors"].append("strict mode disallows skipped items")
            bundle["summary"] = build_summary(load_json(validation_path), bundle["patches"], bundle["conflicts"], bundle["skipped_items"], bundle["human_review_items"], bundle["errors"], bundle["warnings"])
            bundle["patch_bundle_pass"] = False
        validate_bundle_schema(bundle, Path(args.schema))
        write_json(out_path, bundle)
        if args.out_dir:
            out_dir = Path(args.out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            for patch in bundle["patches"]:
                write_json(out_dir / f"{patch['patch_id']}.json", patch)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = bundle["summary"]
    print(
        "ai patch build: "
        f"project={bundle['project']} patches={summary['patch_count']} usable={summary['usable_for_ingestion_count']} "
        f"conflicts={summary['conflict_count']} skipped={summary['skipped_item_count']} "
        f"errors={summary['error_count']} warnings={summary['warning_count']} out={out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
