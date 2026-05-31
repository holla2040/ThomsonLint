#!/usr/bin/env python3
"""AI Approval Queue Editor v0 — create and validate human approval decision artifacts.

PR33 scope only: read PR32 promotion-plan artifacts, produce a decision artifact
(ai-approval-decisions.json) with pending/approved/rejected/needs_info decisions per
approval item, and optionally validate that artifact (ai-approval-decision-validation.json).

This script does not call AI, apply approvals, overwrite core artifacts, run ingestion,
run allocation/calculations, merge addenda, create findings, or make pass/fail or
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


SCHEMA_VERSION_DECISION = "ai_approval_decisions_v1"
SCHEMA_VERSION_VALIDATION = "ai_approval_decision_validation_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_approval_decision_schema.json"

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

ALLOWED_REASON_CODES = {
    "approved_evidence_sufficient",
    "approved_matches_datasheet",
    "approved_engineer_verified",
    "rejected_insufficient_evidence",
    "rejected_conflicts_with_core",
    "rejected_wrong_target",
    "rejected_wrong_unit",
    "rejected_wrong_condition",
    "rejected_duplicate_not_needed",
    "needs_info_missing_datasheet_page",
    "needs_info_ambiguous_condition",
    "needs_info_unclear_target",
    "needs_info_requires_engineer_review",
}

DECISION_STATUSES = {"pending", "approved", "rejected", "needs_info"}


# ---------------------------------------------------------------------------
# Utilities (mirrors PR32 patterns)
# ---------------------------------------------------------------------------


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


def check_forbidden_fields(data: Any) -> list[str]:
    return sorted(walk_keys(data).intersection(FORBIDDEN_FIELDS))


# ---------------------------------------------------------------------------
# Decision template builder
# ---------------------------------------------------------------------------


def build_decision_template(project: str, approval_queue_data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create pending decisions for every approval queue item."""
    approval_items = as_list(approval_queue_data.get("approval_items"))
    source_artifacts = as_list(approval_queue_data.get("source_artifacts"))

    # Sort by approval_item_id for deterministic output
    sorted_items = sorted(approval_items, key=lambda x: safe_id(x.get("approval_item_id", "")))

    decisions: list[dict[str, Any]] = []
    for item in sorted_items:
        aid = str(item.get("approval_item_id", "unknown"))
        pid = item.get("promotion_candidate_id")
        decision_id = f"decision_{digest_id(aid, 'template')}"

        source_queue_item = {
            "review_type": str(item.get("review_type", "")),
            "priority": str(item.get("priority", "")),
            "target_summary": str(item.get("target_summary", "")),
            "candidate_summary": str(item.get("candidate_summary", "")),
            "core_summary": str(item.get("core_summary", "")),
        }

        decisions.append({
            "decision_id": decision_id,
            "approval_item_id": aid,
            "promotion_candidate_id": pid if isinstance(pid, (str, type(None))) else None,
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": source_queue_item,
        })

    summary = {
        "approval_queue_count": len(approval_items),
        "decision_count": len(decisions),
        "pending_count": len(decisions),
        "approved_count": 0,
        "rejected_count": 0,
        "needs_info_count": 0,
        "invalid_decision_count": 0,
        "missing_decision_count": 0,
        "safe_to_apply_count": 0,
        "error_count": 0,
        "warning_count": 0,
    }

    return decisions, summary


# ---------------------------------------------------------------------------
# Decision editor (single-item edit)
# ---------------------------------------------------------------------------


