from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_patch_build.py"
SCHEMA = ROOT / "schemas" / "ai_patch_schema.json"
DOC = ROOT / "docs" / "ai_patch_build.md"


def run_build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def accepted_item(**overrides: Any) -> dict[str, Any]:
    row = {
        "accepted_item_id": "accepted_12B_001_ai_item_u2_current",
        "packet_id": "12B-001",
        "source_item_id": "ai_item_u2_current",
        "target_type": "component_current_model",
        "target_refdes": "U2",
        "target_mpn": "MCU-456",
        "field_name": "max_current_a",
        "value": 0.085,
        "unit": "A",
        "normalized_value": 0.085,
        "normalized_unit": "A",
        "condition": "active mode, VDD=3.3V",
        "basis": "datasheet",
        "source_file": "datasheets/U2.pdf",
        "source_page": 92,
        "evidence_quote": "IDD max 85 mA",
        "confidence": 0.86,
        "missing_data_item_ids": ["mdi_u2_current"],
        "usable_for_patch": True,
        "human_review_needed": False,
    }
    row.update(overrides)
    return row


def validation_fixture(
    accepted: list[dict[str, Any]] | None = None,
    *,
    rejected: list[dict[str, Any]] | None = None,
    human: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_extraction_validation_v1",
        "source_artifacts": [],
        "source_validation_artifact": "validation.json",
        "packet_dir": "exports/TestProject/ai_packets/phase_12",
        "validation_pass": True,
        "packet_results": [],
        "accepted_items": accepted if accepted is not None else [accepted_item()],
        "rejected_items": rejected or [],
        "human_review_items": human or [],
        "pending_packets": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def human_review_row(**overrides: Any) -> dict[str, Any]:
    candidate = accepted_item(
        accepted_item_id=None,
        packet_id="12B-001",
        source_item_id="ai_item_review",
        confidence=0.65,
        human_review_needed=True,
        usable_for_patch=False,
    )
    candidate.update(overrides.pop("candidate_overrides", {}))
    row = {
        "human_review_item_id": "human_12B_001_ai_item_review",
        "packet_id": "12B-001",
        "source_item_id": "ai_item_review",
        "reason_code": "medium_confidence",
        "detail": "needs review",
        "candidate_item": candidate,
    }
    row.update(overrides)
    return row


def invoke(
    tmp_path: Path,
    validation: dict[str, Any] | str | None = None,
    *,
    include_human: bool = False,
    out_dir: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    validation_path = tmp_path / "exports" / "TestProject-ai-extraction-validation.json"
    if validation is not None:
        validation_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(validation, str):
            validation_path.write_text(validation, encoding="utf-8")
        else:
            write_json(validation_path, validation)
    else:
        write_json(validation_path, validation_fixture())
    out = tmp_path / "exports" / "TestProject-ai-patch-bundle.json"
    args = ["--project", "TestProject", "--validation", str(validation_path), "--out", str(out)]
    if include_human:
        args.append("--include-human-review")
    if out_dir:
        args.extend(["--out-dir", str(tmp_path / "exports" / "TestProject" / "ai_patches")])
    return run_build(*args), out, validation_path


def artifact_for_items(tmp_path: Path, items: list[dict[str, Any]]) -> dict[str, Any]:
    result, out, _ = invoke(tmp_path, validation_fixture(items))
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


def only_patch(artifact: dict[str, Any]) -> dict[str, Any]:
    assert len(artifact["patches"]) == 1
    return artifact["patches"][0]


def test_missing_validation_artifact_exits_2(tmp_path: Path) -> None:
    result = run_build("--project", "TestProject", "--validation", str(tmp_path / "missing.json"), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_malformed_validation_artifact_exits_2(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path, "{bad")
    assert result.returncode == 2


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_validation_artifact", "patch_bundle_pass", "patches", "conflicts", "skipped_items", "human_review_items", "summary", "errors", "warnings"}
    assert expected.issubset(read_json(out))


def test_cli_writes_valid_json_artifact(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["project"] == "TestProject"


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        assert not (isinstance(value, float) and not math.isfinite(value))


def test_summary_counts_match_arrays(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    assert summary["patch_count"] == len(artifact["patches"])
    assert summary["skipped_item_count"] == len(artifact["skipped_items"])
    assert summary["conflict_count"] == len(artifact["conflicts"])


def test_schema_validates_output_artifact(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    jsonschema.validate(instance=read_json(out), schema=read_json(SCHEMA))


def test_component_current_item_maps_to_current_model_patch(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(target_type="component_current_model")])
    assert only_patch(artifact)["patch_class"] == "current_model_patch"


def test_branch_current_item_maps_to_current_model_patch(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(target_type="branch_current_model", target_refdes="BR1")])
    assert only_patch(artifact)["patch_class"] == "current_model_patch"


def test_rail_current_item_maps_to_current_model_patch(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(target_type="rail_current_model", target_refdes="V3P3")])
    assert only_patch(artifact)["patch_class"] == "current_model_patch"


def test_fuse_rating_item_maps_to_rating_model_patch(tmp_path: Path) -> None:
    item = accepted_item(target_type="fuse_rating", target_refdes="F1", field_name="hold_current", value=0.5, normalized_value=0.5)
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "rating_model_patch"


def test_connector_pin_rating_item_maps_to_rating_model_patch(tmp_path: Path) -> None:
    item = accepted_item(target_type="connector_pin_rating", target_refdes="J1", field_name="pin_current_max", value=2.0, normalized_value=2.0)
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "rating_model_patch"


def test_regulator_rating_item_maps_to_rating_model_patch(tmp_path: Path) -> None:
    item = accepted_item(target_type="regulator_rating", target_refdes="U1", field_name="output_current_max", value=1.5, normalized_value=1.5)
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "rating_model_patch"


def test_capacitor_esr_maps_to_passive_support_data_patch(tmp_path: Path) -> None:
    item = accepted_item(target_type="capacitor_support_data", target_refdes="C1", field_name="esr", value=0.05, unit="ohm", normalized_value=0.05, normalized_unit="ohm")
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "passive_support_data_patch"


def test_component_role_maps_to_role_resolution_addendum(tmp_path: Path) -> None:
    item = accepted_item(target_type="component_role", target_refdes="U1", field_name="component_role", value="regulator", unit="text", normalized_value="regulator", normalized_unit="text")
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "role_resolution_addendum"


def test_pin_role_maps_to_pin_role_addendum(tmp_path: Path) -> None:
    item = accepted_item(target_type="pin_role", target_refdes="U1", field_name="pin_role", value="input", unit="text", normalized_value="input", normalized_unit="text")
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "pin_role_addendum"


def test_rail_relationship_maps_to_rail_relationship_hint(tmp_path: Path) -> None:
    item = accepted_item(target_type="rail_relationship_hint", target_refdes="U1", field_name="rail_relationship", value="input_to_output", unit="text", normalized_value="input_to_output", normalized_unit="text")
    artifact = artifact_for_items(tmp_path, [item])
    assert only_patch(artifact)["patch_class"] == "rail_relationship_hint"


def test_patch_preserves_packet_id_source_item_id_and_accepted_item_id(tmp_path: Path) -> None:
    patch = only_patch(artifact_for_items(tmp_path, [accepted_item()]))
    assert patch["source_packet_id"] == "12B-001"
    assert patch["source_item_id"] == "ai_item_u2_current"
    assert patch["source_accepted_item_id"] == "accepted_12B_001_ai_item_u2_current"


def test_patch_preserves_missing_data_item_ids(tmp_path: Path) -> None:
    patch = only_patch(artifact_for_items(tmp_path, [accepted_item(missing_data_item_ids=["mdi_a", "mdi_b"])]))
    assert patch["missing_data_item_ids"] == ["mdi_a", "mdi_b"]


def test_patch_preserves_source_file_page_and_evidence_quote(tmp_path: Path) -> None:
    patch = only_patch(artifact_for_items(tmp_path, [accepted_item(source_file="datasheets/U2.pdf", source_page=92, evidence_quote="row")]))
    assert patch["source_file"] == "datasheets/U2.pdf"
    assert patch["source_page"] == 92
    assert patch["evidence_quote"] == "row"


def test_patch_preserves_confidence_condition_and_basis(tmp_path: Path) -> None:
    patch = only_patch(artifact_for_items(tmp_path, [accepted_item(confidence=0.91, condition="mode", basis="datasheet")]))
    assert patch["confidence"] == 0.91
    assert patch["condition"] == "mode"
    assert patch["basis"] == "ai_validated_datasheet"


def test_rejected_items_are_not_used(tmp_path: Path) -> None:
    validation = validation_fixture([], rejected=[{"rejected_item_id": "rejected_1"}])
    result, out, _ = invoke(tmp_path, validation)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["patches"] == []


def test_human_review_items_are_not_used_by_default(tmp_path: Path) -> None:
    validation = validation_fixture([], human=[human_review_row()])
    result, out, _ = invoke(tmp_path, validation)
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["patches"] == []
    assert artifact["skipped_items"][0]["reason_code"] == "human_review_not_included"


def test_include_human_review_creates_human_review_patch_candidates(tmp_path: Path) -> None:
    validation = validation_fixture([], human=[human_review_row()])
    result, out, _ = invoke(tmp_path, validation, include_human=True)
    assert result.returncode == 0, result.stderr + result.stdout
    patch = only_patch(read_json(out))
    assert patch["patch_class"] == "human_review_patch_candidate"
    assert patch["requires_human_approval_before_ingestion"] is True


def test_unusable_for_patch_item_is_skipped(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(usable_for_patch=False)])
    assert artifact["skipped_items"][0]["reason_code"] == "not_usable_for_patch"


def test_unsupported_target_type_is_skipped(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(target_type="unsupported_target")])
    assert artifact["skipped_items"][0]["reason_code"] == "unsupported_target_type"


def test_missing_target_identity_is_skipped(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(target_refdes=None, target_mpn=None)])
    assert artifact["skipped_items"][0]["reason_code"] == "missing_target_identity"


