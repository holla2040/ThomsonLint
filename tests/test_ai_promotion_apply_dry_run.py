from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_promotion_apply_dry_run.py"
SCHEMA = ROOT / "schemas" / "ai_promotion_apply_dry_run_schema.json"
DOC = ROOT / "docs" / "ai_promotion_apply_dry_run.md"
OUTPUT_NAMES = [
    "ai-approved-promotion-apply-dry-run.json",
    "ai-approved-promotion-apply-status.json",
    "ai-approved-current-model-merge-preview.json",
    "ai-approved-rating-model-merge-preview.json",
    "ai-approved-addenda-merge-preview.json",
    "ai-promotion-apply-blockers.json",
]
FORBIDDEN_KEYS = {
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
CORE_OUTPUT_NAMES = {
    "TestProject-current-models-normalized.json",
    "TestProject-rating-models-normalized.json",
    "TestProject-topology-current-allocation.json",
    "TestProject-topology-copper-calculations.json",
    "TestProject-topology-margin-calculations.json",
}


def run_apply(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    out_dir = tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run"
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--project",
            "TestProject",
            "--promotion-dir",
            str(promo_dir),
            "--decisions",
            str(promo_dir / "ai-approval-decisions.json"),
            "--decision-validation",
            str(promo_dir / "ai-approval-decision-validation.json"),
            "--out-dir",
            str(out_dir),
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(all_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(all_values(child))
    return values


def all_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(all_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(all_keys(child))
    return keys


def candidate(
    cid: str,
    kind: str = "current_model",
    match_status: str = "no_core_match",
    identity: dict[str, Any] | None = None,
    value: dict[str, Any] | None = None,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "promotion_candidate_id": cid,
        "candidate_kind": kind,
        "operation": "add_candidate" if match_status in {"no_core_match", "core_missing"} else "conflict_with_core",
        "promotion_status": "pending_human_approval",
        "safe_to_apply_automatically": False,
        "source_candidate_artifact": "exports/TestProject/ai_ingested/example.json",
        "source_candidate_record_id": f"src_{cid}",
        "source_ai_packet_id": "pkt_001",
        "source_ai_patch_id": "patch_001",
        "source_ai_accepted_item_id": "accepted_001",
        "target_identity": identity if identity is not None else {"refdes": "U2", "rail_name": "V3P3"},
        "candidate_value": value if value is not None else {"current_a": 0.085, "basis": "max"},
        "core_match": {"match_status": match_status, "matched_core_record_ids": []},
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "evidence_refs": evidence if evidence is not None else ["datasheets/U2.pdf:92"],
        "missing_data_item_ids": [],
        "approval": {"approval_required": True, "approved": False, "approved_by": None, "approved_at_utc": None, "approval_note": None},
        "warnings": [],
    }


def decision(aid: str, pid: str, value: str = "approved", note: str | None = "reviewed evidence") -> dict[str, Any]:
    return {
        "decision_id": f"decision_{aid}",
        "approval_item_id": aid,
        "promotion_candidate_id": pid,
        "decision": value,
        "reviewer": "qa",
        "reviewed_at_utc": "2026-05-31T00:00:00Z",
        "approval_note": note,
        "reason_code": None,
        "safe_to_apply": False,
        "source_queue_item": {"review_type": "approve_add", "priority": "high", "target_summary": "target", "candidate_summary": "candidate", "core_summary": "core"},
    }


def validation_for(decisions: list[dict[str, Any]], *, safe_future: bool = False, invalid_ids: set[str] | None = None) -> dict[str, Any]:
    invalid_ids = invalid_ids or set()
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for dec in decisions:
        row = {
            "decision_id": dec["decision_id"],
            "approval_item_id": dec["approval_item_id"],
            "promotion_candidate_id": dec["promotion_candidate_id"],
            "decision": dec["decision"],
            "validation_status": "valid",
            "safe_for_future_apply_stage": safe_future,
            "reason_codes": None,
            "warnings": [],
        }
        if dec["decision_id"] in invalid_ids:
            invalid.append({"decision_id": dec["decision_id"], "approval_item_id": dec["approval_item_id"], "validation_status": "invalid", "reasons": ["invalid fixture"]})
        else:
            valid.append(row)
    return {
        "project": "TestProject",
        "generated_at_utc": "2026-05-31T00:00:00Z",
        "schema_version": "ai_approval_decision_validation_v1",
        "source_artifacts": [],
        "source_decisions": None,
        "validation_pass": not invalid,
        "validated_decisions": valid,
        "invalid_decisions": invalid,
        "missing_decisions": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def fixtures(
    tmp_path: Path,
    candidates: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    validation: dict[str, Any] | None = None,
    status: str = "planned",
) -> Path:
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    candidates = candidates or [candidate("pc_current")]
    items = [
        {
            "approval_item_id": f"aq_{i:03d}",
            "promotion_candidate_id": row["promotion_candidate_id"],
            "review_type": "addenda_merge_review" if "addendum" in row["candidate_kind"] or row["candidate_kind"] == "passive_support" else "approve_add",
            "priority": "high",
            "reason_code": "review_required",
            "target_summary": "target",
            "candidate_summary": "candidate",
            "core_summary": "core",
            "evidence_refs": row.get("evidence_refs", []),
            "recommended_action": "review_only",
            "approval_required": True,
            "safe_to_apply_automatically": False,
            "status": "pending",
        }
        for i, row in enumerate(candidates, start=1)
    ]
    decisions = decisions if decisions is not None else [decision(items[0]["approval_item_id"], items[0]["promotion_candidate_id"])]
    validation = validation if validation is not None else validation_for(decisions)
    write_json(
        promo_dir / "ai-candidate-promotion-plan.json",
        {
            "project": "TestProject",
            "generated_at_utc": "2026-05-31T00:00:00Z",
            "schema_version": "ai_candidate_promotion_plan_v1",
            "source_artifacts": [],
            "source_ai_ingested_manifest": None,
            "source_ai_ingested_status": None,
            "core_artifacts": {},
            "promotion_plan_pass": True,
            "promotion_candidates": candidates,
            "blocked_candidates": [],
            "conflicts": [],
            "requires_human_approval": [item["approval_item_id"] for item in items],
            "summary": {},
            "errors": [],
            "warnings": [],
        },
    )
    write_json(promo_dir / "ai-candidate-approval-queue.json", {"project": "TestProject", "schema_version": "ai_candidate_approval_queue_v1", "source_artifacts": [], "approval_items": items, "summary": {}, "errors": [], "warnings": []})
    write_json(promo_dir / "ai-candidate-promotion-diff.json", {"project": "TestProject"})
    write_json(promo_dir / "ai-candidate-promotion-status.json", {"project": "TestProject", "status": status, "promotion_plan_pass": status != "failed", "errors": [], "warnings": []})
    write_json(promo_dir / "ai-approval-decisions.json", {"project": "TestProject", "schema_version": "ai_approval_decisions_v1", "decisions": decisions, "summary": {}, "errors": [], "warnings": []})
    write_json(promo_dir / "ai-approval-decision-validation.json", validation)
    return promo_dir


def outputs(tmp_path: Path) -> dict[str, dict[str, Any]]:
    out_dir = tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run"
    return {name: read_json(out_dir / name) for name in OUTPUT_NAMES}


def dry(tmp_path: Path) -> dict[str, Any]:
    return read_json(tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run" / "ai-approved-promotion-apply-dry-run.json")


def test_missing_and_malformed_inputs_exit_2(tmp_path: Path) -> None:
    result = run_apply(tmp_path)
    assert result.returncode == 2
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    promo_dir.mkdir(parents=True)
    (promo_dir / "ai-candidate-promotion-plan.json").write_text("{bad", encoding="utf-8")
    result = run_apply(tmp_path)
    assert result.returncode == 2


def test_output_shape_for_all_six_artifacts_and_schema_validation(tmp_path: Path) -> None:
    fixtures(tmp_path)
    result = run_apply(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(SCHEMA)
    artifacts = outputs(tmp_path)
    assert set(artifacts) == set(OUTPUT_NAMES)
    for artifact in artifacts.values():
        jsonschema.validate(instance=artifact, schema=schema)
        assert artifact["dry_run_only"] is True
        assert not any(isinstance(v, float) and not math.isfinite(v) for v in all_values(artifact))


def test_approved_current_and_rating_candidates_create_would_add(tmp_path: Path) -> None:
    candidates = [candidate("pc_current"), candidate("pc_rating", "rating_model", value={"rating_a": 2.0, "scope": "connector"})]
    decisions = [decision("aq_001", "pc_current"), decision("aq_002", "pc_rating")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    result = run_apply(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    ops = dry(tmp_path)["dry_run_operations"]
    assert [op["dry_run_operation"] for op in ops] == ["would_add", "would_add"]
    assert {op["candidate_kind"] for op in ops} == {"current_model", "rating_model"}


def test_pending_rejected_and_needs_info_decisions_are_skipped(tmp_path: Path) -> None:
    candidates = [candidate("pc1"), candidate("pc2"), candidate("pc3")]
    decisions = [decision("aq_001", "pc1", "pending", None), decision("aq_002", "pc2", "rejected"), decision("aq_003", "pc3", "needs_info")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    assert run_apply(tmp_path).returncode == 0
    artifact = dry(tmp_path)
    assert artifact["dry_run_operations"] == []
    assert [row["decision"] for row in artifact["skipped_decisions"]] == ["pending", "rejected", "needs_info"]


def test_invalid_approved_decisions_are_blocked(tmp_path: Path) -> None:
    decisions = [
        decision("aq_001", "pc_current", note=None),
        decision("aq_missing", "pc_current"),
        decision("aq_001", "pc_unknown"),
    ]
    decisions[2]["decision_id"] = "decision_unknown_pid"
    decisions[2]["approval_item_id"] = "aq_002"
    candidates = [candidate("pc_current"), candidate("pc_other")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    assert run_apply(tmp_path).returncode == 0
    codes = [row["reason_code"] for row in dry(tmp_path)["blocked_operations"]]
    assert "approved_decision_invalid" in codes
    assert "approval_queue_mismatch" in codes


def test_duplicate_safe_flags_and_validation_flags_are_blocked(tmp_path: Path) -> None:
    first = decision("aq_001", "pc_current")
    second = decision("aq_001", "pc_current")
    second["decision_id"] = "decision_duplicate"
    safe = decision("aq_002", "pc_other")
    safe["safe_to_apply"] = True
    future = decision("aq_003", "pc_third")
    decisions = [first, second, safe, future]
    candidates = [candidate("pc_current"), candidate("pc_other"), candidate("pc_third")]
    validation = validation_for(decisions, safe_future=True)
    fixtures(tmp_path, candidates, decisions, validation)
    assert run_apply(tmp_path).returncode == 0
    details = " ".join(row["details"] for row in dry(tmp_path)["blocked_operations"])
    assert "duplicate decision" in details
    assert "safe_to_apply true" in details
    assert "safe_for_future_apply_stage true" in details


def test_exact_duplicates_and_conflicts_are_classified(tmp_path: Path) -> None:
    candidates = [candidate("pc_dup", match_status="exact_duplicate"), candidate("pc_conflict", match_status="value_conflict")]
    decisions = [decision("aq_001", "pc_dup"), decision("aq_002", "pc_conflict")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    core = write_json(tmp_path / "core-current.json", {"normalized_currents": []})
    assert run_apply(tmp_path, "--core-current-models-normalized", str(core)).returncode == 0
    ops = {op["promotion_candidate_id"]: op for op in dry(tmp_path)["dry_run_operations"]}
    assert ops["pc_dup"]["dry_run_operation"] == "would_skip_duplicate"
    assert ops["pc_conflict"]["dry_run_operation"] == "would_block_conflict"
    assert ops["pc_conflict"]["writes_core_artifact"] is False


def test_allow_conflict_preview_still_does_not_write_core_artifacts(tmp_path: Path) -> None:
    candidates = [candidate("pc_conflict", match_status="value_conflict")]
    decisions = [decision("aq_001", "pc_conflict")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    core = write_json(tmp_path / "core-current.json", {"normalized_currents": []})
    assert run_apply(tmp_path, "--core-current-models-normalized", str(core), "--allow-conflict-preview").returncode == 0
    op = dry(tmp_path)["dry_run_operations"][0]
    assert op["dry_run_operation"] == "would_block_conflict"
    assert op["writes_core_artifact"] is False
    assert op["safe_to_apply_in_pr34"] is False


def test_missing_core_artifacts_create_add_previews_with_warnings(tmp_path: Path) -> None:
    fixtures(tmp_path)
    assert run_apply(tmp_path).returncode == 0
    artifact = dry(tmp_path)
    assert artifact["summary"]["core_current_missing"] is True
    assert "core_current_artifact_missing" in artifact["warnings"]
    assert artifact["dry_run_operations"][0]["dry_run_operation"] == "would_add"


def test_connector_rating_not_expanded_and_regulator_side_not_inferred(tmp_path: Path) -> None:
    value = {"rating_a": 3.0, "connector_scope": "connector_wide"}
    candidates = [candidate("pc_rating", "rating_model", value=value, identity={"connector_ref": "J1"})]
    decisions = [decision("aq_001", "pc_rating")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    assert run_apply(tmp_path).returncode == 0
    op = dry(tmp_path)["dry_run_operations"][0]
    assert op["candidate_value"] == value
    assert "pin" not in op["target_identity"]
    assert "input" not in json.dumps(op).lower()
    assert "output" not in json.dumps(op).lower()


def test_addenda_and_passive_support_require_future_merge_validator(tmp_path: Path) -> None:
    candidates = [candidate("pc_role", "role_addendum"), candidate("pc_passive", "passive_support")]
    decisions = [decision("aq_001", "pc_role"), decision("aq_002", "pc_passive")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    assert run_apply(tmp_path, "--include-addenda").returncode == 0
    artifact = dry(tmp_path)
    assert all(op["dry_run_operation"] == "would_require_merge_validator" for op in artifact["dry_run_operations"])
    addenda = read_json(tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run" / "ai-approved-addenda-merge-preview.json")
    assert addenda["safe_to_merge_in_pr34"] is False
    assert addenda["merged_addenda"] is False


def test_blockers_artifact_and_summary_counts_match(tmp_path: Path) -> None:
    candidates = [candidate("pc_conflict", match_status="value_conflict"), candidate("pc_skip")]
    decisions = [decision("aq_001", "pc_conflict"), decision("aq_002", "pc_skip", "rejected")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    core = write_json(tmp_path / "core-current.json", {"normalized_currents": []})
    assert run_apply(tmp_path, "--core-current-models-normalized", str(core)).returncode == 0
    artifact = dry(tmp_path)
    blockers = read_json(tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run" / "ai-promotion-apply-blockers.json")
    assert artifact["summary"]["blocked_operation_count"] == len(blockers["blocker_records"]) + 1
    assert artifact["summary"]["skipped_decision_count"] == len(artifact["skipped_decisions"])


def test_outputs_stay_inside_out_dir_and_forbidden_core_outputs_not_written(tmp_path: Path) -> None:
    fixtures(tmp_path)
    assert run_apply(tmp_path).returncode == 0
    out_dir = tmp_path / "exports" / "TestProject" / "ai_promotion_apply_dry_run"
    assert {path.name for path in out_dir.iterdir()} == set(OUTPUT_NAMES)
    assert not CORE_OUTPUT_NAMES.intersection({path.name for path in tmp_path.rglob("*.json")})


def test_source_and_core_artifacts_are_not_modified(tmp_path: Path) -> None:
    fixtures(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    core_current = write_json(tmp_path / "core-current.json", {"normalized_currents": [{"refdes": "U2", "rail_name": "V3P3", "current_a": 0.01}]})
    before = {path: path.read_text(encoding="utf-8") for path in list(promo_dir.glob("*.json")) + [core_current]}
    assert run_apply(tmp_path, "--core-current-models-normalized", str(core_current)).returncode == 0
    after = {path: path.read_text(encoding="utf-8") for path in before}
    assert before == after


def test_no_live_ai_network_imports_or_script_invocation_terms_in_implementation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in text
    assert not re.search(r"import (openai|anthropic|requests|httpx|socket)", text)
    assert "google.generative" not in text
    for script_name in ["current_model_ingest.py", "rating_model_ingest.py", "topology_current_allocate.py", "topology_copper_calculate.py", "topology_margin_calculate.py"]:
        assert script_name not in text


def test_no_forbidden_fields_or_core_write_instructions_are_emitted(tmp_path: Path) -> None:
    fixtures(tmp_path)
    assert run_apply(tmp_path).returncode == 0
    for artifact in outputs(tmp_path).values():
        assert not FORBIDDEN_KEYS.intersection(all_keys(artifact))
        payload = json.dumps(artifact)
        assert '"writes_core_artifact": true' not in payload
        assert '"safe_to_apply_in_pr34": true' not in payload
        assert '"applied_anything": true' not in payload


def test_operation_ids_and_order_are_deterministic_and_repeat_stable_except_timestamp(tmp_path: Path) -> None:
    candidates = [candidate("pc_b", "rating_model"), candidate("pc_a")]
    decisions = [decision("aq_002", "pc_b"), decision("aq_001", "pc_a")]
    fixtures(tmp_path, candidates, decisions, validation_for(decisions))
    assert run_apply(tmp_path).returncode == 0
    first = dry(tmp_path)
    first_ops = [(op["operation_id"], op["approval_item_id"]) for op in first["dry_run_operations"]]
    assert first_ops == sorted(first_ops, key=lambda row: row[1])
    assert run_apply(tmp_path).returncode == 0
    second = dry(tmp_path)
    first["generated_at_utc"] = "<ts>"
    second["generated_at_utc"] = "<ts>"
    assert first == second


def test_docs_state_dry_run_limitations_and_future_stage() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in [
        "does not call ai",
        "does not apply approvals",
        "does not write core artifacts",
        "does not run ingestion",
        "does not run allocation",
        "does not run calculations",
        "approved-only",
        "pending, rejected, and needs_info",
        "future apply stages only",
        "addenda merge validator",
    ]:
        assert phrase in text
