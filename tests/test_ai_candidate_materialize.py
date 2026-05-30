from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_candidate_materialize.py"
SCHEMA = ROOT / "schemas" / "ai_candidate_inputs_schema.json"
DOC = ROOT / "docs" / "ai_candidate_materialize.md"


def run_materialize(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def patch(**overrides: Any) -> dict[str, Any]:
    row = {
        "patch_id": "patch_current_model_patch_component_current_model_U2_max_current_a_abc123",
        "patch_class": "current_model_patch",
        "operation": "add_candidate",
        "target_type": "component_current_model",
        "target_refdes": "U2",
        "target_mpn": "MCU-456",
        "field_name": "max_current_a",
        "value": 0.085,
        "unit": "A",
        "normalized_value": 0.085,
        "normalized_unit": "A",
        "condition": "active mode, VDD=3.3V",
        "basis": "ai_validated_datasheet",
        "source_packet_id": "12B-001",
        "source_item_id": "ai_item_u2_current",
        "source_accepted_item_id": "accepted_12B_001_ai_item_u2_current",
        "source_item_ids": ["ai_item_u2_current"],
        "source_accepted_item_ids": ["accepted_12B_001_ai_item_u2_current"],
        "missing_data_item_ids": ["mdi_u2_current"],
        "source_file": "datasheets/U2.pdf",
        "source_page": 92,
        "evidence_quote": "IDD max 85 mA",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "requires_human_approval_before_ingestion": False,
        "provenance": {
            "validation_artifact": "validation.json",
            "packet_id": "12B-001",
            "source_item_id": "ai_item_u2_current",
            "source_accepted_item_id": "accepted_12B_001_ai_item_u2_current",
            "basis": "ai_validated_datasheet",
        },
        "warnings": [],
    }
    row.update(overrides)
    return row


def bundle_fixture(
    patches: list[dict[str, Any]] | None = None,
    *,
    conflicts: list[dict[str, Any]] | None = None,
    skipped: list[dict[str, Any]] | None = None,
    human_review: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = patches if patches is not None else [patch()]
    return {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_patch_bundle_v1",
        "source_artifacts": [],
        "source_validation_artifact": "exports/TestProject-ai-extraction-validation.json",
        "patch_bundle_pass": True,
        "patches": rows,
        "conflicts": conflicts or [],
        "skipped_items": skipped or [],
        "human_review_items": human_review or [],
        "summary": {
            "patch_count": len(rows),
            "conflict_count": len(conflicts or []),
        },
        "errors": [],
        "warnings": [],
    }


def conflict_for(*patch_ids: str) -> dict[str, Any]:
    return {
        "conflict_id": "conflict_conflicting_candidate_values_abc123",
        "reason_code": "conflicting_candidate_values",
        "target_type": "component_current_model",
        "target_refdes": "U2",
        "field_name": "max_current_a",
        "candidate_patch_ids": list(patch_ids),
        "detail": "conflict",
        "human_review_needed": True,
    }


def invoke(
    tmp_path: Path,
    bundle: dict[str, Any] | str | None = None,
    *,
    include_human: bool = False,
    allow_conflicted: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bundle_path = tmp_path / "exports" / "TestProject-ai-patch-bundle.json"
    if bundle is None:
        write_json(bundle_path, bundle_fixture())
    elif isinstance(bundle, str):
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(bundle, encoding="utf-8")
    else:
        write_json(bundle_path, bundle)
    out_dir = tmp_path / "exports" / "TestProject" / "ai_candidates"
    args = ["--project", "TestProject", "--patch-bundle", str(bundle_path), "--out-dir", str(out_dir)]
    if include_human:
        args.append("--include-human-review")
    if allow_conflicted:
        args.append("--allow-conflicted")
    return run_materialize(*args), out_dir, bundle_path


def manifest(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-candidate-inputs.json")


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


def artifact_paths(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.json"))


def test_missing_patch_bundle_exits_2(tmp_path: Path) -> None:
    result = run_materialize("--project", "TestProject", "--patch-bundle", str(tmp_path / "missing.json"), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_malformed_patch_bundle_exits_2(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path, "{bad")
    assert result.returncode == 2


def test_output_directory_shape_created(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "ai-candidate-inputs.json",
        "ai-current-model-candidates.json",
        "ai-rating-model-candidates.json",
        "ai-role-resolution-addenda.json",
        "ai-pin-role-addenda.json",
        "ai-rail-relationship-hints.json",
        "ai-passive-support-candidates.json",
        "ai-human-review-candidates.json",
        "materialization-status.json",
    }
    assert expected == {path.name for path in artifact_paths(out_dir)}


def test_manifest_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_patch_bundle", "candidate_materialization_pass", "candidate_files", "skipped_patches", "blocked_by_conflict", "summary", "errors", "warnings"}
    assert expected.issubset(manifest(out_dir))


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


def test_schema_validates_manifest_and_candidate_files(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(SCHEMA)
    for path in artifact_paths(out_dir):
        jsonschema.validate(instance=read_json(path), schema=schema)


def test_summary_counts_match_candidate_files(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    data = manifest(out_dir)
    assert data["summary"]["current_model_candidate_count"] == len(read_json(out_dir / "ai-current-model-candidates.json")["current_records"])
    assert data["summary"]["rating_model_candidate_count"] == len(read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"])
    assert data["summary"]["materialized_candidate_count"] == 1


def test_component_current_patch_materializes_current_model_candidate(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([patch(target_type="component_current_model")]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-current-model-candidates.json")["current_records"][0]
    assert row["record_type"] == "component_current"
    assert row["refdes"] == "U2"


def test_rail_current_patch_materializes_current_model_candidate(tmp_path: Path) -> None:
    item = patch(target_type="rail_current_model", target_refdes="V3P3")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-current-model-candidates.json")["current_records"][0]
    assert row["record_type"] == "rail_current"
    assert row["rail_name"] == "V3P3"


def test_branch_current_patch_materializes_current_model_candidate(tmp_path: Path) -> None:
    item = patch(target_type="branch_current_model", target_refdes="br_v3p3")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-current-model-candidates.json")["current_records"][0]
    assert row["record_type"] == "branch_current"
    assert row["branch_id"] == "br_v3p3"


def test_current_candidate_preserves_condition_evidence_and_provenance(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-current-model-candidates.json")["current_records"][0]
    assert row["condition"] == "active mode, VDD=3.3V"
    assert row["evidence_refs"][0]["source_file"] == "datasheets/U2.pdf"
    assert row["source_patch_id"].startswith("patch_")


def test_current_candidate_uses_normalized_amp_value(tmp_path: Path) -> None:
    item = patch(value=85, unit="mA", normalized_value=0.085, normalized_unit="A")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-current-model-candidates.json")["current_records"][0]
    assert row["current_a"] == 0.085
    assert row["current_unit"] == "A"


def test_fuse_rating_patch_materializes_rating_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="rating_model_patch", target_type="fuse_rating", target_refdes="F1", field_name="hold_current", normalized_value=1.1)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"][0]
    assert row["target_type"] == "fuse"


def test_connector_pin_rating_patch_materializes_rating_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="rating_model_patch", target_type="connector_pin_rating", target_refdes="J1", field_name="pin_current_max", normalized_value=2.0)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"][0]["target_type"] == "connector_pin"


def test_regulator_rating_patch_materializes_rating_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="rating_model_patch", target_type="regulator_rating", target_refdes="U1", field_name="output_current_max", normalized_value=1.5)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"][0]["target_type"] == "regulator"


def test_rating_candidate_preserves_condition_evidence_and_provenance(tmp_path: Path) -> None:
    item = patch(patch_class="rating_model_patch", target_type="fuse_rating", target_refdes="F1", field_name="hold_current", condition="25C")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"][0]
    assert row["condition"] == "25C"
    assert row["evidence_refs"][0]["evidence_quote"] == "IDD max 85 mA"


def test_rating_candidate_uses_normalized_current_value(tmp_path: Path) -> None:
    item = patch(patch_class="rating_model_patch", target_type="fuse_rating", target_refdes="F1", field_name="hold_current", value=1100, unit="mA", normalized_value=1.1, normalized_unit="A")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rating-model-candidates.json")["rating_records"][0]["value_a"] == 1.1


def test_component_role_patch_materializes_role_addendum(tmp_path: Path) -> None:
    item = patch(patch_class="role_resolution_addendum", target_type="component_role", target_refdes="U1", field_name="component_role", value="regulator", normalized_value="regulator", normalized_unit="text")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-role-resolution-addenda.json")["role_addenda"][0]["role"] == "regulator"


def test_pass_through_role_patch_materializes_role_addendum(tmp_path: Path) -> None:
    item = patch(patch_class="role_resolution_addendum", target_type="pass_through_role", target_refdes="F1", field_name="role_subtype", value="fuse", normalized_value="fuse", normalized_unit="text")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-role-resolution-addenda.json")["role_addenda"][0]["role_subtype"] == "fuse"


def test_pin_role_patch_materializes_pin_role_addendum(tmp_path: Path) -> None:
    item = patch(patch_class="pin_role_addendum", target_type="pin_role", target_refdes="U1", field_name="output_pin", value="VOUT", normalized_value="output", normalized_unit="text", pin_name="VOUT")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-pin-role-addenda.json")["pin_role_addenda"][0]["pin_name"] == "VOUT"


def test_rail_relationship_patch_materializes_rail_relationship_hint(tmp_path: Path) -> None:
    item = patch(patch_class="rail_relationship_hint", target_type="rail_relationship_hint", target_refdes="U1", field_name="rail_relationship", value="regulator_input_output", normalized_value="regulator_input_output", normalized_unit="text", input_pin="VIN", output_pin="VOUT")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rail-relationship-hints.json")["rail_relationship_hints"][0]["relationship_type"] == "regulator_input_output"


def test_rail_relationship_does_not_invent_board_rail_names(tmp_path: Path) -> None:
    item = patch(patch_class="rail_relationship_hint", target_type="rail_relationship_hint", target_refdes="U1", field_name="rail_relationship", value="regulator_input_output", normalized_value="regulator_input_output", normalized_unit="text", input_pin="VIN", output_pin="VOUT")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-rail-relationship-hints.json")["rail_relationship_hints"][0]
    assert row["input_rail_name"] is None
    assert row["output_rail_name"] is None


def test_capacitor_esr_patch_materializes_passive_support_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="passive_support_data_patch", target_type="capacitor_support_data", target_refdes="C1", field_name="esr", value=0.05, unit="ohm", normalized_value=0.05, normalized_unit="ohm")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-passive-support-candidates.json")["passive_support_records"][0]["field_name"] == "esr"


def test_ferrite_impedance_patch_materializes_passive_support_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="passive_support_data_patch", target_type="ferrite_rating", target_refdes="FB1", field_name="impedance", value=600, unit="ohm", normalized_value=600, normalized_unit="ohm")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-passive-support-candidates.json")["passive_support_records"][0]["target_type"] == "ferrite_rating"


def test_passive_candidate_preserves_units_condition_and_evidence(tmp_path: Path) -> None:
    item = patch(patch_class="passive_support_data_patch", target_type="capacitor_support_data", target_refdes="C1", field_name="esr", value=0.05, unit="ohm", normalized_value=0.05, normalized_unit="ohm", condition="100 kHz")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-passive-support-candidates.json")["passive_support_records"][0]
    assert row["normalized_unit"] == "ohm"
    assert row["condition"] == "100 kHz"
    assert row["evidence_refs"][0]["source_file"] == "datasheets/U2.pdf"


def test_rejected_or_skipped_source_items_are_not_materialized(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([], skipped=[{"skipped_item_id": "s1"}]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["summary"]["materialized_candidate_count"] == 0


def test_unusable_patch_is_not_materialized(tmp_path: Path) -> None:
    item = patch(usable_for_ingestion=False)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_patches"][0]["reason_code"] == "not_usable_for_ingestion"


def test_patch_requiring_human_approval_is_not_materialized_by_default(tmp_path: Path) -> None:
    item = patch(requires_human_approval_before_ingestion=True, usable_for_ingestion=False)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-human-review-candidates.json")["human_review_candidates"] == []


def test_include_human_review_materializes_non_usable_human_review_candidate(tmp_path: Path) -> None:
    item = patch(patch_class="human_review_patch_candidate", usable_for_ingestion=False, requires_human_approval_before_ingestion=True)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]), include_human=True)
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-human-review-candidates.json")["human_review_candidates"][0]
    assert row["usable_for_ingestion"] is False


def test_conflicted_patch_is_blocked_by_default(tmp_path: Path) -> None:
    item = patch()
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item], conflicts=[conflict_for(item["patch_id"])]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["blocked_by_conflict"][0]["source_patch_id"] == item["patch_id"]


def test_allow_conflicted_materializes_non_usable_human_review_candidate(tmp_path: Path) -> None:
    item = patch()
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item], conflicts=[conflict_for(item["patch_id"])]), allow_conflicted=True)
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-human-review-candidates.json")["human_review_candidates"][0]
    assert row["usable_for_ingestion"] is False
    assert row["conflict_ids"] == ["conflict_conflicting_candidate_values_abc123"]


def test_missing_evidence_patch_is_skipped(tmp_path: Path) -> None:
    item = patch(evidence_quote=None)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_patches"][0]["reason_code"] == "missing_evidence"


def test_missing_target_identity_patch_is_skipped(tmp_path: Path) -> None:
    item = patch(target_refdes=None, target_mpn=None)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_patches"][0]["reason_code"] == "missing_target_identity"


def test_no_findings_or_pass_fail_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    item = patch(finding_id="F1", severity="high", pass_fail="pass")
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    keys = {key for path in artifact_paths(out_dir) for key in all_keys(read_json(path))}
    assert not {"finding_id", "severity", "pass_fail", "compliance_pass"}.intersection(keys)


def test_forbidden_mutation_fields_are_not_emitted(tmp_path: Path) -> None:
    item = patch(apply_to_artifact="core.json", overwrite=True)
    result, out_dir, _ = invoke(tmp_path, bundle_fixture([item]))
    assert result.returncode == 0, result.stderr + result.stdout
    keys = {key for path in artifact_paths(out_dir) for key in all_keys(read_json(path))}
    assert not {"apply_to_artifact", "overwrite", "replace_existing"}.intersection(keys)


def test_materializer_does_not_modify_source_patch_bundle(tmp_path: Path) -> None:
    result, _, bundle_path = invoke(tmp_path)
    before = bundle_path.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr + result.stdout
    after = bundle_path.read_text(encoding="utf-8")
    assert before == after


def test_materializer_does_not_write_core_normalized_or_calculation_artifacts(tmp_path: Path) -> None:
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


def test_candidate_ids_are_deterministic(tmp_path: Path) -> None:
    result1, out1, _ = invoke(tmp_path / "a")
    result2, out2, _ = invoke(tmp_path / "b")
    assert result1.returncode == 0, result1.stderr + result1.stdout
    assert result2.returncode == 0, result2.stderr + result2.stdout
    id1 = read_json(out1 / "ai-current-model-candidates.json")["current_records"][0]["record_id"]
    id2 = read_json(out2 / "ai-current-model-candidates.json")["current_records"][0]["record_id"]
    assert id1 == id2


def test_candidate_order_is_deterministic(tmp_path: Path) -> None:
    items = [patch(patch_id="patch_z", target_refdes="U9"), patch(patch_id="patch_a", target_refdes="U1")]
    result, out_dir, _ = invoke(tmp_path, bundle_fixture(items))
    assert result.returncode == 0, result.stderr + result.stdout
    ids = [row["record_id"] for row in read_json(out_dir / "ai-current-model-candidates.json")["current_records"]]
    assert ids == sorted(ids)


def test_docs_state_materializer_does_not_call_ai() -> None:
    assert "does not call AI" in DOC.read_text(encoding="utf-8")


def test_docs_state_candidates_are_not_directly_applied() -> None:
    assert "not directly applied" in DOC.read_text(encoding="utf-8")


def test_docs_state_normalized_outputs_are_not_overwritten() -> None:
    assert "do not overwrite" in DOC.read_text(encoding="utf-8")


def test_docs_state_conflicts_require_human_review() -> None:
    assert "require human review" in DOC.read_text(encoding="utf-8")
