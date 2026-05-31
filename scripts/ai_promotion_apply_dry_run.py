#!/usr/bin/env python3
"""Approved-only promotion apply dry run v0."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_VERSION = "ai_promotion_apply_dry_run_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_promotion_apply_dry_run_schema.json"

OUTPUTS = {
    "dry_run": "ai-approved-promotion-apply-dry-run.json",
    "status": "ai-approved-promotion-apply-status.json",
    "current_preview": "ai-approved-current-model-merge-preview.json",
    "rating_preview": "ai-approved-rating-model-merge-preview.json",
    "addenda_preview": "ai-approved-addenda-merge-preview.json",
    "blockers": "ai-promotion-apply-blockers.json",
}

FORBIDDEN_OUTPUT_FILENAMES = {
    "{project}-current-models-normalized.json",
    "{project}-rating-models-normalized.json",
    "{project}-topology-current-allocation.json",
    "{project}-topology-copper-calculations.json",
    "{project}-topology-margin-calculations.json",
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
    "apply_to_artifact",
    "mutate_artifact",
    "overwrite",
    "delete_existing",
    "replace_existing",
}

BLOCKER_CODES = {
    "invalid_decision",
    "missing_decision_validation",
    "approval_queue_mismatch",
    "promotion_candidate_missing",
    "decision_not_approved",
    "approved_decision_invalid",
    "core_conflict",
    "missing_target_identity",
    "missing_evidence",
    "addenda_requires_merge_validator",
    "unsupported_candidate_kind",
    "stale_or_failed_promotion_status",
    "attempted_core_write_blocked",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def require_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing {label}: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return data


def safe_load_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_safe(data), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def digest_id(*values: Any) -> str:
    payload = json.dumps([json_safe(v) for v in values], sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def sort_key(value: Any) -> str:
    return str(value or "")


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


def source_artifact(artifact_type: str, path: Path | None, notes: str | None = None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path) if path else None, "notes": notes}


def canonical(value: Any) -> str:
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"))


def records_from_core(path: Path | None, keys: list[str]) -> list[dict[str, Any]]:
    data = safe_load_object(path)
    for key in keys:
        rows = data.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def core_missing(path: Path | None) -> bool:
    return path is None or not path.exists()


def target_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    return all(right.get(k) == v for k, v in left.items())


def classify_against_core(
    candidate_kind: str,
    target_identity: dict[str, Any],
    candidate_value: dict[str, Any],
    core_match: dict[str, Any],
    core_current_records: list[dict[str, Any]],
    core_rating_records: list[dict[str, Any]],
    current_missing: bool,
    rating_missing: bool,
) -> tuple[str, str, list[str]]:
    match_status = str(core_match.get("match_status") or "")
    warnings: list[str] = []
    if candidate_kind == "current_model" and current_missing:
        warnings.append("core_current_artifact_missing")
        return "core_missing", "would_add", warnings
    if candidate_kind == "rating_model" and rating_missing:
        warnings.append("core_rating_artifact_missing")
        return "core_missing", "would_add", warnings
    if match_status == "exact_duplicate":
        return match_status, "would_skip_duplicate", warnings
    if match_status in {"value_conflict", "condition_conflict", "identity_conflict"}:
        return match_status, "would_block_conflict", warnings
    if match_status == "no_core_match":
        return match_status, "would_add", warnings
    if match_status == "core_missing":
        warnings.append("core_artifact_missing_for_candidate")
        return match_status, "would_add", warnings

    records = core_current_records if candidate_kind == "current_model" else core_rating_records
    for row in records:
        if not target_matches(target_identity, row):
            continue
        if row.get("candidate_value") == candidate_value or {k: row.get(k) for k in candidate_value} == candidate_value:
            return "exact_duplicate", "would_skip_duplicate", warnings
        return "value_conflict", "would_block_conflict", warnings
    return "no_core_match", "would_add", warnings


def blocker(
    reason_code: str,
    approval_item_id: str | None,
    decision_id: str | None,
    promotion_candidate_id: str | None,
    details: str,
) -> dict[str, Any]:
    if reason_code not in BLOCKER_CODES:
        reason_code = "invalid_decision"
    return {
        "approval_item_id": approval_item_id,
        "decision_id": decision_id,
        "promotion_candidate_id": promotion_candidate_id,
        "reason_code": reason_code,
        "details": details,
    }


def approved_blocker_reason(reason_code: str) -> bool:
    return reason_code not in {"decision_not_approved"}


def validation_maps(validation_data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_decision: dict[str, dict[str, Any]] = {}
    invalid_by_decision: dict[str, list[dict[str, Any]]] = {}
    for row in as_list(validation_data.get("validated_decisions")):
        if isinstance(row, dict) and row.get("decision_id"):
            by_decision[str(row["decision_id"])] = row
    for row in as_list(validation_data.get("invalid_decisions")):
        if isinstance(row, dict) and row.get("decision_id"):
            invalid_by_decision.setdefault(str(row["decision_id"]), []).append(row)
    return by_decision, invalid_by_decision


def build_outputs(
    *,
    project: str,
    promotion_dir: Path,
    decisions_path: Path,
    validation_path: Path,
    out_dir: Path,
    plan_data: dict[str, Any],
    queue_data: dict[str, Any],
    status_data: dict[str, Any],
    decisions_data: dict[str, Any],
    validation_data: dict[str, Any],
    core_current_path: Path | None,
    core_rating_path: Path | None,
    strict: bool,
    include_addenda: bool,
    allow_conflict_preview: bool,
) -> dict[str, dict[str, Any]]:
    candidates = [r for r in as_list(plan_data.get("promotion_candidates")) if isinstance(r, dict)]
    queue_items = [r for r in as_list(queue_data.get("approval_items")) if isinstance(r, dict)]
    decisions = [r for r in as_list(decisions_data.get("decisions")) if isinstance(r, dict)]

    candidates_by_id = {str(c.get("promotion_candidate_id")): c for c in candidates if c.get("promotion_candidate_id")}
    queue_by_id = {str(q.get("approval_item_id")): q for q in queue_items if q.get("approval_item_id")}
    valid_by_decision, invalid_by_decision = validation_maps(validation_data)
    current_records = records_from_core(core_current_path, ["normalized_currents", "current_models", "currents"])
    rating_records = records_from_core(core_rating_path, ["normalized_ratings", "rating_models", "ratings"])
    current_missing = core_missing(core_current_path)
    rating_missing = core_missing(core_rating_path)

    decision_counts_by_item: dict[str, int] = {}
    for decision in decisions:
        aid = str(decision.get("approval_item_id") or "")
        decision_counts_by_item[aid] = decision_counts_by_item.get(aid, 0) + 1

    blockers: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    current_entries: list[dict[str, Any]] = []
    rating_entries: list[dict[str, Any]] = []
    addenda_entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    if current_missing:
        warnings.append("core_current_artifact_missing")
    if rating_missing:
        warnings.append("core_rating_artifact_missing")
    if status_data.get("status") == "failed":
        warnings.append("promotion_status_failed")

    processed_decision_ids: set[str] = set()
    for decision in sorted(decisions, key=lambda d: (sort_key(d.get("approval_item_id")), sort_key(d.get("decision_id")))):
        aid = str(decision.get("approval_item_id") or "")
        did = str(decision.get("decision_id") or "")
        pid = decision.get("promotion_candidate_id")
        pid_text = str(pid) if pid is not None else None
        decision_value = str(decision.get("decision") or "pending")
        processed_decision_ids.add(did)

        if decision_counts_by_item.get(aid, 0) > 1:
            blockers.append(blocker("invalid_decision", aid, did, pid_text, f"duplicate decision for approval_item_id={aid}"))
            continue
        queue_item = queue_by_id.get(aid)
        if queue_item is None:
            blockers.append(blocker("approval_queue_mismatch", aid, did, pid_text, f"unknown approval_item_id={aid}"))
            continue
        if pid_text != str(queue_item.get("promotion_candidate_id")):
            blockers.append(blocker("approval_queue_mismatch", aid, did, pid_text, f"decision promotion_candidate_id does not match queue item for {aid}"))
            continue
        if decision.get("safe_to_apply") is True:
            blockers.append(blocker("invalid_decision", aid, did, pid_text, "safe_to_apply true is invalid for PR34"))
            continue
        if decision_value != "approved":
            skipped.append({"approval_item_id": aid, "decision_id": did, "promotion_candidate_id": pid_text, "decision": decision_value, "reason_code": "decision_not_approved"})
            continue
        if strict and status_data.get("status") == "failed":
            blockers.append(blocker("stale_or_failed_promotion_status", aid, did, pid_text, "PR32 promotion status is failed in strict mode"))
            continue
        validation = valid_by_decision.get(did)
        if validation is None:
            if did in invalid_by_decision:
                blockers.append(blocker("approved_decision_invalid", aid, did, pid_text, "PR33 validation marks approved decision invalid"))
            else:
                blockers.append(blocker("missing_decision_validation", aid, did, pid_text, "missing PR33 validation record for approved decision"))
            continue
        if validation.get("validation_status") != "valid":
            blockers.append(blocker("approved_decision_invalid", aid, did, pid_text, "approved decision validation_status is not valid"))
            continue
        if validation.get("safe_for_future_apply_stage") is True:
            blockers.append(blocker("invalid_decision", aid, did, pid_text, "safe_for_future_apply_stage true is invalid for PR34"))
            continue
        if not decision.get("approval_note"):
            blockers.append(blocker("approved_decision_invalid", aid, did, pid_text, "approved decision missing approval_note"))
            continue
        candidate = candidates_by_id.get(str(pid_text))
        if candidate is None:
            blockers.append(blocker("promotion_candidate_missing", aid, did, pid_text, f"unknown promotion_candidate_id={pid_text}"))
            continue

        candidate_kind = str(candidate.get("candidate_kind") or "")
        target_identity = candidate.get("target_identity") if isinstance(candidate.get("target_identity"), dict) else {}
        candidate_value = candidate.get("candidate_value") if isinstance(candidate.get("candidate_value"), dict) else {}
        core_match = candidate.get("core_match") if isinstance(candidate.get("core_match"), dict) else {}
        evidence_refs = as_list(candidate.get("evidence_refs"))
        if not target_identity:
            blockers.append(blocker("missing_target_identity", aid, did, pid_text, "candidate has no target_identity"))
            continue
        if not evidence_refs:
            blockers.append(blocker("missing_evidence", aid, did, pid_text, "candidate has no evidence_refs"))
            continue

        op_blockers: list[str] = []
        op_warnings: list[str] = []
        if candidate_kind in {"role_addendum", "pin_role_addendum", "rail_relationship_hint", "passive_support"}:
            match_status = str(core_match.get("match_status") or "no_core_match")
            dry_run_operation = "would_require_merge_validator"
            op_blockers.append("addenda_requires_merge_validator")
            if candidate_kind == "passive_support":
                op_warnings.append("passive_support_preview_only")
        elif candidate_kind in {"current_model", "rating_model"}:
            match_status, dry_run_operation, class_warnings = classify_against_core(
                candidate_kind,
                target_identity,
                candidate_value,
                core_match,
                current_records,
                rating_records,
                current_missing,
                rating_missing,
            )
            op_warnings.extend(class_warnings)
            if dry_run_operation == "would_block_conflict":
                op_blockers.append("core_conflict")
                if allow_conflict_preview:
                    op_warnings.append("conflict_preview_only_core_write_still_false")
        else:
            blockers.append(blocker("unsupported_candidate_kind", aid, did, pid_text, f"unsupported candidate_kind={candidate_kind}"))
            continue

        op_id = f"op_{digest_id(aid, did, pid_text, candidate_kind, dry_run_operation)}"
        operation = {
            "operation_id": op_id,
            "promotion_candidate_id": pid_text,
            "approval_item_id": aid,
            "decision_id": did,
            "candidate_kind": candidate_kind,
            "dry_run_operation": dry_run_operation,
            "operation_status": "blocked_dry_run" if op_blockers else "preview_dry_run",
            "dry_run_only": True,
            "writes_core_artifact": False,
            "safe_to_apply_in_pr34": False,
            "requires_future_apply_stage": True,
            "target_identity": target_identity,
            "candidate_value": candidate_value,
            "core_match": {"match_status": match_status, "matched_core_record_ids": as_list(core_match.get("matched_core_record_ids"))},
            "approval": {
                "decision": "approved",
                "reviewer": decision.get("reviewer"),
                "reviewed_at_utc": decision.get("reviewed_at_utc"),
                "approval_note": decision.get("approval_note"),
            },
            "preview_target": {
                "preview_only": True,
                "future_core_artifact": candidate_kind in {"current_model", "rating_model"},
                "target_identity": target_identity,
                "candidate_value": candidate_value,
            },
            "blockers": op_blockers,
            "warnings": op_warnings,
        }
        operations.append(operation)

        entry = {
            "operation_id": op_id,
            "promotion_candidate_id": pid_text,
            "target_identity": target_identity,
            "candidate_value": candidate_value,
            "core_match_status": match_status,
            "preview_action": dry_run_operation,
            "blockers": op_blockers,
            "warnings": op_warnings,
        }
        if candidate_kind == "current_model":
            current_entries.append(entry)
        elif candidate_kind == "rating_model":
            rating_entries.append(entry)
        else:
            addenda_entries.append({
                "operation_id": op_id,
                "promotion_candidate_id": pid_text,
                "addenda_kind": candidate_kind,
                "preview_action": "would_require_merge_validator",
                "safe_to_merge_in_pr34": False,
                "merged_addenda": False,
                "blockers": op_blockers,
                "warnings": op_warnings,
            })
            blockers.append(blocker("addenda_requires_merge_validator", aid, did, pid_text, "addenda candidate requires a future merge validator"))

    for queue_item in sorted(queue_items, key=lambda q: sort_key(q.get("approval_item_id"))):
        aid = str(queue_item.get("approval_item_id") or "")
        if decision_counts_by_item.get(aid, 0) == 0:
            blockers.append(blocker("invalid_decision", aid, None, str(queue_item.get("promotion_candidate_id") or ""), "missing decision for approval queue item"))

    source_artifacts = [
        source_artifact("ai_candidate_promotion_plan", promotion_dir / "ai-candidate-promotion-plan.json"),
        source_artifact("ai_candidate_approval_queue", promotion_dir / "ai-candidate-approval-queue.json"),
        source_artifact("ai_candidate_promotion_diff", promotion_dir / "ai-candidate-promotion-diff.json"),
        source_artifact("ai_candidate_promotion_status", promotion_dir / "ai-candidate-promotion-status.json"),
        source_artifact("ai_approval_decisions", decisions_path),
        source_artifact("ai_approval_decision_validation", validation_path),
    ]
    core_artifacts = {
        "core_current_models_normalized": str(core_current_path) if core_current_path else None,
        "core_rating_models_normalized": str(core_rating_path) if core_rating_path else None,
        "core_current_missing": current_missing,
        "core_rating_missing": rating_missing,
    }

    decision_count = len(decisions)
    approved_count = sum(1 for d in decisions if d.get("decision") == "approved")
    rejected_count = sum(1 for d in decisions if d.get("decision") == "rejected")
    needs_info_count = sum(1 for d in decisions if d.get("decision") == "needs_info")
    pending_count = sum(1 for d in decisions if d.get("decision") == "pending")
    invalid_approved = sum(1 for b in blockers if approved_blocker_reason(str(b.get("reason_code"))) and b.get("decision_id") in processed_decision_ids)
    valid_approved = sum(1 for o in operations if o["approval"]["decision"] == "approved" and not o["blockers"])
    blocked_operation_count = len(blockers) + sum(1 for o in operations if o["blockers"])

    summary = {
        "approval_queue_count": len(queue_items),
        "decision_count": decision_count,
        "approved_decision_count": approved_count,
        "rejected_decision_count": rejected_count,
        "needs_info_decision_count": needs_info_count,
        "pending_decision_count": pending_count,
        "valid_approved_decision_count": valid_approved,
        "invalid_approved_decision_count": invalid_approved,
        "dry_run_operation_count": len(operations),
        "current_model_operation_count": sum(1 for o in operations if o["candidate_kind"] == "current_model"),
        "rating_model_operation_count": sum(1 for o in operations if o["candidate_kind"] == "rating_model"),
        "addenda_operation_count": sum(1 for o in operations if o["candidate_kind"] in {"role_addendum", "pin_role_addendum", "rail_relationship_hint", "passive_support"}),
        "would_add_count": sum(1 for o in operations if o["dry_run_operation"] == "would_add"),
        "would_update_count": sum(1 for o in operations if o["dry_run_operation"] == "would_update"),
        "would_skip_duplicate_count": sum(1 for o in operations if o["dry_run_operation"] == "would_skip_duplicate"),
        "would_block_conflict_count": sum(1 for o in operations if o["dry_run_operation"] == "would_block_conflict"),
        "blocked_operation_count": blocked_operation_count,
        "skipped_decision_count": len(skipped),
        "core_current_missing": current_missing,
        "core_rating_missing": rating_missing,
        "applied_anything": False,
        "wrote_core_artifacts": False,
        "ran_ingestion": False,
        "ran_current_allocation": False,
        "ran_calculations": False,
        "merged_addenda": False,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    status_value = "dry_run_failed" if errors else ("dry_run_with_warnings" if warnings or blocked_operation_count else "dry_run_pass")
    generated = utc_now()
    operations = sorted(operations, key=lambda o: (sort_key(o.get("approval_item_id")), sort_key(o.get("operation_id"))))
    blockers = sorted(blockers, key=lambda b: (sort_key(b.get("approval_item_id")), sort_key(b.get("decision_id")), sort_key(b.get("reason_code"))))
    skipped = sorted(skipped, key=lambda s: (sort_key(s.get("approval_item_id")), sort_key(s.get("decision_id"))))

    dry_run = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "dry_run_only": True,
        "source_artifacts": source_artifacts,
        "source_promotion_plan": str(promotion_dir / "ai-candidate-promotion-plan.json"),
        "source_approval_queue": str(promotion_dir / "ai-candidate-approval-queue.json"),
        "source_decisions": str(decisions_path),
        "source_decision_validation": str(validation_path),
        "core_artifacts": core_artifacts,
        "approved_decision_count": approved_count,
        "dry_run_operations": operations,
        "blocked_operations": blockers,
        "skipped_decisions": skipped,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    status = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "status": status_value,
        "dry_run_only": True,
        "applied_anything": False,
        "wrote_core_artifacts": False,
        "ran_ingestion": False,
        "ran_current_allocation": False,
        "ran_calculations": False,
        "merged_addenda": False,
        "safe_to_apply_in_pr34": False,
        "requires_future_apply_stage": True,
        "approved_decision_count": approved_count,
        "dry_run_operation_count": len(operations),
        "blocked_operation_count": blocked_operation_count,
        "skipped_decision_count": len(skipped),
        "errors": errors,
        "warnings": warnings,
    }

    def preview(preview_type: str, entries: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out = {
            "project": project,
            "generated_at_utc": generated,
            "schema_version": SCHEMA_VERSION,
            "dry_run_only": True,
            "preview_type": preview_type,
            "entries": sorted(entries, key=lambda e: sort_key(e.get("operation_id"))),
            "summary": {"entry_count": len(entries)},
            "errors": [],
            "warnings": warnings,
        }
        if extra:
            out.update(extra)
        return out

    return {
        "dry_run": dry_run,
        "status": status,
        "current_preview": preview("current_model_merge_preview", current_entries),
        "rating_preview": preview("rating_model_merge_preview", rating_entries),
        "addenda_preview": preview(
            "addenda_merge_preview",
            addenda_entries if include_addenda or addenda_entries else [],
            {"safe_to_merge_in_pr34": False, "merged_addenda": False},
        ),
        "blockers": {
            "project": project,
            "generated_at_utc": generated,
            "schema_version": SCHEMA_VERSION,
            "dry_run_only": True,
            "blocker_records": blockers,
            "summary": {"total_blockers": len(blockers), "blocked_operation_count": blocked_operation_count},
            "errors": [],
            "warnings": warnings,
        },
    }


def validate_outputs(outputs: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for output in outputs:
        forbidden = sorted(walk_keys(output).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            raise ValueError(f"dry-run output contains forbidden field(s): {', '.join(forbidden)}")
        jsonschema.validate(instance=output, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an approved-only promotion apply dry-run plan.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--promotion-dir", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--decision-validation", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--core-current-models-normalized", default=None)
    parser.add_argument("--core-rating-models-normalized", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-addenda", action="store_true")
    parser.add_argument("--allow-conflict-preview", action="store_true")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        promotion_dir = Path(args.promotion_dir).resolve()
        if not promotion_dir.exists():
            raise FileNotFoundError(f"promotion directory does not exist: {promotion_dir}")
        decisions_path = Path(args.decisions).resolve()
        validation_path = Path(args.decision_validation).resolve()
        out_dir = Path(args.out_dir).resolve()
        for filename in OUTPUTS.values():
            verify_output_path(out_dir / filename, out_dir, args.project)

        plan_data = require_json_object(promotion_dir / "ai-candidate-promotion-plan.json", "promotion plan")
        queue_data = require_json_object(promotion_dir / "ai-candidate-approval-queue.json", "approval queue")
        status_data = safe_load_object(promotion_dir / "ai-candidate-promotion-status.json")
        decisions_data = require_json_object(decisions_path, "decisions")
        validation_data = require_json_object(validation_path, "decision validation")

        core_current = Path(args.core_current_models_normalized).resolve() if args.core_current_models_normalized else None
        core_rating = Path(args.core_rating_models_normalized).resolve() if args.core_rating_models_normalized else None
        outputs = build_outputs(
            project=args.project,
            promotion_dir=promotion_dir,
            decisions_path=decisions_path,
            validation_path=validation_path,
            out_dir=out_dir,
            plan_data=plan_data,
            queue_data=queue_data,
            status_data=status_data,
            decisions_data=decisions_data,
            validation_data=validation_data,
            core_current_path=core_current,
            core_rating_path=core_rating,
            strict=args.strict,
            include_addenda=args.include_addenda,
            allow_conflict_preview=args.allow_conflict_preview,
        )
        validate_outputs(list(outputs.values()), Path(args.schema).resolve())
        for key, filename in OUTPUTS.items():
            write_json(out_dir / filename, outputs[key])
    except (OSError, json.JSONDecodeError, ValueError, jsonschema.ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = outputs["dry_run"]["summary"]
    print(
        "ai promotion apply dry run: "
        f"project={outputs['dry_run']['project']} "
        f"approved={summary['approved_decision_count']} "
        f"operations={summary['dry_run_operation_count']} "
        f"blocked={summary['blocked_operation_count']} "
        f"skipped={summary['skipped_decision_count']} "
        f"out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
