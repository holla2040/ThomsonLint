from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_candidate_promotion_plan.py"
SCHEMA = ROOT / "schemas" / "ai_candidate_promotion_schema.json"
DOC = ROOT / "docs" / "ai_candidate_promotion_plan.md"


def run_plan(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence() -> list[str]:
    return ["datasheets/U2.pdf:92:IDD max 85 mA"]


def current_record(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "cur_component_current_u2_v3p3_000001_max",
        "record_type": "component_current",
        "target_type": "component",
        "branch_id": None,
        "rail_name": "V3P3",
        "net_name": None,
        "refdes": "U2",
        "pin": None,
        "value": 0.085,
        "unit": "A",
        "current_type": "max",
        "basis": "ai_validated_datasheet",
        "source": "current_model",
        "confidence": 0.86,
        "evidence_refs": evidence(),
        "source_artifacts": [],
        "usable_for_calculation": False,
        "human_review_needed": False,
        "missing_data_manifest_item_ids": ["mdi_u2_current"],
        "missing_data_group_ids": [],
        "warnings": [],
        "provenance": {"original_value": 0.085, "original_unit": "A"},
    }
    row.update(overrides)
    return row


def rating_record(**overrides: Any) -> dict[str, Any]:
    row = {
        "rating_id": "rating_fuse_f1_unknown_hold_current_000001",
        "source_record_id": "cur_rating_fuse_f1_unknown_000001",
        "target_type": "fuse",
        "normalized_target_type": "fuse",
        "refdes": "F1",
        "pin": None,
        "rail_name": None,
        "branch_id": None,
        "net_name": None,
        "rating_name": "hold_current",
        "normalized_rating_name": "hold_current",
        "value_a": 1.1,
        "unit": "A",
        "original_value": 1.1,
        "original_unit": "A",
        "original_rating_name": "hold_current",
        "basis": "ai_validated_datasheet",
        "source": "current_models_normalized",
        "confidence": 0.86,
        "evidence_refs": ["datasheets/F1.pdf:3:Hold current 1.1 A"],
        "source_artifacts": [],
        "usable_for_margin_calculation": True,
        "human_review_needed": False,
        "applies_to_calculation_families": ["fuse_margin"],
        "missing_data_manifest_item_ids": ["mdi_f1_rating"],
        "missing_data_group_ids": [],
        "resolution_path": None,
        "resolution_queue": None,
        "warnings": [],
    }
    row.update(overrides)
    return row


def write_ai_ingested_dir(
    path: Path,
    *,
    currents: list[dict[str, Any]] | None = None,
    ratings: list[dict[str, Any]] | None = None,
    human_records: list[dict[str, Any]] | None = None,
    manifest_text: str | None = None,
) -> Path:
    manifest = {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_candidate_ingestion_workflow_v1",
        "source_artifacts": [],
        "source_adapter_manifest": "adapter_manifest.json",
        "source_adapter_status": "adapter_status.json",
        "workflow_pass": True,
        "outputs": {},
        "steps": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }
    status = {
        "project": "TestProject",
        "status": "completed",
        "workflow_pass": True,
        "safe_to_use_as_candidate_inputs": True,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_current_allocation_automatically": False,
        "safe_to_rerun_calculations_automatically": False,
        "current_ingest_pass": True,
        "rating_current_ingest_pass": True,
        "rating_ingest_pass": True,
        "requires_human_review_count": len(human_records or []),
        "errors": [],
        "warnings": [],
    }
    if manifest_text is None:
        write_json(path / "ai-candidate-ingestion-manifest.json", manifest)
    else:
        path.mkdir(parents=True, exist_ok=True)
        (path / "ai-candidate-ingestion-manifest.json").write_text(manifest_text, encoding="utf-8")
    write_json(path / "ai-candidate-ingestion-status.json", status)
    write_json(path / "ai-current-models-normalized.json", {"project": "TestProject", "normalized_currents": currents if currents is not None else [current_record()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-rating-current-models-normalized.json", {"project": "TestProject", "normalized_currents": [], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-rating-models-normalized.json", {"project": "TestProject", "normalized_ratings": ratings if ratings is not None else [rating_record()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-addenda-index.json", {
        "project": "TestProject",
        "schema_version": "ai_addenda_index_v1",
        "source_artifacts": [],
        "role_resolution_addenda_adapter": str(path / "role.json"),
        "pin_role_addenda_adapter": str(path / "pin.json"),
        "rail_relationship_hints_adapter": str(path / "rail.json"),
        "passive_support_adapter": str(path / "passive.json"),
        "summary": {},
        "safe_to_merge_automatically": False,
        "requires_merge_validator": True,
        "errors": [],
        "warnings": [],
    })
    write_json(path / "role.json", {"role_addenda": [{"addendum_id": "role_1"}]})
    write_json(path / "pin.json", {"pin_role_addenda": [{"addendum_id": "pin_1"}]})
    write_json(path / "rail.json", {"rail_relationship_hints": [{"hint_id": "rail_1"}]})
    write_json(path / "passive.json", {"passive_support_records": [{"record_id": "passive_1"}]})
    write_json(path / "ai-human-review-index.json", {"human_review_records": human_records or [{"review_id": "human_1", "reason_code": "medium_confidence"}], "workflow_review_records": []})
    write_json(path / "ai-candidate-ingestion-review.json", {"project": "TestProject"})
    return path


def write_core_current(path: Path, records: list[dict[str, Any]]) -> Path:
    return write_json(path, {"project": "TestProject", "normalized_currents": records, "summary": {}, "errors": [], "warnings": []})


def write_core_rating(path: Path, records: list[dict[str, Any]]) -> Path:
    return write_json(path, {"project": "TestProject", "normalized_ratings": records, "summary": {}, "errors": [], "warnings": []})


def invoke(
    tmp_path: Path,
    *,
    currents: list[dict[str, Any]] | None = None,
    ratings: list[dict[str, Any]] | None = None,
    core_currents: list[dict[str, Any]] | None = None,
    core_ratings: list[dict[str, Any]] | None = None,
    include_addenda: bool = False,
    include_human_review: bool = False,
    manifest_text: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path | None, Path | None]:
    ai_dir = write_ai_ingested_dir(tmp_path / "exports" / "TestProject" / "ai_ingested", currents=currents, ratings=ratings, manifest_text=manifest_text)
    core_current_path = write_core_current(tmp_path / "exports" / "TestProject-current-models-normalized.json", core_currents) if core_currents is not None else None
    core_rating_path = write_core_rating(tmp_path / "exports" / "TestProject-rating-models-normalized.json", core_ratings) if core_ratings is not None else None
    out_dir = tmp_path / "exports" / "TestProject" / "ai_promotion"
    args = ["--project", "TestProject", "--ai-ingested-dir", str(ai_dir), "--out-dir", str(out_dir)]
    if core_current_path:
        args.extend(["--core-current-models-normalized", str(core_current_path)])
    if core_rating_path:
        args.extend(["--core-rating-models-normalized", str(core_rating_path)])
    if include_addenda:
        args.append("--include-addenda")
    if include_human_review:
        args.append("--include-human-review")
    return run_plan(*args), out_dir, ai_dir, core_current_path, core_rating_path


def artifact_paths(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.json"))


def plan(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-promotion-plan.json")


def queue(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-approval-queue.json")


def status(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-promotion-status.json")


def diff(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-promotion-diff.json")


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


def only_candidate(out_dir: Path) -> dict[str, Any]:
    candidates = plan(out_dir)["promotion_candidates"]
    assert len(candidates) == 1
    return candidates[0]


def test_missing_ai_ingested_dir_exits_2(tmp_path: Path) -> None:
    result = run_plan("--project", "TestProject", "--ai-ingested-dir", str(tmp_path / "missing"), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_missing_ai_ingested_manifest_exits_2(tmp_path: Path) -> None:
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    result = run_plan("--project", "TestProject", "--ai-ingested-dir", str(ai_dir), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_malformed_ai_ingested_manifest_exits_2(tmp_path: Path) -> None:
    result, _, _, _, _ = invoke(tmp_path, manifest_text="{bad")
    assert result.returncode == 2


def test_output_directory_shape_created(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = set(["ai-candidate-promotion-plan.json", "ai-candidate-approval-queue.json", "ai-candidate-promotion-diff.json", "ai-candidate-promotion-status.json", "ai-addenda-promotion-review.json", "ai-human-review-promotion-index.json"])
    assert expected == {path.name for path in artifact_paths(out_dir)}


def test_plan_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_ai_ingested_manifest", "source_ai_ingested_status", "core_artifacts", "promotion_plan_pass", "promotion_candidates", "blocked_candidates", "conflicts", "requires_human_approval", "summary", "errors", "warnings"}
    assert expected.issubset(plan(out_dir))


def test_status_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "status", "promotion_plan_pass", "safe_to_apply_automatically", "safe_to_overwrite_core_artifacts", "safe_to_rerun_current_allocation_automatically", "safe_to_rerun_calculations_automatically", "requires_human_approval_count", "conflict_count", "errors", "warnings"}
    assert expected.issubset(status(out_dir))


def test_cli_writes_valid_json_artifacts(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        assert isinstance(read_json(path), dict)


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        for value in all_values(read_json(path)):
            assert not (isinstance(value, float) and not math.isfinite(value))


def test_schema_validates_all_promotion_artifacts(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, include_addenda=True, include_human_review=True)
    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(SCHEMA)
    for path in artifact_paths(out_dir):
        jsonschema.validate(instance=read_json(path), schema=schema)


def test_summary_counts_match_outputs(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    summary = plan(out_dir)["summary"]
    assert summary["promotion_candidate_count"] == len(plan(out_dir)["promotion_candidates"])
    assert summary["approval_queue_count"] == len(queue(out_dir)["approval_items"])
    assert summary["conflict_count"] == len(plan(out_dir)["conflicts"])


def test_current_candidate_without_core_match_creates_add_candidate(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert any(row["candidate_kind"] == "current_model" and row["operation"] == "add_candidate" for row in plan(out_dir)["promotion_candidates"])


def test_current_candidate_matching_core_value_is_exact_duplicate(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_currents=[current_record()], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert any(row["operation"] == "duplicate_existing" for row in plan(out_dir)["promotion_candidates"] if row["candidate_kind"] == "current_model")


def test_current_candidate_different_value_creates_conflict(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_currents=[current_record(value=0.1)], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert any(row["operation"] == "conflict_with_core" for row in plan(out_dir)["promotion_candidates"] if row["candidate_kind"] == "current_model")


def test_current_candidate_different_unit_creates_conflict(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_currents=[current_record(unit="mA")], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert plan(out_dir)["conflicts"][0]["warnings"] == ["conflicting_core_unit"]


def test_current_candidate_missing_identity_is_blocked(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[current_record(refdes=None, rail_name=None, branch_id=None)], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert plan(out_dir)["blocked_candidates"][0]["warnings"] == ["missing_target_identity"]


def test_core_current_missing_creates_add_candidates_with_warning(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    candidate = next(row for row in plan(out_dir)["promotion_candidates"] if row["candidate_kind"] == "current_model")
    assert candidate["core_match"]["match_status"] == "core_missing"
    assert plan(out_dir)["warnings"]


def test_rating_candidate_without_core_match_creates_add_candidate(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["operation"] == "add_candidate"


def test_rating_candidate_matching_core_value_is_exact_duplicate(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record()])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["operation"] == "duplicate_existing"


def test_rating_candidate_different_value_creates_conflict(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record(value_a=1.2)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["operation"] == "conflict_with_core"


def test_rating_candidate_different_unit_creates_conflict(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record(unit="mA")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["warnings"] == ["conflicting_core_unit"]


def test_rating_candidate_missing_identity_is_blocked(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], ratings=[rating_record(refdes=None, rail_name=None, branch_id=None)], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["operation"] == "needs_human_review"


def test_connector_wide_rating_is_not_expanded_to_pins(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], ratings=[rating_record(target_type="connector", normalized_target_type="connector", refdes="J1", pin=None, normalized_rating_name="current_max", rating_name="current_max")], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["target_identity"]["pin"] is None


def test_regulator_input_output_side_is_not_inferred(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], ratings=[rating_record(target_type="regulator", normalized_target_type="regulator", refdes="U12", normalized_rating_name="current_max", rating_name="current_max")], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["target_identity"]["target_type"] == "regulator"


def test_core_rating_missing_creates_add_candidates_with_warning(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert only_candidate(out_dir)["core_match"]["match_status"] == "core_missing"


def test_add_candidate_requires_human_approval(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert all(row["approval"]["approval_required"] for row in plan(out_dir)["promotion_candidates"])


def test_conflict_requires_human_approval_high_priority(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record(value_a=1.2)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert queue(out_dir)["approval_items"][0]["priority"] == "high"


def test_exact_duplicate_gets_low_priority_review(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record()])
    assert result.returncode == 0, result.stderr + result.stdout
    assert queue(out_dir)["approval_items"][0]["priority"] == "low"


def test_no_candidate_is_auto_approved(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert all(row["approval"]["approved"] is False for row in plan(out_dir)["promotion_candidates"])


def test_safe_to_apply_automatically_is_always_false(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert status(out_dir)["safe_to_apply_automatically"] is False
    assert all(row["safe_to_apply_automatically"] is False for row in plan(out_dir)["promotion_candidates"])


def test_promotion_diff_contains_add_duplicate_conflict_blocked_sections(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert set(diff(out_dir)["current_model_diff"]) == {"add_candidates", "exact_duplicates", "conflicts", "blocked"}
    assert set(diff(out_dir)["rating_model_diff"]) == {"add_candidates", "exact_duplicates", "conflicts", "blocked"}


def test_status_safety_booleans_prevent_auto_apply_and_auto_calculation_rerun(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    data = status(out_dir)
    assert data["safe_to_apply_automatically"] is False
    assert data["safe_to_overwrite_core_artifacts"] is False
    assert data["safe_to_rerun_calculations_automatically"] is False


def test_status_records_conflict_and_approval_counts(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[], core_currents=[], core_ratings=[rating_record(value_a=1.2)])
    assert result.returncode == 0, result.stderr + result.stdout
    assert status(out_dir)["conflict_count"] == 1
    assert status(out_dir)["requires_human_approval_count"] == 1


def test_addenda_promotion_review_indexes_role_pin_rail_passive_addenda(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, include_addenda=True)
    assert result.returncode == 0, result.stderr + result.stdout
    addenda = read_json(out_dir / "ai-addenda-promotion-review.json")
    assert addenda["summary"]["role_addenda_review_count"] == 1
    assert addenda["summary"]["pin_role_addenda_review_count"] == 1
    assert addenda["summary"]["rail_relationship_hint_review_count"] == 1
    assert addenda["summary"]["passive_support_review_count"] == 1


def test_addenda_review_marks_safe_to_merge_automatically_false(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, include_addenda=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-addenda-promotion-review.json")["safe_to_merge_automatically"] is False


def test_human_review_promotion_index_carries_forward_pr31_human_review_records(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, include_human_review=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-human-review-promotion-index.json")["summary"]["human_review_record_count"] == 1


def test_human_review_promotion_index_includes_blocked_candidates_and_conflicts(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path, currents=[current_record(refdes=None, rail_name=None, branch_id=None)], core_currents=[current_record(value=0.1)], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    index = read_json(out_dir / "ai-human-review-promotion-index.json")
    assert index["summary"]["blocked_candidate_count"] >= 1


def test_outputs_are_inside_out_dir(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        path.resolve().relative_to(out_dir.resolve())


def test_forbidden_core_output_filenames_are_not_written(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"TestProject-current-models-normalized.json", "TestProject-rating-models-normalized.json", "TestProject-topology-current-allocation.json", "TestProject-topology-copper-calculations.json", "TestProject-topology-margin-calculations.json"}
    assert forbidden.isdisjoint({path.name for path in artifact_paths(out_dir)})


def test_source_ai_ingested_files_are_not_modified(tmp_path: Path) -> None:
    result, _, ai_dir, _, _ = invoke(tmp_path)
    before = {path.name: path.read_text(encoding="utf-8") for path in ai_dir.glob("*.json")}
    assert result.returncode == 0, result.stderr + result.stdout
    result2 = run_plan("--project", "TestProject", "--ai-ingested-dir", str(ai_dir), "--out-dir", str(tmp_path / "out2"))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    after = {path.name: path.read_text(encoding="utf-8") for path in ai_dir.glob("*.json")}
    assert before == after


def test_core_artifacts_are_not_modified(tmp_path: Path) -> None:
    result, _, _, core_current, core_rating = invoke(tmp_path, core_currents=[current_record()], core_ratings=[rating_record()])
    assert result.returncode == 0, result.stderr + result.stdout
    assert core_current is not None and core_rating is not None
    before = (core_current.read_text(encoding="utf-8"), core_rating.read_text(encoding="utf-8"))
    result2 = run_plan("--project", "TestProject", "--ai-ingested-dir", str(tmp_path / "exports" / "TestProject" / "ai_ingested"), "--out-dir", str(tmp_path / "out2"), "--core-current-models-normalized", str(core_current), "--core-rating-models-normalized", str(core_rating))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    assert before == (core_current.read_text(encoding="utf-8"), core_rating.read_text(encoding="utf-8"))


def test_no_ingestion_or_calculation_scripts_are_invoked() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "topology_current_allocate" not in text
    assert "topology_copper_calculate" not in text
    assert "topology_margin_calculate" not in text


def test_no_live_ai_or_network_client_imports_are_used() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "gemini", "requests", "httpx", "urllib", "socket"):
        assert token not in text


def test_no_findings_or_pass_fail_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"finding_id", "issue_id", "violation", "severity", "pass_fail", "compliance_pass", "compliance_fail"}
    for path in artifact_paths(out_dir):
        assert forbidden.isdisjoint(all_keys(read_json(path)))


def test_forbidden_mutation_fields_are_not_emitted(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing"}
    for path in artifact_paths(out_dir):
        assert forbidden.isdisjoint(all_keys(read_json(path)))


def test_approval_fields_are_pending_and_unapproved_only(tmp_path: Path) -> None:
    result, out_dir, _, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for candidate in plan(out_dir)["promotion_candidates"]:
        assert candidate["promotion_status"] == "pending_human_approval"
        assert candidate["approval"]["approved"] is False
        assert candidate["approval"]["approved_by"] is None
        assert candidate["approval"]["approved_at_utc"] is None


def test_promotion_candidate_ids_are_deterministic(tmp_path: Path) -> None:
    result, out_dir, ai_dir, core_current, core_rating = invoke(tmp_path, core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    first = [row["promotion_candidate_id"] for row in plan(out_dir)["promotion_candidates"]]
    args = ["--project", "TestProject", "--ai-ingested-dir", str(ai_dir), "--out-dir", str(tmp_path / "out2")]
    if core_current:
        args.extend(["--core-current-models-normalized", str(core_current)])
    if core_rating:
        args.extend(["--core-rating-models-normalized", str(core_rating)])
    result2 = run_plan(*args)
    assert result2.returncode == 0, result2.stderr + result2.stdout
    second = [row["promotion_candidate_id"] for row in plan(tmp_path / "out2")["promotion_candidates"]]
    assert first == second


def test_approval_item_ids_are_deterministic(tmp_path: Path) -> None:
    result, out_dir, ai_dir, _, _ = invoke(tmp_path, core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    first = [row["approval_item_id"] for row in queue(out_dir)["approval_items"]]
    result2 = run_plan("--project", "TestProject", "--ai-ingested-dir", str(ai_dir), "--out-dir", str(tmp_path / "out2"))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    second = [row["approval_item_id"] for row in queue(tmp_path / "out2")["approval_items"]]
    assert first == second


def test_output_order_is_deterministic(tmp_path: Path) -> None:
    currents = [current_record(record_id="z", refdes="UZ"), current_record(record_id="a", refdes="UA")]
    result, out_dir, _, _, _ = invoke(tmp_path, currents=currents, ratings=[], core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    ids = [row["promotion_candidate_id"] for row in plan(out_dir)["promotion_candidates"]]
    assert ids == sorted(ids)


def test_repeated_run_produces_stable_artifacts_except_generated_timestamp(tmp_path: Path) -> None:
    result, out_dir, ai_dir, core_current, core_rating = invoke(tmp_path, core_currents=[], core_ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    first = plan(out_dir)
    assert core_current is not None and core_rating is not None
    result2 = run_plan(
        "--project",
        "TestProject",
        "--ai-ingested-dir",
        str(ai_dir),
        "--out-dir",
        str(out_dir),
        "--core-current-models-normalized",
        str(core_current),
        "--core-rating-models-normalized",
        str(core_rating),
    )
    assert result2.returncode == 0, result2.stderr + result2.stdout
    second = plan(out_dir)
    first["generated_at_utc"] = "<ts>"
    second["generated_at_utc"] = "<ts>"
    assert first == second


def test_docs_state_promotion_plan_does_not_call_ai() -> None:
    assert "does not call ai" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_promotion_plan_does_not_apply_candidates() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "does not" in text and "promote data" in text


def test_docs_state_normalized_outputs_are_not_overwritten() -> None:
    assert "overwrite normalized outputs" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_allocation_and_calculations_are_not_run() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "run current allocation" in text and "run copper/via/margin calculations" in text


def test_docs_state_future_promotion_requires_explicit_approval() -> None:
    assert "explicit approval" in DOC.read_text(encoding="utf-8").lower()