def edit_decision(
    decisions: list[dict[str, Any]],
    approval_item_id: str,
    action: str,
    note: str | None = None,
    reason_code: str | None = None,
    reviewer: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Apply a single approval/reject/needs-info edit to one decision item."""
    errors: list[str] = []
    warnings: list[str] = []

    # Find existing decision for this approval_item_id
    target = None
    for d in decisions:
        if str(d.get("approval_item_id", "")) == approval_item_id:
            target = d
            break

    if target is None:
        errors.append(f"no decision found for approval_item_id={approval_item_id}")
        return decisions, errors, warnings

    now = utc_now()

    if action == "approve":
        if not note:
            errors.append("--approve requires --note")
            return decisions, errors, warnings
        target["decision"] = "approved"
        target["approval_note"] = note
        target["reviewed_at_utc"] = now
        target["reason_code"] = reason_code

    elif action == "reject":
        if not note and not reason_code:
            errors.append("--reject requires --note or --reason-code")
            return decisions, errors, warnings
        target["decision"] = "rejected"
        target["approval_note"] = note
        target["reviewed_at_utc"] = now
        target["reason_code"] = reason_code

    elif action == "needs_info":
        if not note:
            errors.append("--needs-info requires --note")
            return decisions, errors, warnings
        target["decision"] = "needs_info"
        target["approval_note"] = note
        target["reviewed_at_utc"] = now
        target["reason_code"] = reason_code

    else:
        errors.append(f"unknown action: {action}")
        return decisions, errors, warnings

    if reviewer is not None:
        target["reviewer"] = reviewer

    # safe_to_apply always remains false — never set it to true
    target["safe_to_apply"] = False

    return decisions, errors, warnings


# ---------------------------------------------------------------------------
# Decision validator
# ---------------------------------------------------------------------------


def validate_decisions(
    decisions_data: dict[str, Any],
    approval_queue_data: dict[str, Any],
    promotion_plan_data: dict[str, Any] | None,
    strict: bool = False,
    promotion_status_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a decision artifact against PR32 queue/plan data."""
    decisions = as_list(decisions_data.get("decisions"))
    approval_items = as_list(approval_queue_data.get("approval_items"))

    # Build lookup sets from PR32 artifacts
    valid_approval_ids: set[str] = set()
    queue_item_map: dict[str, dict[str, Any]] = {}
    for item in approval_items:
        aid = str(item.get("approval_item_id", ""))
        valid_approval_ids.add(aid)
        queue_item_map[aid] = item

    # Build valid promotion_candidate_id set from plan and queue
    valid_promotion_candidates: set[str | None] = {None}
    if promotion_plan_data:
        for candidate in as_list(promotion_plan_data.get("promotion_candidates", [])):
            cid = candidate.get("promotion_candidate_id")
            if isinstance(cid, str):
                valid_promotion_candidates.add(cid)
    for item in approval_items:
        pid = item.get("promotion_candidate_id")
        if isinstance(pid, str):
            valid_promotion_candidates.add(pid)

    validated: list[dict[str, Any]] = []
    invalid_list: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Track seen approval_item_ids for duplicate detection
    seen_approval_ids: set[str] = set()

    # Sort decisions by decision_id for deterministic output
    sorted_decisions = sorted(decisions, key=lambda d: str(d.get("decision_id", "")))

    for dec in sorted_decisions:
        aid = str(dec.get("approval_item_id", "unknown"))
        did = str(dec.get("decision_id", "unknown"))
        pid = dec.get("promotion_candidate_id")
        decision_val = dec.get("decision", "pending")
        note = dec.get("approval_note")
        reason_code = dec.get("reason_code")
        reviewed_at = dec.get("reviewed_at_utc")

        item_errors: list[str] = []
        item_warnings: list[str] = []

        # Check approval_item_id exists in queue
        if aid not in valid_approval_ids:
            item_errors.append(f"unknown approval_item_id={aid}")

        # Check for duplicate approval_item_id
        if aid in seen_approval_ids:
            item_errors.append(f"duplicate decision for approval_item_id={aid}")
        else:
            seen_approval_ids.add(aid)

        # Check promotion_candidate_id matches plan/queue
        if pid is not None and pid not in valid_promotion_candidates:
            item_errors.append(f"unknown promotion_candidate_id={pid}")

        # Decision-specific validation rules
        if decision_val == "approved":
            if not note:
                item_errors.append("approved decisions require non-empty approval_note")
        elif decision_val == "rejected":
            if not note and not reason_code:
                item_errors.append("rejected decisions require non-empty approval_note or reason_code")
        elif decision_val == "needs_info":
            if not note:
                item_errors.append("needs_info decisions require non-empty approval_note")

        # Validate reviewed_at_utc ISO-8601 format
        if reviewed_at is not None and isinstance(reviewed_at, str):
            try:
                datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                item_errors.append(f"invalid reviewed_at_utc format: {reviewed_at}")

        # Validate reason_code against allowed set
        if reason_code is not None and isinstance(reason_code, str) and reason_code not in ALLOWED_REASON_CODES:
            item_warnings.append(f"unknown reason_code={reason_code}")

        # Check safe_to_apply is false
        if dec.get("safe_to_apply") is True:
            item_errors.append("safe_to_apply must always be false")

        validation_status = "invalid" if item_errors else ("valid" if decision_val != "pending" else "pending")

        validated_entry = {
            "decision_id": did,
            "approval_item_id": aid,
            "promotion_candidate_id": pid,
            "decision": decision_val,
            "validation_status": validation_status,
            "safe_for_future_apply_stage": False,
            "reason_codes": [str(rc)] if reason_code and isinstance(reason_code, str) else None,
            "warnings": item_warnings,
        }

        if item_errors:
            invalid_list.append({
                "decision_id": did if did != "unknown" else None,
                "approval_item_id": aid,
                "validation_status": "invalid",
                "reasons": item_errors,
            })
            errors.extend(item_errors)
        else:
            validated.append(validated_entry)

    # Check for missing decisions (queue items without corresponding decision)
    missing: list[dict[str, Any]] = []
    for aid in sorted(valid_approval_ids):
        if aid not in seen_approval_ids:
            qi = queue_item_map.get(aid, {})
            missing.append({
                "approval_item_id": aid,
                "promotion_candidate_id": qi.get("promotion_candidate_id"),
                "review_type": str(qi.get("review_type", "")),
                "priority": str(qi.get("priority", "")),
                "target_summary": str(qi.get("target_summary", "")),
                "candidate_summary": str(qi.get("candidate_summary", "")),
                "core_summary": str(qi.get("core_summary", "")),
            })

    # Strict mode: check PR32 status
    if strict and promotion_status_data:
        status_val = promotion_status_data.get("status")
        if status_val == "failed":
            warnings.append("PR32 promotion status is failed; decisions marked invalid in strict mode")
            for v in validated:
                v["validation_status"] = "invalid"
                v["warnings"].append("promotion status failed (strict mode)")
            # Move all validated to invalid
            for v in list(validated):
                invalid_list.append({
                    "decision_id": v.get("decision_id"),
                    "approval_item_id": v.get("approval_item_id"),
                    "validation_status": "invalid",
                    "reasons": ["promotion status failed (strict mode)"],
                })
            validated = []

    # Compute summary counts
    decision_count = len(sorted_decisions)
    valid_count = sum(1 for d in validated if d["validation_status"] == "valid")
    invalid_count = len(invalid_list)
    pending_count = sum(1 for d in sorted_decisions if d.get("decision") == "pending")
    approved_count = sum(1 for d in sorted_decisions if d.get("decision") == "approved")
    rejected_count = sum(1 for d in sorted_decisions if d.get("decision") == "rejected")
    needs_info_count = sum(1 for d in sorted_decisions if d.get("decision") == "needs_info")
    safe_for_future_count = 0  # PR33 never sets this to true

    summary = {
        "decision_count": decision_count,
        "valid_decision_count": valid_count,
        "invalid_decision_count": invalid_count,
        "pending_decision_count": pending_count,
        "missing_decision_count": len(missing),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "needs_info_count": needs_info_count,
        "safe_for_future_apply_count": safe_for_future_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }

    validation_pass = invalid_count == 0 and not (strict and promotion_status_data and promotion_status_data.get("status") == "failed")

    return {
        "project": decisions_data.get("project", ""),
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION_VALIDATION,
        "source_artifacts": as_list(decisions_data.get("source_artifacts")),
        "source_decisions": None,  # set by caller
        "validation_pass": validation_pass,
        "validated_decisions": validated,
        "invalid_decisions": invalid_list,
        "missing_decisions": missing,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------


def compute_decision_summary(decisions: list[dict[str, Any]], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "approval_queue_count": 0,  # set by caller from queue data
        "decision_count": len(decisions),
        "pending_count": sum(1 for d in decisions if d.get("decision") == "pending"),
        "approved_count": sum(1 for d in decisions if d.get("decision") == "approved"),
        "rejected_count": sum(1 for d in decisions if d.get("decision") == "rejected"),
        "needs_info_count": sum(1 for d in decisions if d.get("decision") == "needs_info"),
        "invalid_decision_count": 0,  # set by caller from validation
        "missing_decision_count": 0,  # set by caller from validation
        "safe_to_apply_count": 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Approval Queue Editor v0 — create and validate human approval decision artifacts.",
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="Project name")
    parser.add_argument("--promotion-dir", required=True, help="PR32 ai_promotion output directory")
    parser.add_argument("--out", default=None, help="Output path for decisions artifact (default: <promotion-dir>/ai-approval-decisions.json)")
    parser.add_argument("--validate-out", default=None, help="Output path for validation artifact (default: <promotion-dir>/ai-approval-decision-validation.json)")

    # Template mode
    parser.add_argument("--decision-template", action="store_true", help="Create pending decision template for every approval queue item")

    # Edit modes (mutually exclusive)
    edit_group = parser.add_mutually_exclusive_group()
    edit_group.add_argument("--approve", metavar="APPROVAL_ITEM_ID", default=None, help="Approve a single approval item")
    edit_group.add_argument("--reject", metavar="APPROVAL_ITEM_ID", default=None, help="Reject a single approval item")
    edit_group.add_argument("--needs-info", metavar="APPROVAL_ITEM_ID", default=None, help="Mark a single approval item as needs_info")

    # Edit options
    parser.add_argument("--note", default=None, help="Human note for the decision (required for approve/reject/needs-info)")
    parser.add_argument("--reason-code", default=None, help="Reason code for rejection or other decisions")
    parser.add_argument("--reviewer", default=None, help="Optional reviewer label")

    # Validation mode
    parser.add_argument("--decisions", default=None, help="Path to existing decisions artifact to validate")
    parser.add_argument("--validate-only", action="store_true", help="Validate without mutating the decision file")
    parser.add_argument("--strict", action="store_true", help="Strict validation: fail if PR32 status is failed")

    # Schema
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help="Path to JSON schema for validation")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    promotion_dir = Path(args.promotion_dir).resolve()

    # 1. Verify promotion dir exists
    if not promotion_dir.exists():
        print(f"ERROR: promotion directory does not exist: {promotion_dir}", file=sys.stderr)
        return 2

    # 2. Load PR32 artifacts
    queue_path = promotion_dir / "ai-candidate-approval-queue.json"
    plan_path = promotion_dir / "ai-candidate-promotion-plan.json"
    status_path = promotion_dir / "ai-candidate-promotion-status.json"

    if not queue_path.exists():
        print(f"ERROR: missing approval queue: {queue_path}", file=sys.stderr)
        return 2

    try:
        approval_queue_data = load_json(queue_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: malformed approval queue: {exc}", file=sys.stderr)
        return 2

    promotion_plan_data = safe_load(plan_path)
    promotion_status_data = safe_load(status_path)

    # 3. Resolve output paths
    decisions_out = Path(args.out).resolve() if args.out else (promotion_dir / "ai-approval-decisions.json").resolve()
    validate_out = Path(args.validate_out).resolve() if args.validate_out else (promotion_dir / "ai-approval-decision-validation.json").resolve()

    # 4. Verify output paths are safe
    try:
        verify_output_path(decisions_out, promotion_dir, args.project)
        verify_output_path(validate_out, promotion_dir, args.project)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # 5. Branch: --decision-template
    if args.decision_template:
        decisions, summary = build_decision_template(args.project, approval_queue_data)

        source_artifacts = [
            {"artifact_type": "ai_candidate_promotion_plan", "path": str(plan_path), "notes": None},
            {"artifact_type": "ai_candidate_approval_queue", "path": str(queue_path), "notes": None},
        ]

        artifact = {
            "project": args.project,
            "generated_at_utc": utc_now(),
            "schema_version": SCHEMA_VERSION_DECISION,
            "source_artifacts": source_artifacts,
            "source_promotion_plan": str(plan_path),
            "source_approval_queue": str(queue_path),
            "decision_set_status": "draft",
            "decisions": decisions,
            "summary": summary,
            "errors": [],
            "warnings": [],
        }

        write_json(decisions_out, artifact)
        print(f"ai approval decision template: project={args.project} decisions={len(decisions)} out={decisions_out}")
        return 0

    # 6. Branch: edit (--approve / --reject / --needs-info)
    if args.approve or args.reject or args.needs_info:
        action = None
        approval_item_id = None
        if args.approve:
            action = "approve"
            approval_item_id = args.approve
        elif args.reject:
            action = "reject"
            approval_item_id = args.reject
        elif args.needs_info:
            action = "needs_info"
            approval_item_id = args.needs_info

        # Load existing decisions or create from queue
        if Path(args.decisions).exists() if args.decisions else False:
            try:
                decisions_data = load_json(Path(args.decisions))
                decisions = as_list(decisions_data.get("decisions"))
            except (json.JSONDecodeError, ValueError) as exc:
                print(f"ERROR: malformed decisions file: {exc}", file=sys.stderr)
                return 2
        else:
            decisions, _ = build_decision_template(args.project, approval_queue_data)

        decisions, edit_errors, edit_warnings = edit_decision(
            decisions,
            approval_item_id,
            action,
            note=args.note,
            reason_code=args.reason_code,
            reviewer=args.reviewer,
        )

        if edit_errors:
            for err in edit_errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 2

        summary = compute_decision_summary(decisions, edit_errors, edit_warnings)
        source_artifacts = [
            {"artifact_type": "ai_candidate_promotion_plan", "path": str(plan_path), "notes": None},
            {"artifact_type": "ai_candidate_approval_queue", "path": str(queue_path), "notes": None},
        ]

        artifact = {
            "project": args.project,
            "generated_at_utc": utc_now(),
            "schema_version": SCHEMA_VERSION_DECISION,
            "source_artifacts": source_artifacts,
            "source_promotion_plan": str(plan_path),
            "source_approval_queue": str(queue_path),
            "decision_set_status": "draft",
            "decisions": decisions,
            "summary": summary,
            "errors": edit_errors,
            "warnings": edit_warnings,
        }

        write_json(decisions_out, artifact)
        print(f"ai approval decision edited: project={args.project} item={approval_item_id} action={action} out={decisions_out}")
        return 0

    # 7. Branch: --validate-only or --decisions
    decisions_path = Path(args.decisions).resolve() if args.decisions else decisions_out

    if not decisions_path.exists():
        print(f"ERROR: decisions file does not exist: {decisions_path}", file=sys.stderr)
        return 2

    try:
        decisions_data = load_json(decisions_path)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: malformed decisions file: {exc}", file=sys.stderr)
        return 2

    validation_artifact = validate_decisions(
        decisions_data,
        approval_queue_data,
        promotion_plan_data if promotion_plan_data else None,
        strict=args.strict,
        promotion_status_data=promotion_status_data if promotion_status_data else {},
    )
    validation_artifact["source_decisions"] = str(decisions_path)

    write_json(validate_out, validation_artifact)
    summary = validation_artifact.get("summary", {})
    print(
        f"ai approval decision validation: project={args.project} "
        f"valid={summary.get('valid_decision_count', 0)} invalid={summary.get('invalid_decision_count', 0)} "
        f"missing={summary.get('missing_decision_count', 0)} pass={validation_artifact['validation_pass']} out={validate_out}"
    )
    return 0 if validation_artifact["validation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
