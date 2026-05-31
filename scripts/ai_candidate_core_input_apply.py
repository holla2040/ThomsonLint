#!/usr/bin/env python3
"""Approved promotion apply to isolated candidate core-input files v0."""
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


SCHEMA_VERSION = "ai_candidate_core_input_apply_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_candidate_core_input_apply_schema.json"

OUTPUTS = {
    "manifest": "ai-candidate-core-input-apply-manifest.json",
    "status": "ai-candidate-core-input-apply-status.json",
    "current_input": "ai-candidate-current-model-input.json",
    "rating_input": "ai-candidate-rating-model-input.json",
    "role_addenda": "ai-candidate-role-addenda.json",
    "pin_role_addenda": "ai-candidate-pin-role-addenda.json",
    "rail_hints": "ai-candidate-rail-relationship-hints.json",
    "passive_support": "ai-candidate-passive-support-inputs.json",
    "diff": "ai-candidate-core-input-apply-diff.json",
    "blockers": "ai-candidate-core-input-apply-blockers.json",
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
    "safe_to_apply",
}

BLOCKER_CODES = {
    "missing_dry_run_dir",
    "missing_dry_run_artifact",
    "missing_dry_run_status",
    "malformed_dry_run_artifact",
    "dry_run_status_failed",
    "operation_not_approved_for_candidate_apply",
    "operation_blocked_in_pr34",
    "unsupported_candidate_kind",
    "unsupported_dry_run_operation",
    "missing_target_identity",
    "missing_candidate_value",
    "missing_evidence",
    "duplicate_skipped",
    "addenda_requires_merge_validator",
    "base_input_malformed",
    "output_path_outside_out_dir",
    "attempted_core_write_blocked",
}

