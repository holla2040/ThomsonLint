#!/usr/bin/env python3
"""Build a human approval queue for isolated AI candidate outputs.

PR32 scope only: compare PR31 candidate-normalized outputs against optional
core normalized artifacts and emit reviewable promotion-plan artifacts. This
script does not call AI, rerun ingestion, overwrite core artifacts, run
allocation/calculations, merge addenda, create findings, or make pass/fail or
compliance judgments.
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


SCHEMA_VERSION = "ai_candidate_promotion_plan_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_candidate_promotion_schema.json"

OUTPUTS = {
    "plan": "ai-candidate-promotion-plan.json",
    "approval_queue": "ai-candidate-approval-queue.json",
    "diff": "ai-candidate-promotion-diff.json",
    "status": "ai-candidate-promotion-status.json",
    "addenda_review": "ai-addenda-promotion-review.json",
    "human_review_index": "ai-human-review-promotion-index.json",
}

FORBIDDEN_OUTPUT_FILENAMES = {
    "{project}-current-models-normalized.json",
    "{project}-rating-models-normalized.json",
    "{project}-topology-current-allocation.json",
    "{project}-topology-copper-calculations.json",
    "{project}-topology-margin-calculations.json",
}

FORBIDDEN_FIELDS = {
    "finding_id", "issue_id", "violation", "severity", "compliance_pass", "compliance_fail", "pass_fail",
    "margin_pass", "margin_fail", "acceptable", "unacceptable", "final_finding", "recommendation_severity",
    "apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_load(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


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


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def source_artifact(artifact_type: str, path: Path | None, notes: str | None = None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path) if path else None, "notes": notes}


def safe_id(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_")
    return text or "unknown"


def digest_id(*values: Any) -> str:
    payload = json.dumps([json_safe(value) for value in values], sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


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


def forbidden_non_null_approval(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in {"approved_by", "approved_at_utc"} and child is not None:
                return True
            if forbidden_non_null_approval(child):
                return True
    elif isinstance(value, list):
        return any(forbidden_non_null_approval(child) for child in value)
    return False


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def verify_output_path(path: Path, out_dir: Path, project: str) -> None:
    forbidden = {name.format(project=project) for name in FORBIDDEN_OUTPUT_FILENAMES}
    if path.name in forbidden:
        raise ValueError(f"forbidden core output filename: {path.name}")
    if not path_is_relative_to(path, out_dir):
        raise ValueError(f"output path must be inside out-dir: {path}")


def source_record_index(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"source_record_(\d+)", value)
    return int(match.group(1)) if match else None


def flattened_source_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("branch_currents", "rail_currents", "component_currents", "ratings"):
        rows.extend(row for row in as_list(data.get(key)) if isinstance(row, dict))
    return rows


def source_record_from_artifact(record: dict[str, Any]) -> dict[str, Any]:
    for artifact in as_list(record.get("source_artifacts")):
        if not isinstance(artifact, dict):
            continue
        index = source_record_index(artifact.get("record_id"))
        path_value = artifact.get("path")
        if index is None or not isinstance(path_value, str):
            continue
        path = Path(path_value)
        if not path.exists():
            continue
        data = safe_load(path)
        rows = flattened_source_records(data)
        if 1 <= index <= len(rows):
            return rows[index - 1]
    return {}


def source_record_for_candidate(record: dict[str, Any], rating_current: dict[str, Any] | None = None) -> dict[str, Any]:
    source = source_record_from_artifact(record)
    if source:
        return source
    source_record_id = record.get("source_record_id")
    if rating_current and isinstance(source_record_id, str):
        for row in as_list(rating_current.get("normalized_currents")):
            if isinstance(row, dict) and row.get("record_id") == source_record_id:
                return source_record_from_artifact(row)
    return {}


def current_identity(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_type": record.get("target_type") or record.get("record_type"),
        "refdes": record.get("refdes"),
        "pin": record.get("pin"),
        "rail_name": record.get("rail_name"),
        "branch_id": record.get("branch_id"),
        "field_name": record.get("field_name") or record.get("current_type"),
        "condition": record.get("condition"),
    }


def rating_identity(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_type": record.get("normalized_target_type") or record.get("target_type"),
        "refdes": record.get("refdes"),
        "pin": record.get("pin"),
        "rail_name": record.get("rail_name"),
        "branch_id": record.get("branch_id"),
        "field_name": record.get("normalized_rating_name") or record.get("rating_name"),
        "condition": record.get("condition"),
    }


def identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(identity.get(key) or "") for key in ("target_type", "refdes", "pin", "rail_name", "branch_id", "field_name", "condition"))


def loose_identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(identity.get(key) or "") for key in ("target_type", "refdes", "pin", "rail_name", "branch_id", "field_name"))


def identity_sufficient(identity: dict[str, Any], kind: str) -> bool:
    has_target = bool(identity.get("refdes") or identity.get("rail_name") or identity.get("branch_id"))
    has_field = bool(identity.get("field_name"))
    has_type = bool(identity.get("target_type"))
    if kind == "rating_model" and identity.get("target_type") == "connector_pin" and not identity.get("pin"):
        return False
    return has_target and has_field and has_type


def candidate_value(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    value = record.get("value_a") if record.get("value_a") is not None else record.get("value")
    unit = record.get("unit")
    return {
        "value": value,
        "unit": unit,
        "normalized_value": value,
        "normalized_unit": unit,
    }


def same_value(a: dict[str, Any], b: dict[str, Any]) -> bool:
    av = a.get("value_a") if a.get("value_a") is not None else a.get("value")
    bv = b.get("value_a") if b.get("value_a") is not None else b.get("value")
    au = a.get("unit")
    bu = b.get("unit")
    return is_number(av) and is_number(bv) and math.isclose(float(av), float(bv), rel_tol=1e-9, abs_tol=1e-12) and au == bu


def promotion_id(kind: str, identity: dict[str, Any], value: dict[str, Any], record_id: Any) -> str:
    return f"promo_{safe_id(kind)}_{digest_id(identity, value, record_id)}"


def approval_id(candidate_id: str) -> str:
    return f"approve_{digest_id(candidate_id)}"


def target_summary(identity: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in identity.items() if value not in (None, "")]
    return ", ".join(parts) if parts else "unknown target"


def source_ids(record: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    provenance = source.get("provenance") if isinstance(source.get("provenance"), dict) else {}
    return {
        "source_candidate_record_id": source.get("source_candidate_record_id") or record.get("source_record_id") or record.get("record_id") or record.get("rating_id"),
        "source_ai_packet_id": source.get("source_packet_id") or provenance.get("source_packet_id"),
        "source_ai_patch_id": source.get("source_patch_id") or provenance.get("source_patch_id"),
        "source_ai_accepted_item_id": source.get("source_accepted_item_id") or provenance.get("source_accepted_item_id"),
        "missing_data_item_ids": as_list(source.get("missing_data_item_ids")) or as_list(record.get("missing_data_manifest_item_ids")),
    }


def make_candidate(
    *,
    kind: str,
    operation: str,
    match_status: str,
    record: dict[str, Any],
    source: dict[str, Any],
    source_artifact_path: Path,
    identity: dict[str, Any],
    matched_core_ids: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    value = candidate_value(record, source)
    ids = source_ids(record, source)
    candidate_id = promotion_id(kind, identity, value, ids["source_candidate_record_id"])
    return {
        "promotion_candidate_id": candidate_id,
        "candidate_kind": kind,
        "operation": operation,
        "promotion_status": "pending_human_approval",
        "safe_to_apply_automatically": False,
        "source_candidate_artifact": str(source_artifact_path),
        "source_candidate_record_id": ids["source_candidate_record_id"],
        "source_ai_packet_id": ids["source_ai_packet_id"],
        "source_ai_patch_id": ids["source_ai_patch_id"],
        "source_ai_accepted_item_id": ids["source_ai_accepted_item_id"],
        "target_identity": identity,
        "candidate_value": value,
        "core_match": {
            "match_status": match_status,
            "matched_core_record_ids": matched_core_ids,
        },
        "basis": record.get("basis") or source.get("basis"),
        "confidence": record.get("confidence") if record.get("confidence") is not None else source.get("confidence"),
        "evidence_refs": as_list(record.get("evidence_refs")) or as_list(source.get("evidence_refs")),
        "missing_data_item_ids": ids["missing_data_item_ids"],
        "approval": {
            "approval_required": True,
            "approved": False,
            "approved_by": None,
            "approved_at_utc": None,
            "approval_note": None,
        },
        "warnings": warnings or [],
    }


def approval_item(candidate: dict[str, Any], reason_code: str) -> dict[str, Any]:
    operation = candidate["operation"]
    if operation == "conflict_with_core":
        review_type = "resolve_conflict"
        priority = "high"
    elif operation == "duplicate_existing":
        review_type = "review_duplicate"
        priority = "low"
    elif operation == "needs_human_review":
        review_type = "human_review_required"
        priority = "high"
    elif candidate["candidate_kind"].endswith("addendum") or candidate["candidate_kind"] in {"rail_relationship_hint", "passive_support"}:
        review_type = "addenda_merge_review"
        priority = "low"
    else:
        review_type = "approve_add"
        priority = "medium"
    value = candidate["candidate_value"]
    return {
        "approval_item_id": approval_id(candidate["promotion_candidate_id"]),
        "promotion_candidate_id": candidate["promotion_candidate_id"],
        "review_type": review_type,
        "priority": priority,
        "reason_code": reason_code,
        "target_summary": target_summary(candidate["target_identity"]),
        "candidate_summary": f"{value.get('normalized_value')} {value.get('normalized_unit')}",
        "core_summary": candidate["core_match"]["match_status"],
        "evidence_refs": candidate["evidence_refs"],
        "recommended_action": "review_only",
        "approval_required": True,
        "safe_to_apply_automatically": False,
        "status": "pending",
    }


def classify_against_core(
    *,
    kind: str,
    record: dict[str, Any],
    source: dict[str, Any],
    source_path: Path,
    core_records: list[dict[str, Any]],
    core_missing: bool,
) -> tuple[dict[str, Any], str]:
    identity = current_identity(record) if kind == "current_model" else rating_identity(record)
    if not identity_sufficient(identity, kind):
        return make_candidate(
            kind=kind,
            operation="needs_human_review",
            match_status="identity_conflict",
            record=record,
            source=source,
            source_artifact_path=source_path,
            identity=identity,
            matched_core_ids=[],
            warnings=["missing_target_identity"],
        ), "missing_target_identity"
    if core_missing:
        return make_candidate(
            kind=kind,
            operation="add_candidate",
            match_status="core_missing",
            record=record,
            source=source,
            source_artifact_path=source_path,
            identity=identity,
            matched_core_ids=[],
            warnings=["core_artifact_missing"],
        ), "core_artifact_missing"

    exact_matches: list[dict[str, Any]] = []
    loose_matches: list[dict[str, Any]] = []
    for core in core_records:
        core_identity = current_identity(core) if kind == "current_model" else rating_identity(core)
        if identity_key(core_identity) == identity_key(identity):
            exact_matches.append(core)
        elif loose_identity_key(core_identity) == loose_identity_key(identity):
            loose_matches.append(core)
    matched = exact_matches or loose_matches
    matched_ids = [str(row.get("record_id") or row.get("rating_id") or row.get("source_record_id") or "") for row in matched]
    if not matched:
        return make_candidate(
            kind=kind,
            operation="add_candidate",
            match_status="no_core_match",
            record=record,
            source=source,
            source_artifact_path=source_path,
            identity=identity,
            matched_core_ids=[],
        ), "candidate_not_in_core"
    if exact_matches and any(same_value(record, core) for core in exact_matches):
        return make_candidate(
            kind=kind,
            operation="duplicate_existing",
            match_status="exact_duplicate",
            record=record,
            source=source,
            source_artifact_path=source_path,
            identity=identity,
            matched_core_ids=matched_ids,
        ), "exact_duplicate_existing_core"
    if loose_matches and not exact_matches:
        reason = "conflicting_core_condition"
        match_status = "condition_conflict"
    elif any((record.get("unit") != core.get("unit")) for core in matched):
        reason = "conflicting_core_unit"
        match_status = "value_conflict"
    else:
        reason = "conflicting_core_value"
        match_status = "value_conflict"
    return make_candidate(
        kind=kind,
        operation="conflict_with_core",
        match_status=match_status,
        record=record,
        source=source,
        source_artifact_path=source_path,
        identity=identity,
        matched_core_ids=matched_ids,
        warnings=[reason],
    ), reason


def addenda_review(project: str, ai_dir: Path, source_artifacts: list[dict[str, Any]], include_addenda: bool) -> dict[str, Any]:
    index_path = ai_dir / "ai-addenda-index.json"
    index = safe_load(index_path)
    role = safe_load(Path(index.get("role_resolution_addenda_adapter", ""))) if index else {}
    pin = safe_load(Path(index.get("pin_role_addenda_adapter", ""))) if index else {}
    rail = safe_load(Path(index.get("rail_relationship_hints_adapter", ""))) if index else {}
    passive = safe_load(Path(index.get("passive_support_adapter", ""))) if index else {}
    return {
        "project": project,
        "schema_version": "ai_addenda_promotion_review_v1",
        "source_artifacts": source_artifacts + [source_artifact("ai_addenda_index", index_path)],
        "role_addenda_review": as_list(role.get("role_addenda")) if include_addenda else [],
        "pin_role_addenda_review": as_list(pin.get("pin_role_addenda")) if include_addenda else [],
        "rail_relationship_hint_review": as_list(rail.get("rail_relationship_hints")) if include_addenda else [],
        "passive_support_review": as_list(passive.get("passive_support_records")) if include_addenda else [],
        "safe_to_merge_automatically": False,
        "requires_merge_validator": True,
        "summary": {
            "role_addenda_review_count": len(as_list(role.get("role_addenda"))) if include_addenda else 0,
            "pin_role_addenda_review_count": len(as_list(pin.get("pin_role_addenda"))) if include_addenda else 0,
            "rail_relationship_hint_review_count": len(as_list(rail.get("rail_relationship_hints"))) if include_addenda else 0,
            "passive_support_review_count": len(as_list(passive.get("passive_support_records"))) if include_addenda else 0,
        },
        "errors": [],
        "warnings": [] if include_addenda else ["addenda review excluded by default"],
    }


def human_review_records(ai_dir: Path, include_human_review: bool) -> list[dict[str, Any]]:
    if not include_human_review:
        return []
    index = safe_load(ai_dir / "ai-human-review-index.json")
    return as_list(index.get("human_review_records")) + as_list(index.get("workflow_review_records"))


def build_plan(
    *,
    project: str,
    ai_ingested_dir: Path,
    out_dir: Path,
    core_current_path: Path | None,
    core_rating_path: Path | None,
    strict: bool,
    include_addenda: bool,
    include_human_review: bool,
    allow_core_missing: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ai_ingested_dir = ai_ingested_dir.resolve()
    out_dir = out_dir.resolve()
    manifest_path = ai_ingested_dir / "ai-candidate-ingestion-manifest.json"
    status_path = ai_ingested_dir / "ai-candidate-ingestion-status.json"
    ai_manifest = load_json(manifest_path)
    ai_status = load_json(status_path)
    if not isinstance(ai_manifest, dict):
        raise ValueError(f"ai ingested manifest must be a JSON object: {manifest_path}")
    if not isinstance(ai_status, dict):
        raise ValueError(f"ai ingested status must be a JSON object: {status_path}")
    for filename in OUTPUTS.values():
        verify_output_path(out_dir / filename, out_dir, project)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidate_current_path = ai_ingested_dir / "ai-current-models-normalized.json"
    candidate_rating_current_path = ai_ingested_dir / "ai-rating-current-models-normalized.json"
    candidate_rating_path = ai_ingested_dir / "ai-rating-models-normalized.json"
    candidate_current = safe_load(candidate_current_path)
    candidate_rating_current = safe_load(candidate_rating_current_path)
    candidate_rating = safe_load(candidate_rating_path)

    if core_current_path is None:
        default = Path(f"exports/{project}-current-models-normalized.json")
        core_current_path = default if default.exists() else None
    if core_rating_path is None:
        default = Path(f"exports/{project}-rating-models-normalized.json")
        core_rating_path = default if default.exists() else None
    core_current_missing = core_current_path is None or not core_current_path.exists()
    core_rating_missing = core_rating_path is None or not core_rating_path.exists()
    core_current = safe_load(core_current_path)
    core_rating = safe_load(core_rating_path)

    source_artifacts = [
        source_artifact("ai_candidate_ingestion_manifest", manifest_path),
        source_artifact("ai_candidate_ingestion_status", status_path),
        source_artifact("ai_current_models_normalized", candidate_current_path),
        source_artifact("ai_rating_models_normalized", candidate_rating_path),
    ]
    warnings: list[str] = []
    errors: list[str] = []
    if core_current_missing:
        warnings.append("core current models normalized artifact missing")
    if core_rating_missing:
        warnings.append("core rating models normalized artifact missing")
    if strict and (core_current_missing or core_rating_missing) and not allow_core_missing:
        errors.append("strict mode requires core current/rating artifacts unless allow-core-missing is set")

    promotion_candidates: list[dict[str, Any]] = []
    blocked_candidates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    approval_items: list[dict[str, Any]] = []
    diff_current = {"add_candidates": [], "exact_duplicates": [], "conflicts": [], "blocked": []}
    diff_rating = {"add_candidates": [], "exact_duplicates": [], "conflicts": [], "blocked": []}

    for record in sorted(as_list(candidate_current.get("normalized_currents")), key=lambda row: str(row.get("record_id") or "")):
        if not isinstance(record, dict):
            continue
        source = source_record_for_candidate(record)
        candidate, reason = classify_against_core(
            kind="current_model",
            record=record,
            source=source,
            source_path=candidate_current_path,
            core_records=[row for row in as_list(core_current.get("normalized_currents")) if isinstance(row, dict)],
            core_missing=core_current_missing,
        )
        promotion_candidates.append(candidate)
        approval_items.append(approval_item(candidate, reason))
        if candidate["operation"] == "add_candidate":
            diff_current["add_candidates"].append(candidate["promotion_candidate_id"])
        elif candidate["operation"] == "duplicate_existing":
            diff_current["exact_duplicates"].append(candidate["promotion_candidate_id"])
        elif candidate["operation"] == "conflict_with_core":
            diff_current["conflicts"].append(candidate["promotion_candidate_id"])
            conflicts.append(candidate)
        else:
            diff_current["blocked"].append(candidate["promotion_candidate_id"])
            blocked_candidates.append(candidate)

    for record in sorted(as_list(candidate_rating.get("normalized_ratings")), key=lambda row: str(row.get("rating_id") or row.get("source_record_id") or "")):
        if not isinstance(record, dict):
            continue
        source = source_record_for_candidate(record, candidate_rating_current)
        candidate, reason = classify_against_core(
            kind="rating_model",
            record=record,
            source=source,
            source_path=candidate_rating_path,
            core_records=[row for row in as_list(core_rating.get("normalized_ratings")) if isinstance(row, dict)],
            core_missing=core_rating_missing,
        )
        promotion_candidates.append(candidate)
        approval_items.append(approval_item(candidate, reason))
        if candidate["operation"] == "add_candidate":
            diff_rating["add_candidates"].append(candidate["promotion_candidate_id"])
        elif candidate["operation"] == "duplicate_existing":
            diff_rating["exact_duplicates"].append(candidate["promotion_candidate_id"])
        elif candidate["operation"] == "conflict_with_core":
            diff_rating["conflicts"].append(candidate["promotion_candidate_id"])
            conflicts.append(candidate)
        else:
            diff_rating["blocked"].append(candidate["promotion_candidate_id"])
            blocked_candidates.append(candidate)

    addenda = addenda_review(project, ai_ingested_dir, source_artifacts, include_addenda)
    carried_human = human_review_records(ai_ingested_dir, include_human_review)
    for record in carried_human:
        if isinstance(record, dict):
            candidate = make_candidate(
                kind="passive_support",
                operation="needs_human_review",
                match_status="identity_conflict",
                record={"basis": record.get("basis"), "confidence": record.get("confidence"), "evidence_refs": as_list(record.get("evidence_refs"))},
                source=record,
                source_artifact_path=ai_ingested_dir / "ai-human-review-index.json",
                identity={"target_type": record.get("candidate_type"), "refdes": record.get("refdes"), "pin": record.get("pin"), "rail_name": record.get("rail_name"), "branch_id": record.get("branch_id"), "field_name": record.get("reason_code"), "condition": None},
                matched_core_ids=[],
                warnings=["human_review_carried_forward"],
            )
            blocked_candidates.append(candidate)
            promotion_candidates.append(candidate)
            approval_items.append(approval_item(candidate, "human_review_carried_forward"))

    approval_items = sorted(approval_items, key=lambda row: row["approval_item_id"])
    promotion_candidates = sorted(promotion_candidates, key=lambda row: row["promotion_candidate_id"])
    blocked_candidates = sorted(blocked_candidates, key=lambda row: row["promotion_candidate_id"])
    conflicts = sorted(conflicts, key=lambda row: row["promotion_candidate_id"])
    requires_human_approval = [row["promotion_candidate_id"] for row in promotion_candidates]

    summary = {
        "candidate_current_record_count": len(as_list(candidate_current.get("normalized_currents"))),
        "candidate_rating_record_count": len(as_list(candidate_rating.get("normalized_ratings"))),
        "core_current_record_count": len(as_list(core_current.get("normalized_currents"))),
        "core_rating_record_count": len(as_list(core_rating.get("normalized_ratings"))),
        "promotion_candidate_count": len(promotion_candidates),
        "add_candidate_count": sum(1 for row in promotion_candidates if row["operation"] == "add_candidate"),
        "exact_duplicate_count": sum(1 for row in promotion_candidates if row["operation"] == "duplicate_existing"),
        "conflict_count": len(conflicts),
        "blocked_candidate_count": len(blocked_candidates),
        "requires_human_approval_count": len(requires_human_approval),
        "approval_queue_count": len(approval_items),
        "role_addenda_review_count": addenda["summary"]["role_addenda_review_count"],
        "pin_role_addenda_review_count": addenda["summary"]["pin_role_addenda_review_count"],
        "rail_relationship_hint_review_count": addenda["summary"]["rail_relationship_hint_review_count"],
        "passive_support_review_count": addenda["summary"]["passive_support_review_count"],
        "safe_to_apply_automatically": False,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    pass_status = not errors
    plan = {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts,
        "source_ai_ingested_manifest": str(manifest_path),
        "source_ai_ingested_status": str(status_path),
        "core_artifacts": {
            "current_models_normalized": str(core_current_path) if core_current_path and core_current_path.exists() else None,
            "rating_models_normalized": str(core_rating_path) if core_rating_path and core_rating_path.exists() else None,
        },
        "promotion_plan_pass": pass_status,
        "promotion_candidates": promotion_candidates,
        "blocked_candidates": blocked_candidates,
        "conflicts": conflicts,
        "requires_human_approval": requires_human_approval,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    queue = {
        "project": project,
        "schema_version": "ai_candidate_approval_queue_v1",
        "source_artifacts": source_artifacts,
        "approval_items": approval_items,
        "summary": {"approval_queue_count": len(approval_items), "requires_human_approval_count": len(requires_human_approval)},
        "errors": [],
        "warnings": warnings,
    }
    diff = {
        "project": project,
        "schema_version": "ai_candidate_promotion_diff_v1",
        "current_model_diff": diff_current,
        "rating_model_diff": diff_rating,
        "summary": summary,
        "errors": [],
        "warnings": warnings,
    }
    status = {
        "project": project,
        "status": "failed" if errors else "planned_with_warnings" if warnings else "planned",
        "promotion_plan_pass": pass_status,
        "safe_to_apply_automatically": False,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "requires_human_approval_count": len(requires_human_approval),
        "conflict_count": len(conflicts),
        "errors": errors,
        "warnings": warnings,
    }
    human_index = {
        "project": project,
        "schema_version": "ai_human_review_promotion_index_v1",
        "source_artifacts": source_artifacts + [source_artifact("ai_human_review_index", ai_ingested_dir / "ai-human-review-index.json")],
        "human_review_records": carried_human,
        "blocked_candidates": blocked_candidates,
        "conflicts": conflicts,
        "approval_item_ids": [row["approval_item_id"] for row in approval_items],
        "summary": {
            "human_review_record_count": len(carried_human),
            "blocked_candidate_count": len(blocked_candidates),
            "conflict_count": len(conflicts),
            "approval_item_count": len(approval_items),
        },
        "errors": [],
        "warnings": [],
    }
    return plan, queue, diff, status, addenda, human_index


def validate_outputs(outputs: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for output in outputs:
        forbidden = sorted(walk_keys(output).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            raise ValueError(f"promotion output contains forbidden field(s): {', '.join(forbidden)}")
        if forbidden_non_null_approval(output):
            raise ValueError("promotion output contains non-null approval identity/timestamp")
        jsonschema.validate(instance=output, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an AI candidate promotion plan and human approval queue.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--ai-ingested-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--core-current-models-normalized", default=None)
    parser.add_argument("--core-rating-models-normalized", default=None)
    parser.add_argument("--missing-data-manifest", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-addenda", action="store_true")
    parser.add_argument("--include-human-review", action="store_true")
    parser.add_argument("--allow-core-missing", action="store_true")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ai_dir = Path(args.ai_ingested_dir)
    out_dir = Path(args.out_dir)
    try:
        if not ai_dir.exists():
            raise FileNotFoundError(f"missing ai ingested directory: {ai_dir}")
        if not (ai_dir / "ai-candidate-ingestion-manifest.json").exists():
            raise FileNotFoundError(f"missing ai ingested manifest: {ai_dir / 'ai-candidate-ingestion-manifest.json'}")
        if not (ai_dir / "ai-candidate-ingestion-status.json").exists():
            raise FileNotFoundError(f"missing ai ingested status: {ai_dir / 'ai-candidate-ingestion-status.json'}")
        artifacts = build_plan(
            project=args.project,
            ai_ingested_dir=ai_dir,
            out_dir=out_dir,
            core_current_path=Path(args.core_current_models_normalized) if args.core_current_models_normalized else None,
            core_rating_path=Path(args.core_rating_models_normalized) if args.core_rating_models_normalized else None,
            strict=args.strict,
            include_addenda=args.include_addenda,
            include_human_review=args.include_human_review,
            allow_core_missing=args.allow_core_missing,
        )
        validate_outputs(list(artifacts), Path(args.schema))
        for artifact, filename in zip(artifacts, OUTPUTS.values(), strict=True):
            write_json(out_dir / filename, artifact)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    plan = artifacts[0]
    summary = plan["summary"]
    print(
        "ai candidate promotion plan: "
        f"project={plan['project']} candidates={summary['promotion_candidate_count']} "
        f"conflicts={summary['conflict_count']} approvals={summary['approval_queue_count']} out={out_dir}"
    )
    return 0 if plan["promotion_plan_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