def test_missing_evidence_is_skipped(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(evidence_quote=None)])
    assert artifact["skipped_items"][0]["reason_code"] == "missing_evidence"


def test_identical_duplicate_candidates_are_deduplicated(tmp_path: Path) -> None:
    item1 = accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a")
    item2 = accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b")
    artifact = artifact_for_items(tmp_path, [item1, item2])
    patch = only_patch(artifact)
    assert sorted(patch["source_accepted_item_ids"]) == ["accepted_a", "accepted_b"]
    assert "duplicate_identical_candidate" in patch["warnings"]


def test_conflicting_values_create_conflict(tmp_path: Path) -> None:
    item1 = accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a", value=0.085, normalized_value=0.085)
    item2 = accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b", value=0.095, normalized_value=0.095)
    artifact = artifact_for_items(tmp_path, [item1, item2])
    assert artifact["conflicts"][0]["reason_code"] == "conflicting_candidate_values"


def test_conflicting_units_create_conflict(tmp_path: Path) -> None:
    item1 = accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a", unit="A", normalized_unit="A")
    item2 = accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b", unit="mA", normalized_unit="mA", normalized_value=85)
    artifact = artifact_for_items(tmp_path, [item1, item2])
    assert artifact["conflicts"][0]["reason_code"] == "conflicting_units"