PREVIEW_STATUSES = {"preview_only", "preview_dry_run"}
ADDENDA_KIND_TO_KEY = {
    "role_addendum": "role_addenda",
    "pin_role_addendum": "pin_role_addenda",
    "rail_relationship_hint": "rail_hints",
    "passive_support": "passive_support",
}
ADDENDA_KIND_TO_FIELD = {
    "role_addendum": "role_addenda",
    "pin_role_addendum": "pin_role_addenda",
    "rail_relationship_hint": "rail_relationship_hints",
    "passive_support": "passive_support_inputs",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def require_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing {label}: {path}")
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return data


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


def has_forbidden_true_safe_merge(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "safe_to_merge_automatically" and child is True:
                return True
            if has_forbidden_true_safe_merge(child):
                return True
    elif isinstance(value, list):
        return any(has_forbidden_true_safe_merge(child) for child in value)
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


def source_artifact(artifact_type: str, path: Path, notes: str | None = None) -> dict[str, Any]:
    return {"artifact_type": artifact_type, "path": str(path), "notes": notes}


def blocker(reason_code: str, operation_id: str | None, details: str, source: dict[str, Any] | None = None) -> dict[str, Any]:
    if reason_code not in BLOCKER_CODES:
        reason_code = "operation_not_approved_for_candidate_apply"
    return {
        "operation_id": operation_id,
        "promotion_candidate_id": source.get("promotion_candidate_id") if source else None,
        "approval_item_id": source.get("approval_item_id") if source else None,
        "decision_id": source.get("decision_id") if source else None,
        "candidate_kind": source.get("candidate_kind") if source else None,
        "reason_code": reason_code,
        "details": details,
    }


def load_base_records(path: Path | None, labels: list[str]) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        data = require_object(path, "base input")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"base_input_malformed: {exc}") from exc
    for label in labels:
        rows = data.get(label)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    rows = data.get("records")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def operation_evidence(operation: dict[str, Any]) -> list[Any]:
    evidence = operation.get("evidence_refs")
    if isinstance(evidence, list):
        return evidence
    candidate_value = operation.get("candidate_value")
    if isinstance(candidate_value, dict):
        for key in ("evidence_refs", "source_evidence_refs"):
            if isinstance(candidate_value.get(key), list):
                return candidate_value[key]
    approval = operation.get("approval")
    if isinstance(approval, dict) and isinstance(approval.get("evidence_refs"), list):
        return approval["evidence_refs"]
    return []


def candidate_record(operation: dict[str, Any], record_type: str) -> dict[str, Any]:
    operation_id = str(operation.get("operation_id") or "")
    candidate_kind = str(operation.get("candidate_kind") or "")
    target_identity = operation.get("target_identity") if isinstance(operation.get("target_identity"), dict) else {}
    candidate_value = operation.get("candidate_value") if isinstance(operation.get("candidate_value"), dict) else {}
    evidence_refs = operation_evidence(operation)
    return {
        "candidate_record_id": f"candidate_{record_type}_{digest_id(operation_id, candidate_kind, target_identity, candidate_value)}",
        "candidate_input": True,
        "source_pr34_operation_id": operation_id,
        "source_promotion_candidate_id": operation.get("promotion_candidate_id"),
        "source_approval_item_id": operation.get("approval_item_id"),
        "source_decision_id": operation.get("decision_id"),
        "candidate_kind": candidate_kind,
        "target_identity": target_identity,
        "candidate_value": candidate_value,
        "approval": operation.get("approval") if isinstance(operation.get("approval"), dict) else {},
        "pr34_operation": {
            "dry_run_operation": operation.get("dry_run_operation"),
            "operation_status": operation.get("operation_status"),
            "dry_run_only": operation.get("dry_run_only"),
            "writes_core_artifact": operation.get("writes_core_artifact"),
            "safe_to_apply_in_pr34": operation.get("safe_to_apply_in_pr34"),
            "requires_future_apply_stage": operation.get("requires_future_apply_stage"),
        },
        "evidence_refs": evidence_refs,
    }


def is_operation_eligible(operation: dict[str, Any]) -> tuple[bool, str | None]:
    if operation.get("dry_run_only") is not True:
        return False, "operation_not_approved_for_candidate_apply"
    if operation.get("writes_core_artifact") is not False:
        return False, "attempted_core_write_blocked"
    if operation.get("safe_to_apply_in_pr34") is not False:
        return False, "operation_not_approved_for_candidate_apply"
    if operation.get("requires_future_apply_stage") is not True:
        return False, "operation_not_approved_for_candidate_apply"
    if operation.get("operation_status") not in PREVIEW_STATUSES:
        return False, "operation_blocked_in_pr34"
    if operation.get("blockers"):
        return False, "operation_blocked_in_pr34"
    return True, None


def build_outputs(
    *,
    project: str,
    dry_run_dir: Path,
    out_dir: Path,
    dry_run: dict[str, Any],
    status: dict[str, Any],
    blockers_source: dict[str, Any],
    base_current_path: Path | None,
    base_rating_path: Path | None,
    include_addenda: bool,
    strict: bool,
) -> dict[str, dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    blockers: list[dict[str, Any]] = []
    applied_ids: list[str] = []
    skipped_ids: list[str] = []
    blocked_ids: list[str] = []
    duplicate_skips: list[dict[str, Any]] = []
    source_map: list[dict[str, Any]] = []
    addenda_records: dict[str, list[dict[str, Any]]] = {key: [] for key in ADDENDA_KIND_TO_KEY.values()}

    if status.get("status") == "dry_run_failed":
        blockers.append(blocker("dry_run_status_failed", None, "PR34 dry-run status is failed"))
        if strict:
            errors.append("PR34 dry-run status is failed")

    base_current = load_base_records(base_current_path, ["current_model_inputs", "current_model_records", "records"])
    base_rating = load_base_records(base_rating_path, ["rating_model_inputs", "rating_model_records", "records"])
    current_records = list(base_current)
    rating_records = list(base_rating)

    for source_blocker in as_list(dry_run.get("blocked_operations")) + as_list(blockers_source.get("blocker_records")):
        if isinstance(source_blocker, dict):
            op_id = source_blocker.get("operation_id")
            blockers.append(blocker(str(source_blocker.get("reason_code") or "operation_blocked_in_pr34"), str(op_id) if op_id else None, str(source_blocker.get("details") or "blocked in PR34"), source_blocker))

    operations = [row for row in as_list(dry_run.get("dry_run_operations")) if isinstance(row, dict)]
    for operation in sorted(operations, key=lambda row: sort_key(row.get("operation_id"))):
        op_id = str(operation.get("operation_id") or "")
        candidate_kind = str(operation.get("candidate_kind") or "")
        dry_run_operation = str(operation.get("dry_run_operation") or "")
        target_identity = operation.get("target_identity") if isinstance(operation.get("target_identity"), dict) else {}
        candidate_value = operation.get("candidate_value") if isinstance(operation.get("candidate_value"), dict) else {}
        evidence_refs = operation_evidence(operation)

        eligible, reason = is_operation_eligible(operation)
        if not target_identity:
            reason = "missing_target_identity"
            eligible = False
        elif not candidate_value:
            reason = "missing_candidate_value"
            eligible = False
        elif not evidence_refs:
            reason = "missing_evidence"
            eligible = False
        elif candidate_kind not in {"current_model", "rating_model", *ADDENDA_KIND_TO_KEY.keys()}:
            reason = "unsupported_candidate_kind"
            eligible = False
        elif dry_run_operation not in {"would_add", "would_skip_duplicate", "would_require_merge_validator"}:
            reason = "unsupported_dry_run_operation"
            eligible = False

        if not eligible:
            blockers.append(blocker(reason or "operation_not_approved_for_candidate_apply", op_id, f"operation {op_id} is not eligible for PR35 candidate apply", operation))
            blocked_ids.append(op_id)
            continue

        if candidate_kind in ADDENDA_KIND_TO_KEY:
            if not include_addenda:
                blockers.append(blocker("addenda_requires_merge_validator", op_id, "addenda require a future merge validator", operation))
                blocked_ids.append(op_id)
                continue
            record = candidate_record(operation, ADDENDA_KIND_TO_FIELD[candidate_kind])
            record["safe_to_merge_automatically"] = False
            record["merged_addenda"] = False
            addenda_records[ADDENDA_KIND_TO_KEY[candidate_kind]].append(record)
            applied_ids.append(op_id)
            source_map.append({"operation_id": op_id, "candidate_record_id": record["candidate_record_id"], "output": OUTPUTS[ADDENDA_KIND_TO_KEY[candidate_kind]]})
            continue

        if dry_run_operation == "would_skip_duplicate":
            duplicate_skips.append({"operation_id": op_id, "promotion_candidate_id": operation.get("promotion_candidate_id"), "candidate_kind": candidate_kind, "reason_code": "duplicate_skipped"})
            skipped_ids.append(op_id)
            continue
        if dry_run_operation != "would_add":
            blockers.append(blocker("unsupported_dry_run_operation", op_id, f"unsupported dry_run_operation={dry_run_operation}", operation))
            blocked_ids.append(op_id)
            continue

        record_type = "current_model" if candidate_kind == "current_model" else "rating_model"
        record = candidate_record(operation, record_type)
        if candidate_kind == "current_model":
            current_records.append(record)
            source_map.append({"operation_id": op_id, "candidate_record_id": record["candidate_record_id"], "output": OUTPUTS["current_input"]})
        else:
            rating_records.append(record)
            source_map.append({"operation_id": op_id, "candidate_record_id": record["candidate_record_id"], "output": OUTPUTS["rating_input"]})
        applied_ids.append(op_id)

    current_candidate_count = len(current_records) - len(base_current)
    rating_candidate_count = len(rating_records) - len(base_rating)
    addenda_written_count = sum(len(rows) for rows in addenda_records.values())
    addenda_seen_count = sum(1 for op in operations if op.get("candidate_kind") in ADDENDA_KIND_TO_KEY)
    addenda_blocked_count = sum(1 for b in blockers if b["reason_code"] == "addenda_requires_merge_validator")
    blocked_ids = sorted(set(filter(None, blocked_ids + [str(b["operation_id"]) for b in blockers if b.get("operation_id")])))
    skipped_ids = sorted(set(filter(None, skipped_ids)))
    applied_ids = sorted(set(filter(None, applied_ids)))

    summary = {
        "dry_run_operation_count": len(operations),
        "candidate_apply_operation_count": len(applied_ids),
        "current_model_records_added": current_candidate_count,
        "rating_model_records_added": rating_candidate_count,
        "duplicate_operations_skipped": len(duplicate_skips),
        "addenda_operations_seen": addenda_seen_count,
        "addenda_records_written": addenda_written_count,
        "addenda_records_blocked": addenda_blocked_count,
        "blocked_operation_count": len(blockers),
        "skipped_operation_count": len(skipped_ids),
        "base_current_records_preserved": len(base_current),
        "base_rating_records_preserved": len(base_rating),
        "candidate_current_record_count": current_candidate_count,
        "candidate_rating_record_count": rating_candidate_count,
        "wrote_candidate_inputs": True,
        "wrote_core_artifacts": False,
        "wrote_normalized_outputs": False,
        "ran_ingestion": False,
        "ran_current_allocation": False,
        "ran_calculations": False,
        "merged_addenda": False,
        "safe_for_core_apply": False,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }
    generated = utc_now()
    candidate_outputs = {key: str(out_dir / filename) for key, filename in OUTPUTS.items() if key not in {"manifest", "status", "diff", "blockers"}}
    source_artifacts = [
        source_artifact("ai_approved_promotion_apply_dry_run", dry_run_dir / "ai-approved-promotion-apply-dry-run.json"),
        source_artifact("ai_approved_promotion_apply_status", dry_run_dir / "ai-approved-promotion-apply-status.json"),
        source_artifact("ai_promotion_apply_blockers", dry_run_dir / "ai-promotion-apply-blockers.json"),
    ]
    status_value = "candidate_apply_failed" if errors else ("candidate_apply_with_warnings" if warnings or blockers else "candidate_apply_pass")

    manifest = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts,
        "source_dry_run": str(dry_run_dir / "ai-approved-promotion-apply-dry-run.json"),
        "source_dry_run_status": str(dry_run_dir / "ai-approved-promotion-apply-status.json"),
        "candidate_outputs": candidate_outputs,
        "core_outputs_written": False,
        "normalized_outputs_written": False,
        "ran_ingestion": False,
        "ran_current_allocation": False,
        "ran_calculations": False,
        "merged_addenda": False,
        "safe_for_core_apply": False,
        "requires_future_core_apply_stage": True,
        "applied_operation_ids": applied_ids,
        "skipped_operation_ids": skipped_ids,
        "blocked_operation_ids": blocked_ids,
        "summary": summary,
        "errors": errors,
        "warnings": warnings,
    }
    status_artifact = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "status": status_value,
        "candidate_apply_only": True,
        "wrote_candidate_inputs": True,
        "wrote_core_artifacts": False,
        "wrote_normalized_outputs": False,
        "ran_ingestion": False,
        "ran_current_allocation": False,
        "ran_calculations": False,
        "merged_addenda": False,
        "safe_for_core_apply": False,
        "requires_future_core_apply_stage": True,
        "applied_operation_count": len(applied_ids),
        "skipped_operation_count": len(skipped_ids),
        "blocked_operation_count": len(blockers),
        "errors": errors,
        "warnings": warnings,
    }
    current_input = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "candidate_apply_only": True,
        "candidate_input_type": "current_model",
        "base_input": str(base_current_path) if base_current_path else None,
        "base_records_preserved": len(base_current),
        "current_model_inputs": current_records,
        "summary": {"record_count": len(current_records), "candidate_record_count": current_candidate_count},
        "errors": [],
        "warnings": [],
    }
    rating_input = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "candidate_apply_only": True,
        "candidate_input_type": "rating_model",
        "base_input": str(base_rating_path) if base_rating_path else None,
        "base_records_preserved": len(base_rating),
        "rating_model_inputs": rating_records,
        "summary": {"record_count": len(rating_records), "candidate_record_count": rating_candidate_count},
        "errors": [],
        "warnings": [],
    }

    def addenda_artifact(kind: str, field: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project": project,
            "generated_at_utc": generated,
            "schema_version": SCHEMA_VERSION,
            "candidate_apply_only": True,
            "candidate_input_type": kind,
            "safe_to_merge_automatically": False,
            "merged_addenda": False,
            field: sorted(rows, key=lambda r: sort_key(r.get("candidate_record_id"))),
            "summary": {"record_count": len(rows)},
            "errors": [],
            "warnings": [],
        }

    diff = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "candidate_apply_only": True,
        "current_model_records_added": current_candidate_count,
        "rating_model_records_added": rating_candidate_count,
        "duplicate_operations_skipped": duplicate_skips,
        "addenda_preview_records": [row for rows in addenda_records.values() for row in rows],
        "blocked_operations": blockers,
        "source_to_candidate_record_map": sorted(source_map, key=lambda r: sort_key(r.get("operation_id"))),
        "base_input_records_preserved": {"current_model": len(base_current), "rating_model": len(base_rating)},
        "candidate_input_records_added": {"current_model": current_candidate_count, "rating_model": rating_candidate_count, "addenda": addenda_written_count},
        "core_artifacts_unchanged": True,
        "normalized_outputs_unchanged": True,
        "errors": [],
        "warnings": warnings,
    }
    blockers_artifact = {
        "project": project,
        "generated_at_utc": generated,
        "schema_version": SCHEMA_VERSION,
        "candidate_apply_only": True,
        "blocker_records": sorted(blockers, key=lambda b: (sort_key(b.get("operation_id")), sort_key(b.get("reason_code")))),
        "summary": {"blocked_operation_count": len(blockers)},
        "errors": errors,
        "warnings": warnings,
    }

    return {
        "manifest": manifest,
        "status": status_artifact,
        "current_input": current_input,
        "rating_input": rating_input,
        "role_addenda": addenda_artifact("role_addenda", "role_addenda", addenda_records["role_addenda"]),
        "pin_role_addenda": addenda_artifact("pin_role_addenda", "pin_role_addenda", addenda_records["pin_role_addenda"]),
        "rail_hints": addenda_artifact("rail_relationship_hints", "rail_relationship_hints", addenda_records["rail_hints"]),
        "passive_support": addenda_artifact("passive_support_inputs", "passive_support_inputs", addenda_records["passive_support"]),
        "diff": diff,
        "blockers": blockers_artifact,
    }


