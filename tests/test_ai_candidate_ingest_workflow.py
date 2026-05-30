from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_candidate_ingest_workflow.py"
SCHEMA = ROOT / "schemas" / "ai_candidate_ingestion_workflow_schema.json"
DOC = ROOT / "docs" / "ai_candidate_ingest_workflow.md"


def run_workflow(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_ref(source: str = "datasheets/U2.pdf", page: int = 92, quote: str = "IDD max 85 mA") -> str:
    return f"{source}:{page}:{quote}"


def current_input_record(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "ai_cur_adapter_ai_cur_u2",
        "source": "ai_validated_datasheet",
        "refdes": "U2",
        "mpn": "MCU-456",
        "rail_name": "V3P3",
        "branch_id": None,
        "field_name": "max_current_a",
        "current_type": "max",
        "value": 0.085,
        "unit": "A",
        "max_current_a": 0.085,
        "condition": "active mode, VDD=3.3V",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "evidence_refs": [evidence_ref()],
        "ai_evidence_refs": [{"source_file": "datasheets/U2.pdf", "source_page": 92, "evidence_quote": "IDD max 85 mA"}],
        "source_candidate_record_id": "ai_cur_u2",
        "source_patch_id": "patch_u2_current",
        "source_packet_id": "12B-001",
        "source_item_id": "ai_item_u2_current",
        "source_accepted_item_id": "accepted_u2_current",
        "missing_data_item_ids": ["mdi_u2_current"],
        "provenance": {
            "source_candidate_record_id": "ai_cur_u2",
            "source_patch_id": "patch_u2_current",
            "source_packet_id": "12B-001",
            "source_item_id": "ai_item_u2_current",
            "source_accepted_item_id": "accepted_u2_current",
            "basis": "ai_validated_datasheet",
        },
    }
    row.update(overrides)
    return row


def rating_input_record(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "ai_rate_adapter_f1_hold",
        "source": "ai_validated_datasheet",
        "target_type": "fuse",
        "refdes": "F1",
        "pin": None,
        "mpn": "FUSE-123",
        "rating_name": "hold_current",
        "value": 1.1,
        "unit": "A",
        "condition": "25 C",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "evidence_refs": [evidence_ref("datasheets/F1.pdf", 3, "Hold current 1.1 A")],
        "ai_evidence_refs": [{"source_file": "datasheets/F1.pdf", "source_page": 3, "evidence_quote": "Hold current 1.1 A"}],
        "source_candidate_record_id": "ai_rate_f1",
        "source_patch_id": "patch_f1_rating",
        "source_packet_id": "12C-001",
        "source_item_id": "ai_item_f1_rating",
        "source_accepted_item_id": "accepted_f1_rating",
        "missing_data_item_ids": ["mdi_f1_rating"],
        "provenance": {
            "source_candidate_record_id": "ai_rate_f1",
            "source_patch_id": "patch_f1_rating",
            "source_packet_id": "12C-001",
            "source_item_id": "ai_item_f1_rating",
            "source_accepted_item_id": "accepted_f1_rating",
            "basis": "ai_validated_datasheet",
        },
    }
    row.update(overrides)
    return row


def write_adapter_dir(
    path: Path,
    *,
    current_records: list[dict[str, Any]] | None = None,
    rating_records: list[dict[str, Any]] | None = None,
    human_records: list[dict[str, Any]] | None = None,
    manifest_text: str | None = None,
) -> Path:
    files = {
        "current_model_ingest_input": "ai-current-model-ingest-input.json",
        "rating_model_ingest_input": "ai-rating-model-ingest-input.json",
        "role_resolution_addenda_adapter": "ai-role-resolution-addenda-adapter.json",
        "pin_role_addenda_adapter": "ai-pin-role-addenda-adapter.json",
        "rail_relationship_hints_adapter": "ai-rail-relationship-hints-adapter.json",
        "passive_support_adapter": "ai-passive-support-adapter.json",
        "human_review_adapter": "ai-human-review-adapter.json",
    }
    manifest = {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_candidate_adapter_manifest_v1",
        "source_artifacts": [],
        "source_candidate_manifest": "candidate_manifest.json",
        "adapter_build_pass": True,
        "adapter_files": files,
        "skipped_candidates": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }
    status = {
        "project": "TestProject",
        "status": "adapter_built",
        "adapter_build_pass": True,
        "safe_to_run_candidate_current_ingest_manually": True,
        "safe_to_run_candidate_rating_ingest_manually": True,
        "safe_to_overwrite_core_artifacts": False,
        "safe_to_rerun_calculations_automatically": False,
        "requires_human_review_count": len(human_records or []),
        "errors": [],
        "warnings": [],
    }
    if manifest_text is None:
        write_json(path / "ai-adapter-manifest.json", manifest)
    else:
        path.mkdir(parents=True, exist_ok=True)
        (path / "ai-adapter-manifest.json").write_text(manifest_text, encoding="utf-8")
    write_json(path / "adapter-status.json", status)
    write_json(path / "ai-current-model-ingest-input.json", {
        "project": "TestProject",
        "schema_version": "ai_current_model_ingest_input_v1",
        "source": "ai_validated_datasheet",
        "source_artifacts": [],
        "branch_currents": [],
        "rail_currents": [],
        "component_currents": current_records if current_records is not None else [current_input_record()],
        "metadata": {"safe_to_ingest_manually": True, "safe_to_overwrite_core_artifacts": False},
        "errors": [],
        "warnings": [],
    })
    write_json(path / "ai-rating-model-ingest-input.json", {
        "project": "TestProject",
        "schema_version": "ai_rating_model_ingest_input_v1",
        "source": "ai_validated_datasheet",
        "source_artifacts": [],
        "ratings": rating_records if rating_records is not None else [rating_input_record()],
        "metadata": {"safe_to_ingest_manually": True, "safe_to_overwrite_core_artifacts": False},
        "errors": [],
        "warnings": [],
    })
    write_json(path / "ai-role-resolution-addenda-adapter.json", {"project": "TestProject", "schema_version": "ai_role_resolution_addenda_adapter_v1", "source_artifacts": [], "role_addenda": [{"addendum_id": "role_1"}], "metadata": {}, "errors": [], "warnings": []})
    write_json(path / "ai-pin-role-addenda-adapter.json", {"project": "TestProject", "schema_version": "ai_pin_role_addenda_adapter_v1", "source_artifacts": [], "pin_role_addenda": [{"addendum_id": "pin_1"}], "metadata": {}, "errors": [], "warnings": []})
    write_json(path / "ai-rail-relationship-hints-adapter.json", {"project": "TestProject", "schema_version": "ai_rail_relationship_hints_adapter_v1", "source_artifacts": [], "rail_relationship_hints": [{"hint_id": "rail_1"}], "metadata": {}, "errors": [], "warnings": []})
    write_json(path / "ai-passive-support-adapter.json", {"project": "TestProject", "schema_version": "ai_passive_support_adapter_v1", "source_artifacts": [], "passive_support_records": [{"record_id": "passive_1"}], "metadata": {}, "errors": [], "warnings": []})
    write_json(path / "ai-human-review-adapter.json", {"project": "TestProject", "schema_version": "ai_human_review_adapter_v1", "source_artifacts": [], "human_review_records": human_records or [{"review_id": "review_1", "reason_code": "medium_confidence", "detail": "review", "usable_for_ingestion": False}], "metadata": {}, "errors": [], "warnings": []})
    return path


def invoke(
    tmp_path: Path,
    *,
    current_records: list[dict[str, Any]] | None = None,
    rating_records: list[dict[str, Any]] | None = None,
    human_records: list[dict[str, Any]] | None = None,
    skip_current: bool = False,
    skip_rating: bool = False,
    current_script: Path | None = None,
    rating_script: Path | None = None,
    manifest_text: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    adapter_dir = write_adapter_dir(
        tmp_path / "exports" / "TestProject" / "ai_adapters",
        current_records=current_records,
        rating_records=rating_records,
        human_records=human_records,
        manifest_text=manifest_text,
    )
    out_dir = tmp_path / "exports" / "TestProject" / "ai_ingested"
    args = ["--project", "TestProject", "--adapter-dir", str(adapter_dir), "--out-dir", str(out_dir)]
    if skip_current:
        args.append("--skip-current")
    if skip_rating:
        args.append("--skip-rating")
    if current_script:
        args.extend(["--current-model-ingest-script", str(current_script)])
    if rating_script:
        args.extend(["--rating-model-ingest-script", str(rating_script)])
    return run_workflow(*args), out_dir, adapter_dir


def artifact_paths(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.json"))


def manifest(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-ingestion-manifest.json")


def status(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-ingestion-status.json")


def review(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-ingestion-review.json")


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


def write_failing_script(path: Path, stdout: str = "", stderr: str = "") -> Path:
    path.write_text(
        "import sys\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    return path


def test_missing_adapter_dir_exits_2(tmp_path: Path) -> None:
    result = run_workflow("--project", "TestProject", "--adapter-dir", str(tmp_path / "missing"), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_missing_adapter_manifest_exits_2(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    result = run_workflow("--project", "TestProject", "--adapter-dir", str(adapter_dir), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_malformed_adapter_manifest_exits_2(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path, manifest_text="{bad")
    assert result.returncode == 2


def test_output_directory_shape_created(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "ai-candidate-ingestion-manifest.json",
        "ai-candidate-ingestion-status.json",
        "ai-current-models-normalized.json",
        "ai-rating-current-models-normalized.json",
        "ai-rating-models-normalized.json",
        "ai-addenda-index.json",
        "ai-human-review-index.json",
        "ai-candidate-ingestion-review.json",
    }
    assert expected == {path.name for path in artifact_paths(out_dir)}


def test_manifest_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_adapter_manifest", "source_adapter_status", "workflow_pass", "outputs", "steps", "summary", "errors", "warnings"}
    assert expected.issubset(manifest(out_dir))


def test_status_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "status", "workflow_pass", "safe_to_use_as_candidate_inputs", "safe_to_overwrite_core_artifacts", "safe_to_rerun_current_allocation_automatically", "safe_to_rerun_calculations_automatically", "current_ingest_pass", "rating_current_ingest_pass", "rating_ingest_pass", "requires_human_review_count", "errors", "warnings"}
    assert expected.issubset(status(out_dir))


def test_cli_writes_valid_json_artifacts(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        assert isinstance(read_json(path), dict)


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        for value in all_values(read_json(path)):
            assert not (isinstance(value, float) and not math.isfinite(value))


def test_schema_validates_manifest_status_review_and_indexes(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(SCHEMA)
    for name in ("ai-candidate-ingestion-manifest.json", "ai-candidate-ingestion-status.json", "ai-addenda-index.json", "ai-human-review-index.json", "ai-candidate-ingestion-review.json"):
        jsonschema.validate(instance=read_json(out_dir / name), schema=schema)


def test_summary_counts_match_outputs(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    summary = manifest(out_dir)["summary"]
    assert summary["current_normalized_record_count"] == len(read_json(out_dir / "ai-current-models-normalized.json")["normalized_currents"])
    assert summary["rating_current_normalized_record_count"] == len(read_json(out_dir / "ai-rating-current-models-normalized.json")["normalized_currents"])
    assert summary["rating_normalized_record_count"] == len(read_json(out_dir / "ai-rating-models-normalized.json")["normalized_ratings"])


def test_workflow_runs_current_model_ingest_into_isolated_output(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    data = read_json(out_dir / "ai-current-models-normalized.json")
    assert data["normalized_currents"][0]["basis"] == "ai_validated_datasheet"


def test_workflow_runs_rating_path_into_isolated_outputs(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rating-current-models-normalized.json")["normalized_currents"]
    assert read_json(out_dir / "ai-rating-models-normalized.json")["normalized_ratings"]


def test_workflow_records_step_commands_returncodes_and_output_paths(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for step in manifest(out_dir)["steps"]:
        assert isinstance(step["command"], list)
        assert "returncode" in step
        assert step["output_path"] is not None


def test_workflow_truncates_stdout_and_stderr_previews(tmp_path: Path) -> None:
    failing = write_failing_script(tmp_path / "fail.py", stdout="x" * 5000, stderr="y" * 5000)
    result, out_dir, _ = invoke(tmp_path, current_script=failing, skip_rating=True)
    assert result.returncode == 1
    step = manifest(out_dir)["steps"][0]
    assert len(step["stdout_preview"]) <= 4014
    assert len(step["stderr_preview"]) <= 4014
    assert "[truncated]" in step["stdout_preview"]


def test_failed_current_step_stops_dependent_current_outputs(tmp_path: Path) -> None:
    failing = write_failing_script(tmp_path / "fail.py")
    result, out_dir, _ = invoke(tmp_path, current_script=failing, skip_rating=True)
    assert result.returncode == 1
    assert manifest(out_dir)["steps"][0]["status"] == "failed"
    assert not (out_dir / "ai-current-models-normalized.json").exists()


def test_failed_rating_current_step_stops_rating_model_ingest(tmp_path: Path) -> None:
    failing = write_failing_script(tmp_path / "fail.py")
    result, out_dir, _ = invoke(tmp_path, current_script=failing, skip_current=True)
    assert result.returncode == 1
    steps = {step["step_id"]: step for step in manifest(out_dir)["steps"]}
    assert steps["rating_current_model_ingest"]["status"] == "failed"
    assert steps["rating_model_ingest"]["status"] == "skipped"


def test_skip_current_flag_skips_current_step(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, skip_current=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["steps"][0]["status"] == "skipped"


def test_skip_rating_flag_skips_rating_steps(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, skip_rating=True)
    assert result.returncode == 0, result.stderr + result.stdout
    steps = {step["step_id"]: step for step in manifest(out_dir)["steps"]}
    assert steps["rating_current_model_ingest"]["status"] == "skipped"
    assert steps["rating_model_ingest"]["status"] == "skipped"


def test_outputs_are_inside_out_dir(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        path.resolve().relative_to(out_dir.resolve())


def test_forbidden_core_output_filenames_are_not_written(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"TestProject-current-models-normalized.json", "TestProject-rating-models-normalized.json", "TestProject-topology-current-allocation.json", "TestProject-topology-copper-calculations.json", "TestProject-topology-margin-calculations.json"}
    assert forbidden.isdisjoint({path.name for path in artifact_paths(out_dir)})


def test_workflow_does_not_write_core_normalized_or_calculation_artifacts(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert not list(out_dir.parent.glob("TestProject-*.json"))


def test_subprocess_uses_argument_arrays_not_shell_true() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "shell=True" not in text
    assert "subprocess.run(command" in text


def test_script_override_must_exist(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path, current_script=tmp_path / "missing.py")
    assert result.returncode == 2


def test_no_live_ai_or_network_client_imports_are_used() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "gemini", "requests", "httpx", "urllib", "socket"):
        assert token not in text


def test_current_candidate_normalized_output_exists(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (out_dir / "ai-current-models-normalized.json").exists()


def test_rating_candidate_normalized_output_exists(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (out_dir / "ai-rating-current-models-normalized.json").exists()


def test_rating_model_candidate_output_exists(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (out_dir / "ai-rating-models-normalized.json").exists()


def test_empty_candidate_inputs_are_handled_as_empty_or_skipped_with_warning(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, current_records=[], rating_records=[], human_records=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-current-models-normalized.json")["normalized_currents"] == []
    assert read_json(out_dir / "ai-rating-models-normalized.json")["normalized_ratings"] == []


def test_candidate_outputs_are_marked_candidate_not_core(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert status(out_dir)["safe_to_overwrite_core_artifacts"] is False
    assert "ai-" in manifest(out_dir)["outputs"]["current_models_normalized"]


def test_existing_ingestion_scripts_are_not_modified() -> None:
    assert "ai_candidate_ingest_workflow" not in (ROOT / "scripts" / "current_model_ingest.py").read_text(encoding="utf-8")
    assert "ai_candidate_ingest_workflow" not in (ROOT / "scripts" / "rating_model_ingest.py").read_text(encoding="utf-8")


def test_addenda_index_references_role_pin_rail_passive_adapters(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    index = read_json(out_dir / "ai-addenda-index.json")
    assert index["role_resolution_addenda_adapter"].endswith("ai-role-resolution-addenda-adapter.json")
    assert index["pin_role_addenda_adapter"].endswith("ai-pin-role-addenda-adapter.json")
    assert index["rail_relationship_hints_adapter"].endswith("ai-rail-relationship-hints-adapter.json")
    assert index["passive_support_adapter"].endswith("ai-passive-support-adapter.json")


def test_addenda_index_marks_safe_to_merge_automatically_false(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-addenda-index.json")["safe_to_merge_automatically"] is False


def test_human_review_index_collects_human_review_adapter_records(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    index = read_json(out_dir / "ai-human-review-index.json")
    assert index["summary"]["human_review_record_count"] == 1


def test_human_review_index_collects_workflow_failures(tmp_path: Path) -> None:
    failing = write_failing_script(tmp_path / "fail.py")
    result, out_dir, _ = invoke(tmp_path, current_script=failing, skip_rating=True)
    assert result.returncode == 1
    index = read_json(out_dir / "ai-human-review-index.json")
    assert index["summary"]["workflow_review_record_count"] >= 1


def test_review_artifact_lists_not_performed_steps(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "current allocation rerun" in review(out_dir)["not_performed"]
    assert "role/pin/rail addenda merge" in review(out_dir)["not_performed"]


def test_review_artifact_records_known_provenance_gaps_when_ai_fields_not_preserved(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    gaps = review(out_dir)["known_provenance_gaps"]
    assert any("source_candidate_record_id" in gap for gap in gaps)


def test_source_artifacts_reference_adapter_manifest_and_inputs(tmp_path: Path) -> None:
    result, out_dir, adapter_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    paths = [artifact["path"] for artifact in manifest(out_dir)["source_artifacts"]]
    assert str(adapter_dir / "ai-adapter-manifest.json") in paths
    assert str(adapter_dir / "adapter-status.json") in paths


def test_status_safety_booleans_prevent_auto_core_overwrite_and_auto_calculation_rerun(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    data = status(out_dir)
    assert data["safe_to_overwrite_core_artifacts"] is False
    assert data["safe_to_rerun_current_allocation_automatically"] is False
    assert data["safe_to_rerun_calculations_automatically"] is False


def test_no_findings_or_pass_fail_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"finding_id", "issue_id", "violation", "severity", "pass_fail", "compliance_pass", "compliance_fail"}
    for path in artifact_paths(out_dir):
        assert forbidden.isdisjoint(all_keys(read_json(path)))


def test_forbidden_mutation_fields_are_not_emitted(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {"apply_to_artifact", "mutate_artifact", "overwrite", "delete_existing", "replace_existing"}
    for path in artifact_paths(out_dir):
        assert forbidden.isdisjoint(all_keys(read_json(path)))


def test_no_core_artifact_overwrite_directives_are_emitted(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    text = "\n".join(path.read_text(encoding="utf-8") for path in artifact_paths(out_dir))
    assert "safe_to_overwrite_core_artifacts\": false" in text


def test_workflow_output_order_is_deterministic(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert [step["step_id"] for step in manifest(out_dir)["steps"]] == ["current_model_ingest", "rating_current_model_ingest", "rating_model_ingest"]


def test_repeated_run_produces_stable_manifest_except_generated_timestamp(tmp_path: Path) -> None:
    result, out_dir, adapter_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    first = manifest(out_dir)
    result2 = run_workflow("--project", "TestProject", "--adapter-dir", str(adapter_dir), "--out-dir", str(out_dir))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    second = manifest(out_dir)
    first["generated_at_utc"] = "<ts>"
    second["generated_at_utc"] = "<ts>"
    assert first == second


def test_docs_state_workflow_does_not_call_ai() -> None:
    assert "does not call ai" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_candidate_outputs_are_not_core_outputs() -> None:
    assert "candidate outputs, not core outputs" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_allocation_and_calculations_are_not_run() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "run allocation" in text and "run copper/via/margin calculations" in text


def test_docs_state_role_pin_rail_addenda_are_not_merged() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "role, pin, rail" in text and "not merged" in text


def test_docs_state_future_promotion_requires_explicit_approval() -> None:
    assert "explicit approval" in DOC.read_text(encoding="utf-8").lower()
