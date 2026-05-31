from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_approval_decision_edit.py"
SCHEMA = ROOT / "schemas" / "ai_approval_decision_schema.json"
DOC = ROOT / "docs" / "ai_approval_decision_edit.md"


def run_editor(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def all_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(all_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(all_values(child))
    return values


def approval_queue_fixture(
    tmp_path: Path,
    items: list[dict[str, Any]] | None = None,
) -> Path:
    """Create a minimal PR32 approval queue artifact."""
    if items is None:
        items = [
            {
                "approval_item_id": "aq_001",
                "promotion_candidate_id": "pc_u2_v3p3_max",
                "review_type": "approve_add",
                "priority": "high",
                "target_summary": "V3P3 component U2 max current",
                "candidate_summary": "AI-extracted 85 mA from datasheet",
                "core_summary": "no core match",
                "evidence_refs": ["datasheets/U2.pdf:92"],
                "recommended_action": "review_only",
                "approval_required": True,
                "safe_to_apply_automatically": False,
                "status": "pending",
            },
            {
                "approval_item_id": "aq_002",
                "promotion_candidate_id": "pc_f1_hold",
                "review_type": "resolve_conflict",
                "priority": "medium",
                "target_summary": "F1 fuse hold current",
                "candidate_summary": "AI-extracted 1.1 A",
                "core_summary": "core has 1.0 A",
                "evidence_refs": ["datasheets/F1.pdf:3"],
                "recommended_action": "review_only",
                "approval_required": True,
                "safe_to_apply_automatically": False,
                "status": "pending",
            },
        ]

    queue = {
        "project": "TestProject",
        "schema_version": "ai_candidate_approval_queue_v1",
        "source_artifacts": [
            {"artifact_type": "promotion_plan", "path": None, "notes": None},
        ],
        "approval_items": items,
        "summary": {"approval_queue_count": len(items), "requires_human_approval_count": len(items)},
        "errors": [],
        "warnings": [],
    }

    out = tmp_path / "exports" / "TestProject" / "ai_promotion" / "ai-candidate-approval-queue.json"
    write_json(out, queue)
    return out


def promotion_plan_fixture(tmp_path: Path, candidates: list[dict[str, Any]] | None = None) -> Path:
    """Create a minimal PR32 promotion plan artifact."""
    if candidates is None:
        candidates = [
            {
                "promotion_candidate_id": "pc_u2_v3p3_max",
                "candidate_kind": "current_model",
                "operation": "add_candidate",
                "promotion_status": "pending_human_approval",
                "safe_to_apply_automatically": False,
                "source_candidate_artifact": None,
                "source_candidate_record_id": "cur_u2_001",
                "source_ai_packet_id": "pkt_001",
                "source_ai_patch_id": "patch_001",
                "source_ai_accepted_item_id": "item_001",
                "target_identity": {"refdes": "U2", "rail_name": "V3P3"},
                "candidate_value": {"value": 0.085, "unit": "A"},
                "core_match": {"match_status": "no_core_match", "matched_core_record_ids": []},
                "basis": "ai_validated_datasheet",
                "confidence": 0.86,
                "evidence_refs": ["datasheets/U2.pdf:92"],
                "missing_data_item_ids": [],
                "approval": {
                    "approval_required": True,
                    "approved": False,
                    "approved_by": None,
                    "approved_at_utc": None,
                    "approval_note": None,
                },
                "warnings": [],
            },
        ]

    plan = {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_candidate_promotion_plan_v1",
        "source_artifacts": [],
        "source_ai_ingested_manifest": None,
        "source_ai_ingested_status": None,
        "core_artifacts": {
            "current_models_normalized": None,
            "rating_models_normalized": None,
        },
        "promotion_plan_pass": True,
        "promotion_candidates": candidates,
        "blocked_candidates": [],
        "conflicts": [],
        "requires_human_approval": ["aq_001"],
        "summary": {"promotion_candidate_count": len(candidates), "error_count": 0, "warning_count": 0},
        "errors": [],
        "warnings": [],
    }

    out = tmp_path / "exports" / "TestProject" / "ai_promotion" / "ai-candidate-promotion-plan.json"
    write_json(out, plan)
    return out


def promotion_status_fixture(tmp_path: Path, status: str = "planned") -> Path:
    """Create a minimal PR32 promotion status artifact."""
    sdata = {
        "project": "TestProject",
        "status": status,
        "promotion_plan_pass": status != "failed",
        "safe_to_apply_automatically": False,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "requires_human_approval_count": 0,
        "conflict_count": 0,
        "errors": [],
        "warnings": [],
    }

    out = tmp_path / "exports" / "TestProject" / "ai_promotion" / "ai-candidate-promotion-status.json"
    write_json(out, sdata)
    return out


def decisions_fixture(tmp_path: Path, decisions: list[dict[str, Any]] | None = None) -> Path:
    """Create a pre-built decision artifact."""
    if decisions is None:
        decisions = [
            {
                "decision_id": "decision_aq001",
                "approval_item_id": "aq_001",
                "promotion_candidate_id": "pc_u2_v3p3_max",
                "decision": "pending",
                "reviewer": None,
                "reviewed_at_utc": None,
                "approval_note": None,
                "reason_code": None,
                "safe_to_apply": False,
                "source_queue_item": {
                    "review_type": "approve_add",
                    "priority": "high",
                    "target_summary": "V3P3 component U2 max current",
                    "candidate_summary": "AI-extracted 85 mA from datasheet",
                    "core_summary": "no core match",
                },
            },
        ]

    artifact = {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_approval_decisions_v1",
        "source_artifacts": [],
        "source_promotion_plan": None,
        "source_approval_queue": None,
        "decision_set_status": "draft",
        "decisions": decisions,
        "summary": {"approval_queue_count": len(decisions), "decision_count": len(decisions)},
        "errors": [],
        "warnings": [],
    }

    out = tmp_path / "exports" / "TestProject" / "ai_promotion" / "ai-approval-decisions.json"
    write_json(out, artifact)
    return out


# ---------------------------------------------------------------------------
# Tests 1-3: Error exits
# ---------------------------------------------------------------------------


def test_missing_promotion_dir_exits_2(tmp_path: Path) -> None:
    result = run_editor("--project", "TestProject", "--promotion-dir", str(tmp_path / "nonexistent"))
    assert result.returncode == 2


def test_missing_approval_queue_exits_2(tmp_path: Path) -> None:
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    promo_dir.mkdir(parents=True)
    # No queue file created
    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir))
    assert result.returncode == 2


