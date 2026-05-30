from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ai_candidate_adapter_build.py"
CURRENT_INGEST = ROOT / "scripts" / "current_model_ingest.py"
RATING_INGEST = ROOT / "scripts" / "rating_model_ingest.py"
SCHEMA = ROOT / "schemas" / "ai_candidate_adapter_schema.json"
DOC = ROOT / "docs" / "ai_candidate_adapter_build.md"


def run_build(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(source_file: str = "datasheets/U2.pdf", page: int = 92, quote: str = "IDD max 85 mA") -> list[dict[str, Any]]:
    return [{"source_file": source_file, "source_page": page, "evidence_quote": quote}]


def current_candidate(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "ai_cur_u2_max_current",
        "record_type": "component_current",
        "source": "ai_validated_datasheet",
        "refdes": "U2",
        "mpn": "MCU-456",
        "rail_name": "V3P3",
        "branch_id": None,
        "field_name": "max_current_a",
        "current_a": 0.085,
        "current_unit": "A",
        "condition": "active mode, VDD=3.3V",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "requires_human_approval_before_ingestion": False,
        "evidence_refs": evidence(),
        "source_patch_id": "patch_u2_current",
        "source_packet_id": "12B-001",
        "source_item_id": "ai_item_u2_current",
        "source_accepted_item_id": "accepted_u2_current",
        "missing_data_item_ids": ["mdi_u2_current"],
    }
    row.update(overrides)
    return row


def rating_candidate(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "ai_rate_f1_hold_current",
        "record_type": "rating",
        "source": "ai_validated_datasheet",
        "target_type": "fuse",
        "refdes": "F1",
        "pin": None,
        "mpn": "FUSE-123",
        "rating_name": "hold_current",
        "value_a": 1.1,
        "unit": "A",
        "condition": "25 C",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "requires_human_approval_before_ingestion": False,
        "evidence_refs": evidence("datasheets/F1.pdf", 3, "Hold current 1.1 A"),
        "source_patch_id": "patch_f1_rating",
        "source_packet_id": "12C-001",
        "source_item_id": "ai_item_f1_rating",
        "source_accepted_item_id": "accepted_f1_rating",
        "missing_data_item_ids": ["mdi_f1_rating"],
    }
    row.update(overrides)
    return row


def role_addendum(**overrides: Any) -> dict[str, Any]:
    row = {
        "addendum_id": "ai_role_u12",
        "refdes": "U12",
        "mpn": "REG-1",
        "field_name": "component_role",
        "role": "regulator",
        "role_subtype": "buck",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "evidence_refs": evidence("datasheets/U12.pdf", 1, "buck regulator"),
        "source_patch_id": "patch_role",
        "source_packet_id": "12A-001",
        "source_item_id": "ai_item_role",
        "source_accepted_item_id": "accepted_role",
        "missing_data_item_ids": ["mdi_role"],
    }
    row.update(overrides)
    return row


def pin_addendum(**overrides: Any) -> dict[str, Any]:
    row = {
        "addendum_id": "ai_pin_u12_vout",
        "refdes": "U12",
        "mpn": "REG-1",
        "pin": "5",
        "pin_name": "VOUT",
        "field_name": "output_pin",
        "pin_role": "output",
        "pin_direction": "output",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "evidence_refs": evidence("datasheets/U12.pdf", 4, "VOUT pin"),
        "source_patch_id": "patch_pin",
        "source_packet_id": "12A-002",
        "source_item_id": "ai_item_pin",
        "source_accepted_item_id": "accepted_pin",
        "missing_data_item_ids": ["mdi_pin"],
    }
    row.update(overrides)
    return row


def rail_hint(**overrides: Any) -> dict[str, Any]:
    row = {
        "hint_id": "ai_rail_u12",
        "refdes": "U12",
        "mpn": "REG-1",
        "input_pin": "VIN",
        "output_pin": "VOUT",
        "input_rail_name": None,
        "output_rail_name": None,
        "relationship_type": "regulator_input_output",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "evidence_refs": evidence("datasheets/U12.pdf", 4, "VIN to VOUT regulator"),
        "source_patch_id": "patch_rail",
        "source_packet_id": "12A-003",
        "source_item_id": "ai_item_rail",
        "source_accepted_item_id": "accepted_rail",
        "missing_data_item_ids": ["mdi_rail"],
    }
    row.update(overrides)
    return row


def passive_record(**overrides: Any) -> dict[str, Any]:
    row = {
        "record_id": "ai_passive_c1_esr",
        "target_type": "capacitor_support_data",
        "refdes": "C1",
        "mpn": "CAP-1",
        "field_name": "esr",
        "value": 0.02,
        "unit": "ohm",
        "normalized_value": 0.02,
        "normalized_unit": "ohm",
        "condition": "100 kHz, 25 C",
        "basis": "ai_validated_datasheet",
        "confidence": 0.86,
        "human_review_needed": False,
        "usable_for_ingestion": True,
        "evidence_refs": evidence("datasheets/C1.pdf", 8, "ESR 20 mOhm"),
        "source_patch_id": "patch_passive",
        "source_packet_id": "12D-001",
        "source_item_id": "ai_item_passive",
        "source_accepted_item_id": "accepted_passive",
        "missing_data_item_ids": ["mdi_passive"],
    }
    row.update(overrides)
    return row


def human_review_candidate(**overrides: Any) -> dict[str, Any]:
    row = {
        "candidate_id": "human_review_conflict",
        "reason_code": "conflicted_candidate",
        "detail": "conflict requires review",
        "candidate_type": "current_model_candidate",
        "usable_for_ingestion": False,
        "conflict_ids": ["conflict_1"],
        "evidence_refs": evidence(),
        "source_patch_id": "patch_conflict",
        "source_packet_id": "12B-009",
        "source_item_id": "ai_item_conflict",
        "source_accepted_item_id": "accepted_conflict",
        "missing_data_item_ids": ["mdi_conflict"],
    }
    row.update(overrides)
    return row


def candidate_manifest() -> dict[str, Any]:
    files = {
        "current_model_candidates": "ai-current-model-candidates.json",
        "rating_model_candidates": "ai-rating-model-candidates.json",
        "role_resolution_addenda": "ai-role-resolution-addenda.json",
        "pin_role_addenda": "ai-pin-role-addenda.json",
        "rail_relationship_hints": "ai-rail-relationship-hints.json",
        "passive_support_candidates": "ai-passive-support-candidates.json",
        "human_review_candidates": "ai-human-review-candidates.json",
    }
    return {
        "project": "TestProject",
        "generated_at_utc": "2026-05-30T00:00:00Z",
        "schema_version": "ai_candidate_inputs_v1",
        "source_artifacts": [],
        "source_patch_bundle": "patch_bundle.json",
        "candidate_materialization_pass": True,
        "candidate_files": files,
        "skipped_patches": [],
        "blocked_by_conflict": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def write_candidate_dir(
    path: Path,
    *,
    currents: list[dict[str, Any]] | None = None,
    ratings: list[dict[str, Any]] | None = None,
    roles: list[dict[str, Any]] | None = None,
    pins: list[dict[str, Any]] | None = None,
    rails: list[dict[str, Any]] | None = None,
    passives: list[dict[str, Any]] | None = None,
    human: list[dict[str, Any]] | None = None,
    manifest_text: str | None = None,
) -> Path:
    if manifest_text is None:
        write_json(path / "ai-candidate-inputs.json", candidate_manifest())
    else:
        path.mkdir(parents=True, exist_ok=True)
        (path / "ai-candidate-inputs.json").write_text(manifest_text, encoding="utf-8")
    write_json(path / "ai-current-model-candidates.json", {"project": "TestProject", "current_records": currents if currents is not None else [current_candidate()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-rating-model-candidates.json", {"project": "TestProject", "rating_records": ratings if ratings is not None else [rating_candidate()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-role-resolution-addenda.json", {"project": "TestProject", "role_addenda": roles if roles is not None else [role_addendum()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-pin-role-addenda.json", {"project": "TestProject", "pin_role_addenda": pins if pins is not None else [pin_addendum()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-rail-relationship-hints.json", {"project": "TestProject", "rail_relationship_hints": rails if rails is not None else [rail_hint()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-passive-support-candidates.json", {"project": "TestProject", "passive_support_records": passives if passives is not None else [passive_record()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "ai-human-review-candidates.json", {"project": "TestProject", "human_review_candidates": human if human is not None else [human_review_candidate()], "summary": {}, "errors": [], "warnings": []})
    write_json(path / "materialization-status.json", {"project": "TestProject", "status": "materialized"})
    return path


def invoke(
    tmp_path: Path,
    *,
    currents: list[dict[str, Any]] | None = None,
    ratings: list[dict[str, Any]] | None = None,
    roles: list[dict[str, Any]] | None = None,
    pins: list[dict[str, Any]] | None = None,
    rails: list[dict[str, Any]] | None = None,
    passives: list[dict[str, Any]] | None = None,
    human: list[dict[str, Any]] | None = None,
    include_human: bool = False,
    include_role: bool = False,
    include_pin: bool = False,
    include_rail: bool = False,
    manifest_text: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    candidate_dir = write_candidate_dir(
        tmp_path / "exports" / "TestProject" / "ai_candidates",
        currents=currents,
        ratings=ratings,
        roles=roles,
        pins=pins,
        rails=rails,
        passives=passives,
        human=human,
        manifest_text=manifest_text,
    )
    out_dir = tmp_path / "exports" / "TestProject" / "ai_adapters"
    args = ["--project", "TestProject", "--candidate-dir", str(candidate_dir), "--out-dir", str(out_dir)]
    if include_human:
        args.append("--include-human-review")
    if include_role:
        args.append("--include-role-addenda")
    if include_pin:
        args.append("--include-pin-addenda")
    if include_rail:
        args.append("--include-rail-hints")
    return run_build(*args), out_dir, candidate_dir


def artifact_paths(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob("*.json"))


def manifest(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-adapter-manifest.json")


def current_input(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-current-model-ingest-input.json")


def rating_input(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-rating-model-ingest-input.json")


def human_review(out_dir: Path) -> dict[str, Any]:
    return read_json(out_dir / "ai-human-review-adapter.json")


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


def current_records(out_dir: Path) -> list[dict[str, Any]]:
    data = current_input(out_dir)
    return data["component_currents"] + data["rail_currents"] + data["branch_currents"]


def adapter_record_ids(out_dir: Path) -> list[str]:
    ids: list[str] = []
    ids.extend(row["record_id"] for row in current_records(out_dir))
    ids.extend(row["record_id"] for row in rating_input(out_dir)["ratings"])
    return ids


def test_missing_candidate_dir_exits_2(tmp_path: Path) -> None:
    result = run_build("--project", "TestProject", "--candidate-dir", str(tmp_path / "missing"), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_missing_candidate_manifest_exits_2(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    result = run_build("--project", "TestProject", "--candidate-dir", str(candidate_dir), "--out-dir", str(tmp_path / "out"))
    assert result.returncode == 2


def test_malformed_candidate_manifest_exits_2(tmp_path: Path) -> None:
    result, _, _ = invoke(tmp_path, manifest_text="{bad")
    assert result.returncode == 2


def test_output_directory_shape_created(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "ai-adapter-manifest.json",
        "ai-current-model-ingest-input.json",
        "ai-rating-model-ingest-input.json",
        "ai-role-resolution-addenda-adapter.json",
        "ai-pin-role-addenda-adapter.json",
        "ai-rail-relationship-hints-adapter.json",
        "ai-passive-support-adapter.json",
        "ai-human-review-adapter.json",
        "adapter-status.json",
    }
    assert expected == {path.name for path in artifact_paths(out_dir)}


def test_manifest_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {"project", "generated_at_utc", "schema_version", "source_artifacts", "source_candidate_manifest", "adapter_build_pass", "adapter_files", "skipped_candidates", "summary", "errors", "warnings"}
    assert expected.issubset(manifest(out_dir))


def test_cli_writes_valid_json_artifacts(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        assert isinstance(read_json(path), dict)


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(current_a=float("nan"))], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    for path in artifact_paths(out_dir):
        for value in all_values(read_json(path)):
            assert not (isinstance(value, float) and not math.isfinite(value))


def test_schema_validates_manifest_status_and_adapter_files(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(SCHEMA)
    for path in artifact_paths(out_dir):
        jsonschema.validate(instance=read_json(path), schema=schema)


def test_summary_counts_match_adapter_files(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, include_role=True, include_pin=True, include_rail=True, include_human=True)
    assert result.returncode == 0, result.stderr + result.stdout
    summary = manifest(out_dir)["summary"]
    assert summary["current_adapter_record_count"] == len(current_records(out_dir))
    assert summary["rating_adapter_record_count"] == len(rating_input(out_dir)["ratings"])
    assert summary["human_review_adapter_count"] == len(human_review(out_dir)["human_review_records"])


def test_component_current_candidate_maps_to_current_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(record_type="component_current")], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert len(current_input(out_dir)["component_currents"]) == 1


def test_rail_current_candidate_maps_to_current_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(record_id="ai_cur_v3p3", record_type="rail_current", refdes=None, rail_name="V3P3")], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert current_input(out_dir)["rail_currents"][0]["rail_name"] == "V3P3"


def test_branch_current_candidate_maps_to_current_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(record_id="ai_cur_br1", record_type="branch_current", refdes=None, branch_id="br1")], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert current_input(out_dir)["branch_currents"][0]["branch_id"] == "br1"


def test_current_adapter_preserves_condition_evidence_and_provenance(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    row = current_input(out_dir)["component_currents"][0]
    assert row["condition"] == "active mode, VDD=3.3V"
    assert row["evidence_refs"] and row["ai_evidence_refs"]
    assert row["source_patch_id"] == "patch_u2_current"
    assert row["source_packet_id"] == "12B-001"


def test_current_adapter_uses_amp_value_without_inference(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(current_a=0.123)], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    row = current_input(out_dir)["component_currents"][0]
    assert row["value"] == 0.123
    assert row["unit"] == "A"


def test_current_adapter_does_not_infer_missing_refdes_rail_or_branch(tmp_path: Path) -> None:
    rows = [
        current_candidate(record_id="bad_component", record_type="component_current", refdes=None),
        current_candidate(record_id="bad_rail", record_type="rail_current", refdes=None, rail_name=None),
        current_candidate(record_id="bad_branch", record_type="branch_current", refdes=None, branch_id=None),
    ]
    result, out_dir, _ = invoke(tmp_path, currents=rows, ratings=[], roles=[], pins=[], rails=[], passives=[], human=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert current_records(out_dir) == []
    assert {row["reason_code"] for row in manifest(out_dir)["skipped_candidates"]} == {"missing_target_identity"}


def test_fuse_rating_candidate_maps_to_rating_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(target_type="fuse", refdes="F1")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"][0]["target_type"] == "fuse"


def test_connector_pin_rating_candidate_maps_to_rating_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(record_id="pin", target_type="connector_pin", refdes="J1", pin="1", rating_name="pin_current_max")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"][0]["pin"] == "1"


def test_connector_rating_candidate_maps_to_rating_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(record_id="conn", target_type="connector", refdes="J1", pin=None, rating_name="current_max")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"][0]["target_type"] == "connector"


def test_regulator_rating_candidate_maps_to_rating_ingest_input(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(record_id="reg", target_type="regulator", refdes="U12", rating_name="output_current_max")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"][0]["target_type"] == "regulator"


def test_rating_adapter_preserves_condition_evidence_and_provenance(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[])
    assert result.returncode == 0, result.stderr + result.stdout
    row = rating_input(out_dir)["ratings"][0]
    assert row["condition"] == "25 C"
    assert row["evidence_refs"] and row["ai_evidence_refs"]
    assert row["source_patch_id"] == "patch_f1_rating"


def test_rating_adapter_does_not_expand_connector_wide_rating_to_all_pins(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(target_type="connector", refdes="J1", pin=None, rating_name="current_max")])
    assert result.returncode == 0, result.stderr + result.stdout
    row = rating_input(out_dir)["ratings"][0]
    assert row["target_type"] == "connector"
    assert row["pin"] is None


def test_rating_adapter_does_not_infer_regulator_input_output_side(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(target_type="regulator", refdes="U12", rating_name="current_max")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"][0]["target_type"] == "regulator"


def test_voltage_rating_does_not_become_current_margin_rating(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[rating_candidate(record_id="volt", rating_name="voltage_rating", value_a=None, unit="V")])
    assert result.returncode == 0, result.stderr + result.stdout
    assert rating_input(out_dir)["ratings"] == []
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "unsupported_field_name"


def test_role_addendum_candidate_maps_to_role_adapter(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[], include_role=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-role-resolution-addenda-adapter.json")["role_addenda"][0]["refdes"] == "U12"


def test_pin_role_candidate_maps_to_pin_adapter(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[], include_pin=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-pin-role-addenda-adapter.json")["pin_role_addenda"][0]["pin_name"] == "VOUT"


def test_rail_relationship_hint_maps_to_rail_hint_adapter(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[], include_rail=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-rail-relationship-hints-adapter.json")["rail_relationship_hints"][0]["relationship_type"] == "regulator_input_output"


def test_rail_hint_adapter_does_not_invent_board_rail_names(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[], include_rail=True)
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out_dir / "ai-rail-relationship-hints-adapter.json")["rail_relationship_hints"][0]
    assert row["input_rail_name"] is None
    assert row["output_rail_name"] is None


def test_passive_support_candidate_maps_to_passive_adapter(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out_dir / "ai-passive-support-adapter.json")["passive_support_records"][0]["field_name"] == "esr"


def test_human_review_candidates_excluded_by_default(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert human_review(out_dir)["human_review_records"] == []


def test_include_human_review_routes_to_human_review_adapter_non_usable(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[], ratings=[], include_human=True)
    assert result.returncode == 0, result.stderr + result.stdout
    row = human_review(out_dir)["human_review_records"][0]
    assert row["usable_for_ingestion"] is False


def test_conflicted_candidate_routes_to_human_review_adapter(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(conflict_ids=["conflict_1"])], ratings=[], human=[], include_human=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "conflicted_candidate"
    assert human_review(out_dir)["human_review_records"][0]["usable_for_ingestion"] is False


def test_unusable_candidate_is_skipped(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(usable_for_ingestion=False)], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "not_usable_for_ingestion"


def test_missing_evidence_candidate_is_skipped(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(evidence_refs=[])], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "missing_evidence"


def test_missing_target_identity_candidate_is_skipped(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(refdes=None)], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "missing_target_identity"


def test_skipped_candidates_have_stable_reason_codes(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[current_candidate(current_a=None)], ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert manifest(out_dir)["skipped_candidates"][0]["reason_code"] == "normalized_value_missing"


def test_current_adapter_output_can_be_consumed_by_current_model_ingest(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    out = tmp_path / "normalized-current.json"
    ingest = subprocess.run([sys.executable, str(CURRENT_INGEST), "--project", "TestProject", "--current-model", str(out_dir / "ai-current-model-ingest-input.json"), "--out", str(out)], cwd=ROOT, text=True, capture_output=True)
    assert ingest.returncode == 0, ingest.stderr + ingest.stdout
    artifact = read_json(out)
    assert artifact["normalized_currents"][0]["basis"] == "ai_validated_datasheet"
    assert artifact["normalized_currents"][0]["evidence_refs"]


def test_rating_adapter_output_can_flow_through_current_model_ingest_then_rating_model_ingest(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path, currents=[])
    assert result.returncode == 0, result.stderr + result.stdout
    current_out = tmp_path / "normalized-current.json"
    rating_out = tmp_path / "normalized-ratings.json"
    current = subprocess.run([sys.executable, str(CURRENT_INGEST), "--project", "TestProject", "--current-model", str(out_dir / "ai-rating-model-ingest-input.json"), "--out", str(current_out)], cwd=ROOT, text=True, capture_output=True)
    assert current.returncode == 0, current.stderr + current.stdout
    rating = subprocess.run([sys.executable, str(RATING_INGEST), "--project", "TestProject", "--current-models-normalized", str(current_out), "--out", str(rating_out)], cwd=ROOT, text=True, capture_output=True)
    assert rating.returncode == 0, rating.stderr + rating.stdout
    artifact = read_json(rating_out)
    assert artifact["normalized_ratings"][0]["basis"] == "ai_validated_datasheet"
    assert artifact["normalized_ratings"][0]["evidence_refs"]


def test_adapter_does_not_require_changes_to_existing_ingestion_scripts(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "current_model_ingest.py" not in read_json(out_dir / "adapter-status.json")["warnings"]


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


def test_adapter_builder_does_not_modify_source_candidate_files(tmp_path: Path) -> None:
    result, _, candidate_dir = invoke(tmp_path)
    before = {path.name: path.read_text(encoding="utf-8") for path in candidate_dir.glob("*.json")}
    assert result.returncode == 0, result.stderr + result.stdout
    result2 = run_build("--project", "TestProject", "--candidate-dir", str(candidate_dir), "--out-dir", str(tmp_path / "other_out"))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    after = {path.name: path.read_text(encoding="utf-8") for path in candidate_dir.glob("*.json")}
    assert before == after


def test_adapter_builder_does_not_write_core_normalized_or_calculation_artifacts(tmp_path: Path) -> None:
    result, out_dir, _ = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    forbidden = {
        "TestProject-current-models-normalized.json",
        "TestProject-rating-models-normalized.json",
        "TestProject-topology-current-allocation.json",
        "TestProject-topology-copper-calculations.json",
        "TestProject-topology-margin-calculations.json",
    }
    assert forbidden.isdisjoint({path.name for path in out_dir.parent.glob("*.json")})


def test_no_live_ai_or_network_client_imports_are_used() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()
    for token in ("openai", "anthropic", "gemini", "requests", "httpx", "urllib", "socket"):
        assert token not in text


def test_adapter_ids_are_deterministic(tmp_path: Path) -> None:
    result, out_dir, candidate_dir = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    first = adapter_record_ids(out_dir)
    second_out = tmp_path / "exports" / "TestProject" / "ai_adapters_2"
    result2 = run_build("--project", "TestProject", "--candidate-dir", str(candidate_dir), "--out-dir", str(second_out))
    assert result2.returncode == 0, result2.stderr + result2.stdout
    assert first == adapter_record_ids(second_out)


def test_adapter_order_is_deterministic(tmp_path: Path) -> None:
    rows = [current_candidate(record_id="z"), current_candidate(record_id="a", refdes="U3")]
    result, out_dir, _ = invoke(tmp_path, currents=rows, ratings=[])
    assert result.returncode == 0, result.stderr + result.stdout
    assert [row["source_candidate_record_id"] for row in current_input(out_dir)["component_currents"]] == ["a", "z"]


def test_docs_state_adapter_builder_does_not_call_ai() -> None:
    assert "does not call ai" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_adapter_files_are_not_directly_applied() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "not merged" in text or "not apply candidates to core artifacts" in text


def test_docs_state_normalized_outputs_are_not_overwritten() -> None:
    assert "never overwrite normalized outputs" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_current_and_rating_adapters_are_manual_ingest_inputs() -> None:
    assert "manual inputs" in DOC.read_text(encoding="utf-8").lower()


def test_docs_state_role_pin_rail_addenda_are_not_merged() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "role, pin, rail" in text and "not merged" in text