def validate_outputs(outputs: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for output in outputs:
        forbidden = sorted(walk_keys(output).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            raise ValueError(f"candidate apply output contains forbidden field(s): {', '.join(forbidden)}")
        if has_forbidden_true_safe_merge(output):
            raise ValueError("candidate apply output contains safe_to_merge_automatically true")
        jsonschema.validate(instance=output, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply PR34 approved operations to isolated candidate core-input files.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dry-run-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--base-current-input", default=None)
    parser.add_argument("--base-rating-input", default=None)
    parser.add_argument("--include-addenda", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        dry_run_dir = Path(args.dry_run_dir).resolve()
        if not dry_run_dir.exists():
            raise FileNotFoundError("missing_dry_run_dir")
        dry_run_path = dry_run_dir / "ai-approved-promotion-apply-dry-run.json"
        status_path = dry_run_dir / "ai-approved-promotion-apply-status.json"
        blockers_path = dry_run_dir / "ai-promotion-apply-blockers.json"
        if not dry_run_path.exists():
            raise FileNotFoundError("missing_dry_run_artifact")
        if not status_path.exists():
            raise FileNotFoundError("missing_dry_run_status")
        out_dir = Path(args.out_dir).resolve()
        for filename in OUTPUTS.values():
            verify_output_path(out_dir / filename, out_dir, args.project)

        try:
            dry_run = require_object(dry_run_path, "dry-run artifact")
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed_dry_run_artifact: {exc}") from exc
        status = require_object(status_path, "dry-run status")
        blockers_source = require_object(blockers_path, "dry-run blockers") if blockers_path.exists() else {}
        base_current = Path(args.base_current_input).resolve() if args.base_current_input else None
        base_rating = Path(args.base_rating_input).resolve() if args.base_rating_input else None
        outputs = build_outputs(
            project=args.project,
            dry_run_dir=dry_run_dir,
            out_dir=out_dir,
            dry_run=dry_run,
            status=status,
            blockers_source=blockers_source,
            base_current_path=base_current,
            base_rating_path=base_rating,
            include_addenda=args.include_addenda,
            strict=args.strict,
        )
        validate_outputs(list(outputs.values()), Path(args.schema).resolve())
        for key, filename in OUTPUTS.items():
            write_json(out_dir / filename, outputs[key])
    except (OSError, json.JSONDecodeError, ValueError, jsonschema.ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = outputs["manifest"]["summary"]
    print(
        "ai candidate core input apply: "
        f"project={outputs['manifest']['project']} "
        f"applied={summary['candidate_apply_operation_count']} "
        f"current_added={summary['current_model_records_added']} "
        f"rating_added={summary['rating_model_records_added']} "
        f"blocked={summary['blocked_operation_count']} "
        f"out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
