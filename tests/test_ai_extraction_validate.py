from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_extraction_validate.py"
DOC = ROOT / "docs" / "ai_extraction_validate.md"


def run_validate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def packet_dir_fixture(tmp_path: Path, packet_id: str = "12B-001", stage_id: str = "12B", packet_type: str = "datasheet_current_extraction") -> Path:
    packet_dir = tmp_path / "exports" / "TestProject" / "ai_packets" / "phase_12"
    packet = {
        "packet_id": packet_id,
        "stage_id": stage_id,
        "packet_type": packet_type,
        "target_type": "component_current_model",
        "target_refdes": "U2",
        "target_mpn": "MCU-456",
        "missing_data_item_ids": ["mdi_u2_current"],
        "status_path": f"packets/{packet_id}/status.json",
    }
    write_json(packet_dir / "packet_queue.json", {"project": "TestProject", "packets": [packet], "source_artifacts": []})
    write_json(
        packet_dir / "packets" / packet_id / "context.json",
        {"packet_id": packet_id, "missing_data_items": [{"manifest_id": "mdi_u2_current"}]},
    )
    write_json(
        packet_dir / "packets" / packet_id / "status.json",
        {
            "packet_id": packet_id,
            "status": "prompt_ready",
            "attempt_count": 0,
            "max_attempts": 2,
            "raw_response_path": None,
            "validated_result_path": None,
            "patch_path": None,
            "errors": [],
            "warnings": [],
        },
    )
    return packet_dir


def response(item: dict[str, Any] | None = None, *, packet_id: str = "12B-001", unknown_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "packet_id": packet_id,
        "schema_version": "ai_extraction_result_v1",
        "status": "completed",
        "extracted_items": [item or current_item()],
        "unknown_items": unknown_items or [],
        "notes": [],
        "warnings": [],
    }


def current_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "item_id": "ai_item_u2_current",
        "missing_data_item_ids": ["mdi_u2_current"],
        "target_type": "component_current_model",
        "target_refdes": "U2",
        "target_mpn": "MCU-456",
        "field_name": "max_current_a",
        "value": 85,
        "unit": "mA",
        "condition": "active mode, VDD=3.3V",
        "basis": "datasheet",
        "source_file": "datasheets/U2.pdf",
        "source_page": 92,
        "evidence_quote": "IDD max 85 mA",
        "confidence": 0.86,
        "human_review_needed": False,
    }
    item.update(overrides)
    return item


def invoke(tmp_path: Path, raw_response: dict[str, Any] | str | None = None, *, strict: bool = False, update: bool = False) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    packet_dir = packet_dir_fixture(tmp_path)
    if raw_response is not None:
        raw_path = packet_dir / "packets" / "12B-001" / "raw_response.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(raw_response, str):
            raw_path.write_text(raw_response, encoding="utf-8")
        else:
            raw_path.write_text(json.dumps(raw_response, indent=2, allow_nan=True), encoding="utf-8")
    out = tmp_path / "exports" / "TestProject-ai-extraction-validation.json"
    args = ["--project", "TestProject", "--packet-dir", str(packet_dir), "--out", str(out)]
    if strict:
        args.append("--strict")
    if update:
        args.append("--update-packet-status")
    return run_validate(*args), out, packet_dir


def artifact_for_item(tmp_path: Path, item: dict[str, Any]) -> dict[str, Any]:
    result, out, _ = invoke(tmp_path, response(item))
    assert result.returncode == 0, result.stderr + result.stdout
    return read_json(out)