def test_conflicting_conditions_create_conflict_or_separate_candidates(tmp_path: Path) -> None:
    item1 = accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a", condition="active")
    item2 = accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b", condition="sleep")
    artifact = artifact_for_items(tmp_path, [item1, item2])
    assert artifact["conflicts"][0]["reason_code"] == "conflicting_conditions"


def test_conflicted_patches_are_not_usable_for_ingestion(tmp_path: Path) -> None:
    item1 = accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a", value=0.085, normalized_value=0.085)
    item2 = accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b", value=0.095, normalized_value=0.095)
    artifact = artifact_for_items(tmp_path, [item1, item2])
    assert all(not patch["usable_for_ingestion"] for patch in artifact["patches"])


def test_no_findings_or_pass_fail_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(finding_id="F1", severity="high", pass_fail="pass")])
    keys = set(all_keys(artifact))
    assert "finding_id" not in keys
    assert "pass_fail" not in keys
    assert "compliance_pass" not in keys


def test_forbidden_mutation_fields_are_not_emitted(tmp_path: Path) -> None:
    artifact = artifact_for_items(tmp_path, [accepted_item(apply_to_artifact="exports/core.json", overwrite=True)])
    raw = json.dumps(artifact)
    assert "apply_to_artifact" not in raw
    assert "overwrite" not in raw
    assert "replace_existing" not in raw


def test_patch_builder_does_not_modify_source_validation_artifact(tmp_path: Path) -> None:
    validation = validation_fixture()
    result, _, validation_path = invoke(tmp_path, validation)
    before = validation_path.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr + result.stdout
    after = validation_path.read_text(encoding="utf-8")
    assert before == after


def test_patch_builder_does_not_write_core_current_or_rating_artifacts(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for name in [
        "TestProject-current-models-normalized.json",
        "TestProject-rating-models-normalized.json",
        "TestProject-topology-current-allocation.json",
        "TestProject-topology-copper-calculations.json",
        "TestProject-topology-margin-calculations.json",
    ]:
        assert not (tmp_path / "exports" / name).exists()


def test_patch_ids_are_deterministic(tmp_path: Path) -> None:
    result1, out1, _ = invoke(tmp_path / "a")
    result2, out2, _ = invoke(tmp_path / "b")
    assert result1.returncode == 0, result1.stderr + result1.stdout
    assert result2.returncode == 0, result2.stderr + result2.stdout
    assert [patch["patch_id"] for patch in read_json(out1)["patches"]] == [patch["patch_id"] for patch in read_json(out2)["patches"]]


def test_patch_order_is_deterministic(tmp_path: Path) -> None:
    items = [
        accepted_item(accepted_item_id="accepted_b", source_item_id="ai_b", target_refdes="U3"),
        accepted_item(accepted_item_id="accepted_a", source_item_id="ai_a", target_refdes="U2"),
    ]
    artifact = artifact_for_items(tmp_path, items)
    ids = [patch["patch_id"] for patch in artifact["patches"]]
    assert ids == sorted(ids)


def test_docs_state_patch_builder_does_not_call_ai() -> None:
    assert "does not call AI" in DOC.read_text(encoding="utf-8")


def test_docs_state_patch_bundle_is_not_directly_applied() -> None:
    assert "not directly applied" in DOC.read_text(encoding="utf-8")


def test_docs_state_conflicts_require_human_review() -> None:
    assert "Conflicting values" in DOC.read_text(encoding="utf-8") or "require human review" in DOC.read_text(encoding="utf-8")