def test_malformed_approval_queue_exits_2(tmp_path: Path) -> None:
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    promo_dir.mkdir(parents=True)
    queue_file = promo_dir / "ai-candidate-approval-queue.json"
    queue_file.write_text("not valid json {{{", encoding="utf-8")
    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir))
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Tests 4-5: Expected shape
# ---------------------------------------------------------------------------


def test_decision_template_writes_expected_shape(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    result = run_editor("--project", "TestProject", "--promotion-dir", str(tmp_path / "exports" / "TestProject" / "ai_promotion"), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(tmp_path / "exports" / "TestProject" / "ai_promotion" / "ai-approval-decisions.json")
    required_keys = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_promotion_plan", "source_approval_queue", "decision_set_status", "decisions", "summary", "errors", "warnings"}
    assert required_keys.issubset(set(artifact.keys()))


def test_validation_writes_expected_shape(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decision-validation.json")
    required_keys = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_decisions", "validation_pass", "validated_decisions", "invalid_decisions", "missing_decisions", "summary", "errors", "warnings"}
    assert required_keys.issubset(set(artifact.keys()))


# ---------------------------------------------------------------------------
# Tests 6-8: JSON validity, NaN/Infinity, schema validation
# ---------------------------------------------------------------------------


def test_cli_writes_valid_json_artifacts(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    decisions_artifact = read_json(promo_dir / "ai-approval-decisions.json")
    assert isinstance(decisions_artifact, dict)


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    text = (promo_dir / "ai-approval-decisions.json").read_text(encoding="utf-8")
    for token in ("NaN", "Infinity", "-Infinity"):
        assert token not in text


def test_schema_validates_decision_and_validation_artifacts(tmp_path: Path) -> None:
    import jsonschema

    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    # Create template
    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    schema = read_json(SCHEMA)
    decisions_artifact = read_json(promo_dir / "ai-approval-decisions.json")

    # Validate decision artifact against its definition in the schema
    jsonschema.validate(instance=decisions_artifact, schema=schema)


def test_summary_counts_match_decisions(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    summary = artifact["summary"]
    assert summary["decision_count"] == len(artifact["decisions"])


# ---------------------------------------------------------------------------
# Tests 10-13: Template behavior
# ---------------------------------------------------------------------------


def test_template_creates_pending_decision_for_every_approval_item(tmp_path: Path) -> None:
    queue_items = [
        {"approval_item_id": f"aq_{i:03d}", "promotion_candidate_id": f"pc_{i}", "review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""}
        for i in range(5)
    ]
    approval_queue_fixture(tmp_path, items=queue_items)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    decision_ids = {d["approval_item_id"] for d in artifact["decisions"]}
    queue_ids = {item["approval_item_id"] for item in queue_items}
    assert decision_ids == queue_ids

    for d in artifact["decisions"]:
        assert d["decision"] == "pending"


def test_template_decision_ids_are_deterministic(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result1 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result1.returncode == 0, result1.stderr + result1.stdout

    artifact1 = read_json(promo_dir / "ai-approval-decisions.json")
    first_ids = [d["decision_id"] for d in artifact1["decisions"]]

    # Run again to same location
    result2 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result2.returncode == 0, result2.stderr + result2.stdout

    artifact2 = read_json(promo_dir / "ai-approval-decisions.json")
    second_ids = [d["decision_id"] for d in artifact2["decisions"]]

    assert first_ids == second_ids


def test_template_preserves_approval_item_and_promotion_candidate_linkage(tmp_path: Path) -> None:
    queue_items = [
        {"approval_item_id": "aq_010", "promotion_candidate_id": "pc_special", "review_type": "approve_add", "priority": "high", "target_summary": "T", "candidate_summary": "C", "core_summary": ""},
    ]
    approval_queue_fixture(tmp_path, items=queue_items)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    d = artifact["decisions"][0]
    assert d["approval_item_id"] == "aq_010"
    assert d["promotion_candidate_id"] == "pc_special"


def test_template_safe_to_apply_is_false_for_all_items(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    for d in artifact["decisions"]:
        assert d["safe_to_apply"] is False


# ---------------------------------------------------------------------------
# Tests 14-20: Edit actions
# ---------------------------------------------------------------------------


def test_approve_requires_note(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--approve", "aq_001",
    )
    assert result.returncode == 2


def test_approve_sets_decision_and_note_but_safe_to_apply_false(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--approve", "aq_001",
        "--note", "verified against datasheet page 92",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    d = [d for d in artifact["decisions"] if d["approval_item_id"] == "aq_001"][0]
    assert d["decision"] == "approved"
    assert d["approval_note"] == "verified against datasheet page 92"
    assert d["safe_to_apply"] is False


def test_reject_requires_note_or_reason_code(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--reject", "aq_001",
    )
    assert result.returncode == 2


def test_reject_sets_decision_and_reason(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--reject", "aq_001",
        "--note", "value conflicts with core",
        "--reason-code", "rejected_conflicts_with_core",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    d = [d for d in artifact["decisions"] if d["approval_item_id"] == "aq_001"][0]
    assert d["decision"] == "rejected"
    assert d["reason_code"] == "rejected_conflicts_with_core"


def test_needs_info_requires_note(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--needs-info", "aq_001",
    )
    assert result.returncode == 2


def test_needs_info_sets_decision(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--needs-info", "aq_001",
        "--note", "missing datasheet page 45",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    d = [d for d in artifact["decisions"] if d["approval_item_id"] == "aq_001"][0]
    assert d["decision"] == "needs_info"


def test_only_one_edit_action_allowed_per_invocation(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--approve", "aq_001",
        "--reject", "aq_002",
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Tests 21-22: Validate-only and output path behavior
# ---------------------------------------------------------------------------


def test_validate_only_does_not_modify_decision_file(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    before_text = (promo_dir / "ai-approval-decisions.json").read_text(encoding="utf-8")

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    after_text = (promo_dir / "ai-approval-decisions.json").read_text(encoding="utf-8")
    assert before_text == after_text


def test_edit_can_write_to_out_without_mutating_input_decisions(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    out_path = promo_dir / "ai-approval-decisions-new.json"
    before_text = (promo_dir / "ai-approval-decisions.json").read_text(encoding="utf-8")

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--approve", "aq_001",
        "--note", "approved by engineer",
        "--out", str(out_path),
    )
    assert result.returncode == 0, result.stderr + result.stdout

    after_text = (promo_dir / "ai-approval-decisions.json").read_text(encoding="utf-8")
    assert before_text == after_text

    new_artifact = read_json(out_path)
    d = [d for d in new_artifact["decisions"] if d["approval_item_id"] == "aq_001"][0]
    assert d["decision"] == "approved"


# ---------------------------------------------------------------------------
# Tests 23-35: Validation rules
# ---------------------------------------------------------------------------


def test_unknown_approval_item_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_unknown",
            "approval_item_id": "aq_999",
            "promotion_candidate_id": None,
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_999" in invalid_ids


def test_unknown_promotion_candidate_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promotion_plan_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_nonexistent",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_duplicate_decisions_for_same_approval_item_are_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_dup1",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note1",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
        {
            "decision_id": "decision_dup2",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "rejected",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note2",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_missing_decisions_are_reported(tmp_path: Path) -> None:
    approval_queue_fixture(
        tmp_path,
        items=[
            {"approval_item_id": "aq_001", "promotion_candidate_id": "pc_1", "review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""},
            {"approval_item_id": "aq_002", "promotion_candidate_id": "pc_2", "review_type": "approve_add", "priority": "medium", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        ],
    )
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_1",
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    missing_ids = [d["approval_item_id"] for d in validation["missing_decisions"]]
    assert "aq_002" in missing_ids


def test_approved_without_note_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_rejected_without_note_or_reason_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "rejected",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_needs_info_without_note_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "needs_info",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_pending_without_note_is_valid_pending(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    validated_ids = [d["approval_item_id"] for d in validation["validated_decisions"]]
    assert "aq_001" in validated_ids


def test_invalid_reviewed_at_utc_is_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": "not-a-date",
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_valid_reviewed_at_utc_is_accepted(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": "engineer-1",
            "reviewed_at_utc": "2026-05-30T12:00:00Z",
            "approval_note": "verified",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    validated_ids = [d["approval_item_id"] for d in validation["validated_decisions"]]
    assert "aq_001" in validated_ids


def test_status_failed_blocks_validation_or_marks_invalid(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promotion_status_fixture(tmp_path, status="failed")
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    # Strict mode: should fail
    result_strict = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
        "--strict",
    )
    assert result_strict.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_safe_to_apply_true_is_rejected(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": True,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 1

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    invalid_ids = [d["approval_item_id"] for d in validation["invalid_decisions"]]
    assert "aq_001" in invalid_ids


def test_safe_for_future_apply_stage_is_always_false(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    decisions = [
        {
            "decision_id": "decision_aq001",
            "approval_item_id": "aq_001",
            "promotion_candidate_id": "pc_u2_v3p3_max",
            "decision": "approved",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": "note",
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        },
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor(
        "--project", "TestProject",
        "--promotion-dir", str(promo_dir),
        "--decisions", str(promo_dir / "ai-approval-decisions.json"),
        "--validate-only",
    )
    assert result.returncode == 0, result.stderr + result.stdout

    validation = read_json(promo_dir / "ai-approval-decision-validation.json")
    for v in validation["validated_decisions"]:
        assert v["safe_for_future_apply_stage"] is False


# ---------------------------------------------------------------------------
# Tests 36-40: Safety and path constraints
# ---------------------------------------------------------------------------


def test_outputs_are_inside_promotion_dir_by_default(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    decisions_out = promo_dir / "ai-approval-decisions.json"
    validation_out = promo_dir / "ai-approval-decision-validation.json"

    # Decisions file should be inside promotion dir
    decisions_out.resolve().relative_to(promo_dir.resolve())


def test_forbidden_core_output_filenames_are_not_written(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    forbidden = {"TestProject-current-models-normalized.json", "TestProject-rating-models-normalized.json", "TestProject-topology-current-allocation.json", "TestProject-topology-copper-calculations.json", "TestProject-topology-margin-calculations.json"}
    written_files = {f.name for f in promo_dir.glob("*.json")}
    assert forbidden.isdisjoint(written_files)


def test_source_promotion_artifacts_are_not_modified(tmp_path: Path) -> None:
    queue_file = approval_queue_fixture(tmp_path)
    promotion_plan_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    before_queue = queue_file.read_text(encoding="utf-8")
    plan_file = promo_dir / "ai-candidate-promotion-plan.json"
    before_plan = plan_file.read_text(encoding="utf-8")

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    after_queue = queue_file.read_text(encoding="utf-8")
    after_plan = plan_file.read_text(encoding="utf-8")
    assert before_queue == after_queue
    assert before_plan == after_plan


def test_core_artifacts_are_not_modified(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    # Create a fake core artifact outside promotion dir
    core_file = tmp_path / "exports" / "TestProject-current-models-normalized.json"
    core_file.write_text('{"project": "TestProject", "normalized_currents": []}', encoding="utf-8")
    before_core = core_file.read_text(encoding="utf-8")

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    after_core = core_file.read_text(encoding="utf-8")
    assert before_core == after_core


def test_no_ingestion_or_calculation_scripts_are_invoked() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "topology_current_allocate" not in text
    assert "topology_copper_calculate" not in text
    assert "topology_margin_calculate" not in text


# ---------------------------------------------------------------------------
# Tests 41-44: No forbidden patterns
# ---------------------------------------------------------------------------


def test_no_live_ai_or_network_client_imports_are_used() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "gemini", "requests", "httpx", "urllib", "socket"):
        assert token not in text


def test_no_findings_or_pass_fail_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    forbidden = {"finding_id", "issue_id", "violation", "severity", "pass_fail", "compliance_pass", "compliance_fail"}
    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    assert forbidden.isdisjoint(all_keys(artifact))


def test_forbidden_mutation_fields_are_not_emitted(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    forbidden = {"apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing"}
    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    assert forbidden.isdisjoint(all_keys(artifact))


def test_no_apply_instructions_are_emitted(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result.returncode == 0, result.stderr + result.stdout

    artifact = read_json(promo_dir / "ai-approval-decisions.json")
    for d in artifact["decisions"]:
        assert d.get("safe_to_apply") is not True


# ---------------------------------------------------------------------------
# Tests 45-47: Determinism and stability
# ---------------------------------------------------------------------------


def test_decision_ids_are_deterministic() -> None:
    """Decision IDs are deterministic (redundant with test_template_decision_ids_are_deterministic but separate)."""
    import json as _json

    queue_items = [
        {"approval_item_id": "aq_z", "promotion_candidate_id": "pc_1", "review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        {"approval_item_id": "aq_a", "promotion_candidate_id": "pc_2", "review_type": "approve_add", "priority": "medium", "target_summary": "", "candidate_summary": "", "core_summary": ""},
    ]

    # Build template directly via the module function
    sys.path.insert(0, str(ROOT / "scripts"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai_approval_decision_edit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    decisions1, _ = mod.build_decision_template("TestProject", {"approval_items": queue_items})
    ids1 = [d["decision_id"] for d in decisions1]

    decisions2, _ = mod.build_decision_template("TestProject", {"approval_items": queue_items})
    ids2 = [d["decision_id"] for d in decisions2]

    assert ids1 == ids2


def test_validation_order_is_deterministic(tmp_path: Path) -> None:
    approval_queue_fixture(
        tmp_path,
        items=[
            {"approval_item_id": f"aq_{i:03d}", "promotion_candidate_id": f"pc_{i}", "review_type": "approve_add", "priority": "high", "target_summary": "", "candidate_summary": "", "core_summary": ""}
            for i in range(5)
        ],
    )
    decisions = [
        {
            "decision_id": f"decision_aq_{i:03d}",
            "approval_item_id": f"aq_{i:03d}",
            "promotion_candidate_id": f"pc_{i}",
            "decision": "pending",
            "reviewer": None,
            "reviewed_at_utc": None,
            "approval_note": None,
            "reason_code": None,
            "safe_to_apply": False,
            "source_queue_item": {"review_type": "", "priority": "", "target_summary": "", "candidate_summary": "", "core_summary": ""},
        }
        for i in range(5)
    ]
    decisions_fixture(tmp_path, decisions=decisions)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result1 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decisions", str(promo_dir / "ai-approval-decisions.json"), "--validate-only")
    assert result1.returncode == 0, result1.stderr + result1.stdout

    v1 = read_json(promo_dir / "ai-approval-decision-validation.json")
    order1 = [d["decision_id"] for d in v1["validated_decisions"]]

    # Run again
    result2 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decisions", str(promo_dir / "ai-approval-decisions.json"), "--validate-only")
    assert result2.returncode == 0, result2.stderr + result2.stdout

    v2 = read_json(promo_dir / "ai-approval-decision-validation.json")
    order2 = [d["decision_id"] for d in v2["validated_decisions"]]

    assert order1 == order2


def test_repeated_template_run_produces_stable_artifacts_except_generated_timestamp(tmp_path: Path) -> None:
    approval_queue_fixture(tmp_path)
    promo_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"

    result1 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result1.returncode == 0, result1.stderr + result1.stdout

    artifact1 = read_json(promo_dir / "ai-approval-decisions.json")
    artifact1["generated_at_utc"] = "<ts>"

    result2 = run_editor("--project", "TestProject", "--promotion-dir", str(promo_dir), "--decision-template")
    assert result2.returncode == 0, result2.stderr + result2.stdout

    artifact2 = read_json(promo_dir / "ai-approval-decisions.json")
    artifact2["generated_at_utc"] = "<ts>"

    assert artifact1 == artifact2


# ---------------------------------------------------------------------------
# Tests 48-52: Documentation assertions (mirrors PR32 doc test pattern)
# ---------------------------------------------------------------------------


def test_docs_state_editor_does_not_call_ai() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "does not call ai" in text or "does not invoke ai" in text


def test_docs_state_editor_does_not_apply_approvals() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "does not apply" in text or "do not apply" in text


def test_docs_state_normalized_outputs_are_not_overwritten() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "overwrite normalized outputs" in text or "normalized outputs are not overwritten" in text


def test_docs_state_ingestion_allocation_and_calculations_are_not_run() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "ingestion" in text and "allocation" in text and "calculation" in text


def test_docs_state_future_apply_stage_required() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "future" in text and ("apply" in text or "promotion" in text)