def all_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(all_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(all_values(child))
    return values


def test_missing_packet_dir_exits_2(tmp_path: Path) -> None:
    result = run_validate("--project", "TestProject", "--packet-dir", str(tmp_path / "missing"), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_missing_packet_queue_exits_2(tmp_path: Path) -> None:
    packet_dir = tmp_path / "packet_dir"
    packet_dir.mkdir()
    result = run_validate("--project", "TestProject", "--packet-dir", str(packet_dir), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_malformed_packet_queue_exits_2(tmp_path: Path) -> None:
    packet_dir = tmp_path / "packet_dir"
    packet_dir.mkdir()
    (packet_dir / "packet_queue.json").write_text("{bad", encoding="utf-8")
    result = run_validate("--project", "TestProject", "--packet-dir", str(packet_dir), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response())
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "packet_dir", "validation_pass", "packet_results", "accepted_items", "rejected_items", "human_review_items", "pending_packets", "summary", "errors", "warnings"}
    assert expected.issubset(read_json(out))


def test_cli_writes_valid_json_artifact(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response())
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["project"] == "TestProject"


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response())
    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        assert not (isinstance(value, float) and not math.isfinite(value))


def test_summary_counts_match_arrays(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response())
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    assert summary["packet_count"] == len(artifact["packet_results"])
    assert summary["accepted_item_count"] == len(artifact["accepted_items"])
    assert summary["rejected_item_count"] == len(artifact["rejected_items"])
    assert summary["human_review_item_count"] == len(artifact["human_review_items"])


def test_missing_raw_response_is_pending_not_failure_by_default(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["validation_pass"] is True
    assert artifact["packet_results"][0]["status"] == "pending"
    assert artifact["pending_packets"][0]["reason_code"] == "raw_response_missing"


def test_malformed_raw_response_is_rejected(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, "{bad")
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["packet_results"][0]["status"] == "validation_failed"
    assert artifact["rejected_items"][0]["reason_code"] == "malformed_json"


def test_packet_id_mismatch_rejects_packet(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response(packet_id="12B-999"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert any(row["reason_code"] == "packet_id_mismatch" for row in read_json(out)["rejected_items"])


def test_unknown_missing_data_item_rejects_item(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(missing_data_item_ids=["mdi_other"]))
    assert artifact["rejected_items"][0]["reason_code"] == "unknown_missing_data_item"


def test_valid_completed_response_passes_schema(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, response())
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["validation_pass"] is True
    assert artifact["packet_results"][0]["status"] == "accepted"


def test_current_model_item_with_unit_condition_and_evidence_is_accepted(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item())
    assert len(artifact["accepted_items"]) == 1
    assert artifact["accepted_items"][0]["normalized_unit"] == "A"


def test_rating_item_with_unit_and_evidence_is_accepted(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(target_type="connector_pin_rating", field_name="pin_current_max", value=2.0, unit="A", condition=None))
    assert len(artifact["accepted_items"]) == 1


def test_role_pin_text_item_with_evidence_is_accepted_or_human_review(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(target_type="pin_role", field_name="pin_role", value="input", unit="text", condition=None))
    assert artifact["accepted_items"] or artifact["human_review_items"]


def test_current_units_normalize_to_amp(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(value=85000, unit="uA"))
    assert artifact["accepted_items"][0]["normalized_value"] == 0.085


def test_voltage_units_normalize_to_volt(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(target_type="capacitor_support_data", field_name="voltage_rating", value=3300, unit="mV", condition=None))
    assert artifact["accepted_items"][0]["normalized_value"] == 3.3


def test_resistance_units_normalize_to_ohm(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(target_type="capacitor_support_data", field_name="esr", value=50, unit="mOhm", condition=None))
    assert artifact["accepted_items"][0]["normalized_value"] == 0.05


def test_capacitance_units_normalize_to_farad(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(target_type="capacitor_support_data", field_name="capacitance", value=10, unit="uF", condition=None))
    assert artifact["accepted_items"][0]["normalized_value"] == 1e-05


def test_numeric_item_without_unit_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(unit=None))
    assert artifact["rejected_items"][0]["reason_code"] == "missing_unit"


def test_numeric_item_without_evidence_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(evidence_quote=None))
    assert artifact["rejected_items"][0]["reason_code"] == "missing_evidence"


def test_datasheet_item_without_source_file_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(source_file=None))
    assert artifact["rejected_items"][0]["reason_code"] == "missing_source_file"


def test_negative_current_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(value=-1, unit="A"))
    assert artifact["rejected_items"][0]["reason_code"] == "negative_current_or_rating"


def test_nan_or_infinity_value_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(value=float("nan"), unit="A"))
    assert artifact["rejected_items"][0]["reason_code"] == "invalid_numeric_value"


def test_unsupported_unit_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(unit="W"))
    assert artifact["rejected_items"][0]["reason_code"] == "unsupported_unit"


def test_unsupported_field_name_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(field_name="made_up_field"))
    assert artifact["rejected_items"][0]["reason_code"] == "unsupported_field_name"


def test_forbidden_finding_field_rejects_item_or_packet(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(finding_id="F1"))
    assert any(row["reason_code"] == "forbidden_output_field" for row in artifact["rejected_items"])


def test_final_calculation_output_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(final_calculation={"voltage_drop": 1.2}))
    assert any(row["reason_code"] == "final_calculation_not_allowed" for row in artifact["rejected_items"])


def test_topology_mutation_output_is_rejected(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(topology_patch={"replace": []}))
    assert any(row["reason_code"] == "topology_mutation_not_allowed" for row in artifact["rejected_items"])


def test_medium_confidence_routes_to_human_review(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(confidence=0.65))
    assert artifact["human_review_items"][0]["reason_code"] == "medium_confidence"


def test_missing_current_condition_routes_to_human_review(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(condition=None))
    assert artifact["human_review_items"][0]["reason_code"] == "ambiguous_condition"


def test_ambiguous_multiple_candidate_values_routes_to_human_review(tmp_path: Path) -> None:
    artifact = artifact_for_item(tmp_path, current_item(multiple_candidate_values=[1, 2]))
    assert artifact["human_review_items"][0]["reason_code"] == "multiple_candidate_values"


def test_unknown_items_are_preserved(tmp_path: Path) -> None:
    unknown = [{"missing_data_item_id": "mdi_u2_current", "target_type": "component_current_model", "target_refdes": "U2", "field_name": "max_current_a", "reason_code": "not_found_in_provided_context", "detail": "not found"}]
    result, out, _ = invoke(tmp_path, response(current_item(), unknown_items=unknown))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["unknown_items"][0]["missing_data_item_id"] == "mdi_u2_current"


def test_update_packet_status_flag_updates_status_json(tmp_path: Path) -> None:
    result, out, packet_dir = invoke(tmp_path, response(), update=True)
    assert result.returncode == 0, result.stderr + result.stdout
    status = read_json(packet_dir / "packets" / "12B-001" / "status.json")
    assert status["status"] == "accepted"
    assert status["validated_result_path"] == str(out)


def test_default_does_not_mutate_packet_status_json(tmp_path: Path) -> None:
    result, _, packet_dir = invoke(tmp_path, response(), update=False)
    assert result.returncode == 0, result.stderr + result.stdout
    status = read_json(packet_dir / "packets" / "12B-001" / "status.json")
    assert status["status"] == "prompt_ready"
    assert status["validated_result_path"] is None


def test_docs_state_validator_does_not_call_ai() -> None:
    assert "does not call AI" in DOC.read_text(encoding="utf-8")


def test_docs_state_accepted_results_are_not_directly_applied() -> None:
    assert "Accepted validation output is still not directly applied" in DOC.read_text(encoding="utf-8")


def test_docs_state_evidence_is_required_for_datasheet_values() -> None:
    assert "Datasheet-sourced values without `source_file` are rejected" in DOC.read_text(encoding="utf-8")
