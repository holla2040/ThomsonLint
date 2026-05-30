#!/usr/bin/env python3
"""Materialize isolated AI candidate input files from patch bundles.

PR 29 scope only: convert PR28 patch bundles into reviewable candidate input
files. This script does not call AI, apply patches, overwrite normalized/core
artifacts, run ingestion, run calculations, create findings, or make
pass/fail/compliance judgments.
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


SCHEMA_VERSION = "ai_candidate_inputs_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_candidate_inputs_schema.json"
DEFAULT_SOURCE_PRIORITY = "ai_validated_datasheet"

CURRENT_FIELDS = {"typ_current_a", "max_current_a", "idle_current_a", "sleep_current_a", "standby_current_a", "input_current_a", "output_current_a"}
CURRENT_RATING_FIELDS = {"current_max", "pin_current_max", "output_current_max", "input_current_max", "continuous_current_max", "hold_current", "trip_current", "thermal_current_limit", "package_current_limit"}
PASSIVE_FIELDS = {"esr", "impedance", "ripple_current", "voltage_rating", "capacitance"}

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

CORE_ARTIFACT_FILENAMES = {
    "{project}-current-models-normalized.json",
    "{project}-rating-models-normalized.json",
    "{project}-topology-current-allocation.json",
    "{project}-topology-copper-calculations.json",
    "{project}-topology-margin-calculations.json",
}

CANDIDATE_FILES = {
    "current_model_candidates": "ai-current-model-candidates.json",
    "rating_model_candidates": "ai-rating-model-candidates.json",
    "role_resolution_addenda": "ai-role-resolution-addenda.json",
    "pin_role_addenda": "ai-pin-role-addenda.json",
    "rail_relationship_hints": "ai-rail-relationship-hints.json",
    "passive_support_candidates": "ai-passive-support-candidates.json",
    "human_review_candidates": "ai-human-review-candidates.json",
}


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


def stable_candidate_id(prefix: str, patch: dict[str, Any]) -> str:
    return f"{prefix}_{safe_id(patch.get('target_refdes') or patch.get('target_mpn'))}_{safe_id(patch.get('field_name'))}_{digest_id(patch.get('patch_id'))}"


def evidence_refs(patch: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "source_file": patch.get("source_file"),
            "source_page": patch.get("source_page"),
            "evidence_quote": patch.get("evidence_quote"),
        }
    ]


def base_linkage(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "basis": patch.get("basis"),
        "confidence": patch.get("confidence"),
        "human_review_needed": bool(patch.get("human_review_needed")),
        "evidence_refs": evidence_refs(patch),
        "source_patch_id": patch.get("patch_id"),
        "source_packet_id": patch.get("source_packet_id"),
        "source_item_id": patch.get("source_item_id"),
        "source_accepted_item_id": patch.get("source_accepted_item_id"),
        "missing_data_item_ids": [str(value) for value in as_list(patch.get("missing_data_item_ids"))],
    }


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


def skip_patch(patch: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    return {
        "skipped_patch_id": f"skipped_{safe_id(reason)}_{digest_id(patch.get('patch_id'), reason)}",
        "source_patch_id": patch.get("patch_id"),
        "reason_code": reason,
        "detail": detail,
        "original_patch": sanitize_for_output(patch),
    }


def conflict_index(conflicts: list[dict[str, Any]]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for conflict in conflicts:
        if not isinstance(conflict, dict):
            continue
        cid = str(conflict.get("conflict_id") or "")
        for patch_id in as_list(conflict.get("candidate_patch_ids")):
            index.setdefault(str(patch_id), []).append(cid)
    return {key: sorted(values) for key, values in index.items()}


def blocked_conflict_entry(patch: dict[str, Any], conflict_ids: list[str]) -> dict[str, Any]:
    return {
        "blocked_id": f"blocked_conflict_{digest_id(patch.get('patch_id'), conflict_ids)}",
        "source_patch_id": patch.get("patch_id"),
        "conflict_ids": conflict_ids,
        "reason_code": "blocked_by_conflict",
        "detail": "conflicted patch candidates require human review before candidate ingestion",
    }


def can_materialize_patch(patch: dict[str, Any], include_human_review: bool, allow_conflicted: bool, conflicts_by_patch: dict[str, list[str]]) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
    patch_id = str(patch.get("patch_id") or "")
    if walk_keys(patch).intersection(FORBIDDEN_FIELDS):
        return False, skip_patch(patch, "forbidden_output_field", "patch contains forbidden fields"), None
    if patch.get("operation") != "add_candidate":
        return False, skip_patch(patch, "unsupported_operation", "only add_candidate is supported"), None
    conflict_ids = conflicts_by_patch.get(patch_id, [])
    if conflict_ids and not allow_conflicted:
        return False, None, blocked_conflict_entry(patch, conflict_ids)
    if not patch.get("usable_for_ingestion") and not (include_human_review or allow_conflicted):
        return False, skip_patch(patch, "not_usable_for_ingestion", "patch is not usable for ingestion"), None
    if patch.get("requires_human_approval_before_ingestion") and not (include_human_review or allow_conflicted):
        return False, skip_patch(patch, "human_review_required", "patch requires human approval before ingestion"), None
    if patch.get("patch_class") == "human_review_patch_candidate" and not include_human_review:
        return False, skip_patch(patch, "human_review_not_included", "human review patch candidate omitted by default"), None
    if not (patch.get("source_file") and patch.get("evidence_quote")):
        return False, skip_patch(patch, "missing_evidence", "patch lacks source evidence"), None
    if not (patch.get("target_refdes") or patch.get("target_mpn")):
        return False, skip_patch(patch, "missing_target_identity", "target_refdes or target_mpn is required"), None
    return True, None, None


def current_record(patch: dict[str, Any], source_priority: str) -> dict[str, Any]:
    mapping = {
        "component_current_model": "component_current",
        "rail_current_model": "rail_current",
        "branch_current_model": "branch_current",
    }
    target_type = str(patch.get("target_type") or "")
    return {
        "record_id": stable_candidate_id("ai_cur", patch),
        "record_type": mapping[target_type],
        "source": source_priority,
        "refdes": patch.get("target_refdes") if target_type == "component_current_model" else None,
        "mpn": patch.get("target_mpn"),
        "rail_name": patch.get("target_refdes") if target_type == "rail_current_model" else None,
        "branch_id": patch.get("target_refdes") if target_type == "branch_current_model" else None,
        "field_name": patch.get("field_name"),
        "current_a": patch.get("normalized_value"),
        "current_unit": patch.get("normalized_unit"),
        "condition": patch.get("condition"),
        "source": source_priority,
        **base_linkage(patch),
    }


def rating_record(patch: dict[str, Any], source_priority: str) -> dict[str, Any]:
    mapping = {
        "fuse_rating": "fuse",
        "connector_pin_rating": "connector_pin",
        "connector_rating": "connector",
        "regulator_rating": "regulator",
        "load_switch_rating": "load_switch",
        "ferrite_rating": "ferrite",
    }
    record = {
        "record_id": stable_candidate_id("ai_rate", patch),
        "record_type": "rating",
        "source": source_priority,
        "target_type": mapping[str(patch.get("target_type"))],
        "refdes": patch.get("target_refdes"),
        "pin": patch.get("pin"),
        "mpn": patch.get("target_mpn"),
        "rating_name": patch.get("field_name"),
        "value_a": patch.get("normalized_value") if patch.get("normalized_unit") == "A" else None,
        "value_v": patch.get("normalized_value") if patch.get("normalized_unit") == "V" else None,
        "unit": patch.get("normalized_unit"),
        "condition": patch.get("condition"),
        **base_linkage(patch),
    }
    return record


def role_addendum(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "addendum_id": stable_candidate_id("ai_role", patch),
        "refdes": patch.get("target_refdes"),
        "mpn": patch.get("target_mpn"),
        "field_name": patch.get("field_name"),
        "role": patch.get("normalized_value") if patch.get("field_name") == "component_role" else None,
        "role_subtype": patch.get("normalized_value") if patch.get("field_name") == "role_subtype" else "unknown",
        **base_linkage(patch),
    }


def pin_role_addendum(patch: dict[str, Any]) -> dict[str, Any]:
    field_name = str(patch.get("field_name") or "")
    value = patch.get("normalized_value")
    return {
        "addendum_id": stable_candidate_id("ai_pin", patch),
        "refdes": patch.get("target_refdes"),
        "mpn": patch.get("target_mpn"),
        "pin": patch.get("pin"),
        "pin_name": patch.get("pin_name"),
        "field_name": field_name,
        "pin_role": value if field_name in {"pin_role", "input_pin", "output_pin", "ground_pin", "feedback_pin", "enable_pin"} else None,
        "pin_direction": value if field_name == "pin_direction" else "unknown",
        **base_linkage(patch),
    }


def rail_relationship_hint(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "hint_id": stable_candidate_id("ai_rail", patch),
        "refdes": patch.get("target_refdes"),
        "mpn": patch.get("target_mpn"),
        "input_pin": patch.get("input_pin"),
        "output_pin": patch.get("output_pin"),
        "input_rail_name": patch.get("input_rail_name"),
        "output_rail_name": patch.get("output_rail_name"),
        "relationship_type": patch.get("normalized_value") or patch.get("value") or "unknown",
        **base_linkage(patch),
    }


def passive_support_record(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": stable_candidate_id("ai_passive", patch),
        "target_type": patch.get("target_type"),
        "refdes": patch.get("target_refdes"),
        "mpn": patch.get("target_mpn"),
        "field_name": patch.get("field_name"),
        "value": patch.get("value"),
        "unit": patch.get("unit"),
        "normalized_value": patch.get("normalized_value"),
        "normalized_unit": patch.get("normalized_unit"),
        "condition": patch.get("condition"),
        "frequency_or_temperature_note": patch.get("frequency_or_temperature_note") or patch.get("condition"),
        **base_linkage(patch),
    }


def human_review_candidate(patch: dict[str, Any], reason_code: str, detail: str, conflict_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "candidate_id": stable_candidate_id("ai_human", patch),
        "reason_code": reason_code,
        "detail": detail,
        "usable_for_ingestion": False,
        "conflict_ids": conflict_ids or [],
        "patch_class": patch.get("patch_class"),
        "target_type": patch.get("target_type"),
        "target_refdes": patch.get("target_refdes"),
        "target_mpn": patch.get("target_mpn"),
        "field_name": patch.get("field_name"),
        "value": patch.get("value"),
        "unit": patch.get("unit"),
        "normalized_value": patch.get("normalized_value"),
        "normalized_unit": patch.get("normalized_unit"),
        "condition": patch.get("condition"),
        **base_linkage(patch),
    }


def empty_artifact(project: str, schema_version: str, source_artifacts: list[dict[str, Any]], array_name: str) -> dict[str, Any]:
    return {
        "project": project,
        "schema_version": schema_version,
        "source_artifacts": source_artifacts,
        array_name: [],
        "summary": {f"{array_name[:-1] if array_name.endswith('s') else array_name}_count": 0},
        "errors": [],
        "warnings": [],
    }


def update_summary(artifact: dict[str, Any], array_name: str) -> None:
    artifact["summary"] = {
        f"{array_name[:-1] if array_name.endswith('s') else array_name}_count": len(artifact[array_name]),
        "error_count": len(artifact["errors"]),
        "warning_count": len(artifact["warnings"]),
    }


def build_candidate_artifacts(project: str, patch_bundle_path: Path, patch_bundle: dict[str, Any], source_priority: str, include_human_review: bool, allow_conflicted: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    source_artifacts = [source_artifact("ai_patch_bundle", patch_bundle_path)]
    files = {
        "current_model_candidates": empty_artifact(project, "ai_current_model_candidates_v1", source_artifacts, "current_records"),
        "rating_model_candidates": empty_artifact(project, "ai_rating_model_candidates_v1", source_artifacts, "rating_records"),
        "role_resolution_addenda": empty_artifact(project, "ai_role_resolution_addenda_v1", source_artifacts, "role_addenda"),
        "pin_role_addenda": empty_artifact(project, "ai_pin_role_addenda_v1", source_artifacts, "pin_role_addenda"),
        "rail_relationship_hints": empty_artifact(project, "ai_rail_relationship_hints_v1", source_artifacts, "rail_relationship_hints"),
        "passive_support_candidates": empty_artifact(project, "ai_passive_support_candidates_v1", source_artifacts, "passive_support_records"),
        "human_review_candidates": empty_artifact(project, "ai_human_review_candidates_v1", source_artifacts, "human_review_candidates"),
    }
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    conflicts_by_patch = conflict_index(as_list(patch_bundle.get("conflicts")))

    for patch in sorted([p for p in as_list(patch_bundle.get("patches")) if isinstance(p, dict)], key=lambda row: str(row.get("patch_id") or "")):
        ok, skip, block = can_materialize_patch(patch, include_human_review, allow_conflicted, conflicts_by_patch)
        if skip:
            skipped.append(skip)
        if block:
            blocked.append(block)
            continue
        if not ok:
            continue
        conflict_ids = conflicts_by_patch.get(str(patch.get("patch_id") or ""), [])
        if conflict_ids and allow_conflicted:
            files["human_review_candidates"]["human_review_candidates"].append(
                human_review_candidate(patch, "blocked_by_conflict", "conflicted candidate materialized for review only", conflict_ids)
            )
            continue
        if patch.get("patch_class") == "human_review_patch_candidate":
            files["human_review_candidates"]["human_review_candidates"].append(
                human_review_candidate(patch, "human_review_required", "human-review patch candidate materialized for review only")
            )
        elif patch.get("patch_class") == "current_model_patch":
            if patch.get("field_name") in CURRENT_FIELDS and patch.get("normalized_unit") == "A":
                files["current_model_candidates"]["current_records"].append(current_record(patch, source_priority))
            else:
                skipped.append(skip_patch(patch, "unsupported_field_name", "current patch field/unit is unsupported"))
        elif patch.get("patch_class") == "rating_model_patch":
            if patch.get("target_type") == "ferrite_rating" and patch.get("field_name") not in CURRENT_RATING_FIELDS:
                files["passive_support_candidates"]["passive_support_records"].append(passive_support_record(patch))
            elif patch.get("field_name") in CURRENT_RATING_FIELDS or patch.get("field_name") == "voltage_rating":
                files["rating_model_candidates"]["rating_records"].append(rating_record(patch, source_priority))
            else:
                skipped.append(skip_patch(patch, "unsupported_field_name", "rating patch field is unsupported"))
        elif patch.get("patch_class") == "role_resolution_addendum":
            files["role_resolution_addenda"]["role_addenda"].append(role_addendum(patch))
        elif patch.get("patch_class") == "pin_role_addendum":
            if not (patch.get("pin") or patch.get("pin_name")):
                skipped.append(skip_patch(patch, "missing_pin_identity", "pin role addendum requires pin or pin_name"))
            else:
                files["pin_role_addenda"]["pin_role_addenda"].append(pin_role_addendum(patch))
        elif patch.get("patch_class") == "rail_relationship_hint":
            files["rail_relationship_hints"]["rail_relationship_hints"].append(rail_relationship_hint(patch))
        elif patch.get("patch_class") == "passive_support_data_patch":
            if patch.get("field_name") in PASSIVE_FIELDS:
                files["passive_support_candidates"]["passive_support_records"].append(passive_support_record(patch))
            else:
                skipped.append(skip_patch(patch, "unsupported_field_name", "passive support field is unsupported"))
        else:
            skipped.append(skip_patch(patch, "unsupported_patch_class", "patch class is unsupported"))

    for key, array_name in (
        ("current_model_candidates", "current_records"),
        ("rating_model_candidates", "rating_records"),
        ("role_resolution_addenda", "role_addenda"),
        ("pin_role_addenda", "pin_role_addenda"),
        ("rail_relationship_hints", "rail_relationship_hints"),
        ("passive_support_candidates", "passive_support_records"),
        ("human_review_candidates", "human_review_candidates"),
    ):
        files[key][array_name] = sorted(files[key][array_name], key=lambda row: str(row.get("record_id") or row.get("addendum_id") or row.get("hint_id") or row.get("candidate_id") or ""))
        update_summary(files[key], array_name)

    candidate_count = sum(len(files[key][array]) for key, array in (
        ("current_model_candidates", "current_records"),
        ("rating_model_candidates", "rating_records"),
        ("role_resolution_addenda", "role_addenda"),
        ("pin_role_addenda", "pin_role_addenda"),
        ("rail_relationship_hints", "rail_relationship_hints"),
        ("passive_support_candidates", "passive_support_records"),
        ("human_review_candidates", "human_review_candidates"),
    ))
    summary = {
        "source_patch_count": len(as_list(patch_bundle.get("patches"))),
        "usable_source_patch_count": sum(1 for patch in as_list(patch_bundle.get("patches")) if isinstance(patch, dict) and patch.get("usable_for_ingestion")),
        "materialized_candidate_count": candidate_count,
        "current_model_candidate_count": len(files["current_model_candidates"]["current_records"]),
        "rating_model_candidate_count": len(files["rating_model_candidates"]["rating_records"]),
        "role_addendum_count": len(files["role_resolution_addenda"]["role_addenda"]),
        "pin_role_addendum_count": len(files["pin_role_addenda"]["pin_role_addenda"]),
        "rail_relationship_hint_count": len(files["rail_relationship_hints"]["rail_relationship_hints"]),
        "passive_support_candidate_count": len(files["passive_support_candidates"]["passive_support_records"]),
        "human_review_candidate_count": len(files["human_review_candidates"]["human_review_candidates"]),
        "skipped_patch_count": len(skipped),
        "blocked_by_conflict_count": len(blocked),
        "conflict_count": len(as_list(patch_bundle.get("conflicts"))),
        "safe_to_feed_candidate_ingestion": True,
        "safe_to_overwrite_core_artifacts": False,
        "error_count": 0,
        "warning_count": 0,
    }
    manifest = {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts,
        "source_patch_bundle": str(patch_bundle_path),
        "candidate_materialization_pass": True,
        "candidate_files": CANDIDATE_FILES,
        "skipped_patches": skipped,
        "blocked_by_conflict": blocked,
        "summary": summary,
        "errors": [],
        "warnings": [],
    }
    status = {
        "project": project,
        "status": "materialized",
        "source_patch_bundle": str(patch_bundle_path),
        "candidate_materialization_pass": True,
        "safe_to_feed_candidate_ingestion": True,
        "safe_to_overwrite_core_artifacts": False,
        "requires_human_review_count": summary["human_review_candidate_count"] + summary["blocked_by_conflict_count"],
        "conflict_count": summary["conflict_count"],
        "errors": [],
        "warnings": [],
    }
    return manifest, status, files


def validate_no_forbidden(data: dict[str, Any]) -> None:
    forbidden = sorted(walk_keys(data).intersection(FORBIDDEN_FIELDS))
    if forbidden:
        raise ValueError(f"candidate output contains forbidden field(s): {', '.join(forbidden)}")


def validate_artifacts(artifacts: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for artifact in artifacts:
        validate_no_forbidden(artifact)
        jsonschema.validate(instance=artifact, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize isolated AI candidate input files from an AI patch bundle.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--patch-bundle", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-human-review", action="store_true")
    parser.add_argument("--allow-conflicted", action="store_true")
    parser.add_argument("--source-priority", default=DEFAULT_SOURCE_PRIORITY)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    patch_bundle_path = Path(args.patch_bundle)
    out_dir = Path(args.out_dir)
    try:
        if not patch_bundle_path.exists():
            raise FileNotFoundError(f"missing patch bundle: {patch_bundle_path}")
        patch_bundle = load_json(patch_bundle_path)
        if not isinstance(patch_bundle, dict):
            raise ValueError(f"patch bundle must be a JSON object: {patch_bundle_path}")
        manifest, status, files = build_candidate_artifacts(
            args.project,
            patch_bundle_path,
            patch_bundle,
            args.source_priority,
            args.include_human_review,
            args.allow_conflicted,
        )
        if args.strict and manifest["skipped_patches"]:
            manifest["errors"].append("strict mode disallows skipped patches")
            manifest["candidate_materialization_pass"] = False
            status["errors"] = manifest["errors"]
            status["candidate_materialization_pass"] = False
        validate_artifacts([manifest, status, *files.values()], Path(args.schema))
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "ai-candidate-inputs.json", manifest)
        write_json(out_dir / "materialization-status.json", status)
        for key, filename in CANDIDATE_FILES.items():
            write_json(out_dir / filename, files[key])
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(
        "ai candidate materialize: "
        f"project={manifest['project']} candidates={summary['materialized_candidate_count']} "
        f"current={summary['current_model_candidate_count']} rating={summary['rating_model_candidate_count']} "
        f"blocked={summary['blocked_by_conflict_count']} skipped={summary['skipped_patch_count']} out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
