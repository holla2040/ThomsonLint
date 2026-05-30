#!/usr/bin/env python3
"""Build ingestion-compatible adapter files from AI candidate inputs.

PR 30 scope only: create explicit manual ingestion inputs and review addenda
from PR29 candidate files. This script does not call AI, run ingestion, merge
topology addenda, overwrite normalized/core artifacts, run calculations, create
findings, or make pass/fail/compliance judgments.
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


SCHEMA_VERSION = "ai_candidate_adapter_manifest_v1"
DEFAULT_PROJECT = "example"
DEFAULT_SCHEMA = "schemas/ai_candidate_adapter_schema.json"
DEFAULT_SOURCE_PRIORITY = "ai_validated_datasheet"

ADAPTER_FILES = {
    "current_model_ingest_input": "ai-current-model-ingest-input.json",
    "rating_model_ingest_input": "ai-rating-model-ingest-input.json",
    "role_resolution_addenda_adapter": "ai-role-resolution-addenda-adapter.json",
    "pin_role_addenda_adapter": "ai-pin-role-addenda-adapter.json",
    "rail_relationship_hints_adapter": "ai-rail-relationship-hints-adapter.json",
    "passive_support_adapter": "ai-passive-support-adapter.json",
    "human_review_adapter": "ai-human-review-adapter.json",
}

CURRENT_FIELDS = {"typ_current_a", "max_current_a", "idle_current_a", "sleep_current_a", "standby_current_a", "input_current_a", "output_current_a"}
CURRENT_RATING_FIELDS = {"current_max", "pin_current_max", "output_current_max", "input_current_max", "continuous_current_max", "hold_current", "trip_current", "thermal_current_limit", "package_current_limit"}
FORBIDDEN_FIELDS = {
    "finding_id", "issue_id", "violation", "severity", "compliance_pass", "compliance_fail", "pass_fail",
    "margin_pass", "margin_fail", "acceptable", "unacceptable", "final_finding", "recommendation_severity",
    "apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing",
}
CORE_OUTPUTS = {
    "{project}-current-models-normalized.json",
    "{project}-rating-models-normalized.json",
    "{project}-topology-current-allocation.json",
    "{project}-topology-copper-calculations.json",
    "{project}-topology-margin-calculations.json",
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


def stable_id(prefix: str, candidate: dict[str, Any]) -> str:
    source_id = candidate.get("record_id") or candidate.get("addendum_id") or candidate.get("hint_id") or candidate.get("candidate_id")
    return f"{prefix}_{safe_id(source_id)}_{digest_id(source_id)}"


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


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): sanitize(child) for key, child in value.items() if str(key) not in FORBIDDEN_FIELDS}
    if isinstance(value, list):
        return [sanitize(child) for child in value]
    return json_safe(value)


def evidence_strings(candidate: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for ref in as_list(candidate.get("evidence_refs")):
        if isinstance(ref, str):
            refs.append(ref)
        elif isinstance(ref, dict):
            source = ref.get("source_file")
            page = ref.get("source_page")
            quote = ref.get("evidence_quote")
            refs.append(":".join(str(part) for part in (source, page, quote) if part not in (None, "")))
    return sorted({ref for ref in refs if ref})


def base_provenance(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_candidate_record_id": candidate.get("record_id") or candidate.get("addendum_id") or candidate.get("hint_id") or candidate.get("candidate_id"),
        "source_patch_id": candidate.get("source_patch_id"),
        "source_packet_id": candidate.get("source_packet_id"),
        "source_item_id": candidate.get("source_item_id"),
        "source_accepted_item_id": candidate.get("source_accepted_item_id"),
        "missing_data_item_ids": [str(value) for value in as_list(candidate.get("missing_data_item_ids"))],
        "ai_evidence_refs": as_list(candidate.get("evidence_refs")),
        "provenance": {
            "source_candidate_record_id": candidate.get("record_id") or candidate.get("addendum_id") or candidate.get("hint_id") or candidate.get("candidate_id"),
            "source_patch_id": candidate.get("source_patch_id"),
            "source_packet_id": candidate.get("source_packet_id"),
            "source_item_id": candidate.get("source_item_id"),
            "source_accepted_item_id": candidate.get("source_accepted_item_id"),
            "basis": candidate.get("basis"),
        },
    }


def skip_candidate(candidate: dict[str, Any], reason: str, detail: str) -> dict[str, Any]:
    source_id = candidate.get("record_id") or candidate.get("addendum_id") or candidate.get("hint_id") or candidate.get("candidate_id")
    return {
        "skipped_candidate_id": f"skipped_{safe_id(reason)}_{digest_id(source_id, reason)}",
        "source_candidate_id": source_id,
        "reason_code": reason,
        "detail": detail,
        "original_candidate": sanitize(candidate),
    }


def human_review_record(candidate: dict[str, Any], reason: str, detail: str, candidate_type: str) -> dict[str, Any]:
    return {
        "review_id": stable_id("ai_review", candidate),
        "reason_code": reason,
        "detail": detail,
        "candidate_type": candidate_type,
        "usable_for_ingestion": False,
        "evidence_refs": as_list(candidate.get("evidence_refs")),
        **base_provenance(candidate),
    }


def candidate_allowed(candidate: dict[str, Any], include_human_review: bool) -> tuple[bool, str | None, str | None]:
    if walk_keys(candidate).intersection(FORBIDDEN_FIELDS):
        return False, "unsupported_candidate_type", "candidate contains forbidden fields"
    if candidate.get("usable_for_ingestion") is False:
        return False, "not_usable_for_ingestion", "candidate is not usable for ingestion"
    if candidate.get("human_review_needed") is True and not include_human_review:
        return False, "human_review_not_included", "candidate requires human review"
    if candidate.get("requires_human_approval_before_ingestion") is True and not include_human_review:
        return False, "human_review_not_included", "candidate requires human approval"
    if as_list(candidate.get("conflict_ids")):
        return False, "conflicted_candidate", "candidate is blocked by unresolved conflict(s)"
    if not as_list(candidate.get("evidence_refs")):
        return False, "missing_evidence", "candidate lacks evidence_refs"
    return True, None, None


def current_adapter_record(candidate: dict[str, Any], source_priority: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ok, reason, detail = candidate_allowed(candidate, False)
    if not ok:
        return None, skip_candidate(candidate, str(reason), str(detail))
    record_type = candidate.get("record_type")
    if record_type == "component_current" and not candidate.get("refdes"):
        return None, skip_candidate(candidate, "missing_target_identity", "component current requires refdes")
    if record_type == "rail_current" and not candidate.get("rail_name"):
        return None, skip_candidate(candidate, "missing_target_identity", "rail current requires rail_name")
    if record_type == "branch_current" and not candidate.get("branch_id"):
        return None, skip_candidate(candidate, "missing_target_identity", "branch current requires branch_id")
    if candidate.get("current_a") is None or candidate.get("current_unit") != "A":
        return None, skip_candidate(candidate, "normalized_value_missing", "current candidate requires current_a in A")
    field_name = str(candidate.get("field_name") or "")
    row = {
        "record_id": stable_id("ai_cur_adapter", candidate),
        "source": source_priority,
        "refdes": candidate.get("refdes"),
        "mpn": candidate.get("mpn"),
        "rail_name": candidate.get("rail_name"),
        "branch_id": candidate.get("branch_id"),
        "field_name": field_name,
        "current_type": field_name.replace("_current_a", "") if field_name in CURRENT_FIELDS else None,
        "value": candidate.get("current_a"),
        "unit": "A",
        "condition": candidate.get("condition"),
        "basis": candidate.get("basis"),
        "confidence": candidate.get("confidence"),
        "evidence_refs": evidence_strings(candidate),
        **base_provenance(candidate),
    }
    if record_type == "component_current" and field_name in CURRENT_FIELDS:
        row[field_name] = candidate.get("current_a")
    elif record_type == "rail_current":
        row["rail_current_a"] = candidate.get("current_a")
    elif record_type == "branch_current":
        row["branch_current_a"] = candidate.get("current_a")
    return row, None


def rating_adapter_record(candidate: dict[str, Any], source_priority: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ok, reason, detail = candidate_allowed(candidate, False)
    if not ok:
        return None, skip_candidate(candidate, str(reason), str(detail))
    if not candidate.get("refdes"):
        return None, skip_candidate(candidate, "missing_target_identity", "rating candidate requires refdes")
    if candidate.get("rating_name") not in CURRENT_RATING_FIELDS:
        return None, skip_candidate(candidate, "unsupported_field_name", "non-current rating is not a current-margin rating adapter input")
    if candidate.get("value_a") is None or candidate.get("unit") != "A":
        return None, skip_candidate(candidate, "normalized_value_missing", "rating candidate requires value_a in A")
    return {
        "record_id": stable_id("ai_rate_adapter", candidate),
        "source": source_priority,
        "target_type": candidate.get("target_type"),
        "refdes": candidate.get("refdes"),
        "pin": candidate.get("pin"),
        "mpn": candidate.get("mpn"),
        "rating_name": candidate.get("rating_name"),
        "value": candidate.get("value_a"),
        "unit": "A",
        "condition": candidate.get("condition"),
        "basis": candidate.get("basis"),
        "confidence": candidate.get("confidence"),
        "evidence_refs": evidence_strings(candidate),
        **base_provenance(candidate),
    }, None


def load_candidate_file(candidate_dir: Path, manifest: dict[str, Any], key: str, fallback: str) -> dict[str, Any]:
    filename = manifest.get("candidate_files", {}).get(key, fallback)
    path = candidate_dir / str(filename)
    if not path.exists():
        return {}
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"candidate file must be a JSON object: {path}")
    return data


def adapter_base(project: str, schema_version: str, source_artifacts: list[dict[str, Any]], array_name: str) -> dict[str, Any]:
    return {
        "project": project,
        "schema_version": schema_version,
        "source_artifacts": source_artifacts,
        array_name: [],
        "metadata": {
            "generated_by": "ai_candidate_adapter_build.py",
            "safe_to_ingest_manually": False,
            "safe_to_overwrite_core_artifacts": False,
            "safe_to_merge_automatically": False,
            "requires_merge_validator": True,
        },
        "errors": [],
        "warnings": [],
    }


def build_adapters(project: str, candidate_dir: Path, source_priority: str, include_human_review: bool, include_role: bool, include_pin: bool, include_rail: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    manifest_path = candidate_dir / "ai-candidate-inputs.json"
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError(f"candidate manifest must be a JSON object: {manifest_path}")
    source_artifacts = [source_artifact("ai_candidate_inputs", manifest_path)]
    current_candidates = load_candidate_file(candidate_dir, manifest, "current_model_candidates", "ai-current-model-candidates.json")
    rating_candidates = load_candidate_file(candidate_dir, manifest, "rating_model_candidates", "ai-rating-model-candidates.json")
    role_candidates = load_candidate_file(candidate_dir, manifest, "role_resolution_addenda", "ai-role-resolution-addenda.json")
    pin_candidates = load_candidate_file(candidate_dir, manifest, "pin_role_addenda", "ai-pin-role-addenda.json")
    rail_candidates = load_candidate_file(candidate_dir, manifest, "rail_relationship_hints", "ai-rail-relationship-hints.json")
    passive_candidates = load_candidate_file(candidate_dir, manifest, "passive_support_candidates", "ai-passive-support-candidates.json")
    human_candidates = load_candidate_file(candidate_dir, manifest, "human_review_candidates", "ai-human-review-candidates.json")

    skipped: list[dict[str, Any]] = []
    human_review: list[dict[str, Any]] = []
    current_out = {
        "project": project,
        "schema_version": "ai_current_model_ingest_input_v1",
        "source": source_priority,
        "source_artifacts": source_artifacts,
        "branch_currents": [],
        "rail_currents": [],
        "component_currents": [],
        "metadata": {"generated_by": "ai_candidate_adapter_build.py", "safe_to_ingest_manually": True, "safe_to_overwrite_core_artifacts": False},
        "errors": [],
        "warnings": [],
    }
    rating_out = {
        "project": project,
        "schema_version": "ai_rating_model_ingest_input_v1",
        "source": source_priority,
        "source_artifacts": source_artifacts,
        "ratings": [],
        "metadata": {"generated_by": "ai_candidate_adapter_build.py", "safe_to_ingest_manually": True, "safe_to_overwrite_core_artifacts": False},
        "errors": [],
        "warnings": [],
    }
    role_out = adapter_base(project, "ai_role_resolution_addenda_adapter_v1", source_artifacts, "role_addenda")
    pin_out = adapter_base(project, "ai_pin_role_addenda_adapter_v1", source_artifacts, "pin_role_addenda")
    rail_out = adapter_base(project, "ai_rail_relationship_hints_adapter_v1", source_artifacts, "rail_relationship_hints")
    passive_out = adapter_base(project, "ai_passive_support_adapter_v1", source_artifacts, "passive_support_records")
    human_out = adapter_base(project, "ai_human_review_adapter_v1", source_artifacts, "human_review_records")

    for candidate in sorted(as_list(current_candidates.get("current_records")), key=lambda row: str(row.get("record_id") or "")):
        row, skip = current_adapter_record(candidate, source_priority)
        if skip:
            skipped.append(skip)
            human_review.append(human_review_record(candidate, skip["reason_code"], skip["detail"], "current_model_candidate"))
            continue
        assert row is not None
        if candidate.get("record_type") == "branch_current":
            current_out["branch_currents"].append(row)
        elif candidate.get("record_type") == "rail_current":
            current_out["rail_currents"].append(row)
        else:
            current_out["component_currents"].append(row)

    for candidate in sorted(as_list(rating_candidates.get("rating_records")), key=lambda row: str(row.get("record_id") or "")):
        row, skip = rating_adapter_record(candidate, source_priority)
        if skip:
            skipped.append(skip)
            human_review.append(human_review_record(candidate, skip["reason_code"], skip["detail"], "rating_model_candidate"))
            continue
        assert row is not None
        rating_out["ratings"].append(row)

    addenda_inputs = [
        (include_role, role_candidates, "role_addenda", role_out, "role_addendum"),
        (include_pin, pin_candidates, "pin_role_addenda", pin_out, "pin_role_addendum"),
        (include_rail, rail_candidates, "rail_relationship_hints", rail_out, "rail_relationship_hint"),
        (True, passive_candidates, "passive_support_records", passive_out, "passive_support_candidate"),
    ]
    for include, data, key, out, candidate_type in addenda_inputs:
        for candidate in sorted(as_list(data.get(key)), key=lambda row: str(row.get("record_id") or row.get("addendum_id") or row.get("hint_id") or "")):
            if not include:
                skipped.append(skip_candidate(candidate, "human_review_not_included", f"{candidate_type} not included by CLI option"))
                continue
            out[key].append(sanitize(candidate))

    for candidate in sorted(as_list(human_candidates.get("human_review_candidates")), key=lambda row: str(row.get("candidate_id") or "")):
        if include_human_review:
            human_review.append(sanitize(candidate))
        else:
            skipped.append(skip_candidate(candidate, "human_review_not_included", "human review candidate excluded by default"))
    human_out["human_review_records"] = sorted(human_review, key=lambda row: str(row.get("review_id") or row.get("candidate_id") or ""))

    adapters = {
        "current_model_ingest_input": current_out,
        "rating_model_ingest_input": rating_out,
        "role_resolution_addenda_adapter": role_out,
        "pin_role_addenda_adapter": pin_out,
        "rail_relationship_hints_adapter": rail_out,
        "passive_support_adapter": passive_out,
        "human_review_adapter": human_out,
    }
    summary = {
        "source_current_candidate_count": len(as_list(current_candidates.get("current_records"))),
        "source_rating_candidate_count": len(as_list(rating_candidates.get("rating_records"))),
        "source_role_addendum_count": len(as_list(role_candidates.get("role_addenda"))),
        "source_pin_addendum_count": len(as_list(pin_candidates.get("pin_role_addenda"))),
        "source_rail_hint_count": len(as_list(rail_candidates.get("rail_relationship_hints"))),
        "source_passive_candidate_count": len(as_list(passive_candidates.get("passive_support_records"))),
        "current_adapter_record_count": len(current_out["branch_currents"]) + len(current_out["rail_currents"]) + len(current_out["component_currents"]),
        "rating_adapter_record_count": len(rating_out["ratings"]),
        "role_addenda_adapter_count": len(role_out["role_addenda"]),
        "pin_role_addenda_adapter_count": len(pin_out["pin_role_addenda"]),
        "rail_relationship_hint_adapter_count": len(rail_out["rail_relationship_hints"]),
        "passive_support_adapter_count": len(passive_out["passive_support_records"]),
        "human_review_adapter_count": len(human_out["human_review_records"]),
        "skipped_candidate_count": len(skipped),
        "safe_to_run_candidate_current_ingest_manually": True,
        "safe_to_run_candidate_rating_ingest_manually": True,
        "safe_to_overwrite_core_artifacts": False,
        "error_count": 0,
        "warning_count": 0,
    }
    adapter_manifest = {
        "project": project,
        "generated_at_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
        "source_artifacts": source_artifacts,
        "source_candidate_manifest": str(manifest_path),
        "adapter_build_pass": True,
        "adapter_files": ADAPTER_FILES,
        "skipped_candidates": skipped,
        "summary": summary,
        "errors": [],
        "warnings": [],
    }
    status = {
        "project": project,
        "status": "adapter_built",
        "adapter_build_pass": True,
        "safe_to_run_candidate_current_ingest_manually": True,
        "safe_to_run_candidate_rating_ingest_manually": True,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_calculations_automatically": False,
        "requires_human_review_count": len(human_out["human_review_records"]),
        "errors": [],
        "warnings": [],
    }
    return adapter_manifest, status, adapters


def validate_outputs(outputs: list[dict[str, Any]], schema_path: Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft7Validator.check_schema(schema)
    for output in outputs:
        forbidden = sorted(walk_keys(output).intersection(FORBIDDEN_FIELDS))
        if forbidden:
            raise ValueError(f"adapter output contains forbidden field(s): {', '.join(forbidden)}")
        jsonschema.validate(instance=output, schema=schema)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build manual ingestion adapter files from AI candidate inputs.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-human-review", action="store_true")
    parser.add_argument("--include-role-addenda", action="store_true")
    parser.add_argument("--include-pin-addenda", action="store_true")
    parser.add_argument("--include-rail-hints", action="store_true")
    parser.add_argument("--source-priority", default=DEFAULT_SOURCE_PRIORITY)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidate_dir = Path(args.candidate_dir)
    out_dir = Path(args.out_dir)
    try:
        if not candidate_dir.exists():
            raise FileNotFoundError(f"missing candidate directory: {candidate_dir}")
        if not (candidate_dir / "ai-candidate-inputs.json").exists():
            raise FileNotFoundError(f"missing candidate manifest: {candidate_dir / 'ai-candidate-inputs.json'}")
        manifest, status, adapters = build_adapters(
            args.project,
            candidate_dir,
            args.source_priority,
            args.include_human_review,
            args.include_role_addenda,
            args.include_pin_addenda,
            args.include_rail_hints,
        )
        if args.strict and manifest["skipped_candidates"]:
            manifest["errors"].append("strict mode disallows skipped candidates")
            manifest["adapter_build_pass"] = False
            status["errors"] = manifest["errors"]
            status["adapter_build_pass"] = False
        validate_outputs([manifest, status, *adapters.values()], Path(args.schema))
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "ai-adapter-manifest.json", manifest)
        write_json(out_dir / "adapter-status.json", status)
        for key, filename in ADAPTER_FILES.items():
            write_json(out_dir / filename, adapters[key])
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(
        "ai candidate adapter build: "
        f"project={manifest['project']} current={summary['current_adapter_record_count']} "
        f"rating={summary['rating_adapter_record_count']} review={summary['human_review_adapter_count']} "
        f"skipped={summary['skipped_candidate_count']} out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
