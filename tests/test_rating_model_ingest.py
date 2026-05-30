from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rating_model_ingest.py"


def run_ingest(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rating_record(
    *,
    record_id: str = "cur_rating_connector_pin_p20_1_000001",
    target_type: str = "connector_pin",
    refdes: str | None = "P20",
    pin: str | None = "1",
    rail_name: str | None = None,
    branch_id: str | None = None,
    rating_name: str = "pin_current_max",
    value: Any = 2.0,
    unit: str | None = "A",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "record_id": record_id,
        "record_type": "rating",
        "target_type": target_type,
        "rating_name": rating_name,
        "value": value,
        "basis": "datasheet",
        "source": "current_model",
        "confidence": 0.95,
        "evidence_refs": ["datasheet:P20:p3"],
        "source_artifacts": [{"artifact_type": "current_model", "path": "current-model.json", "record_id": record_id}],
        "provenance": {"original_value": value, "original_unit": unit, "original_rating_name": rating_name},
    }
    if refdes is not None:
        row["refdes"] = refdes
    if pin is not None:
        row["pin"] = pin
    if rail_name is not None:
        row["rail_name"] = rail_name
    if branch_id is not None:
        row["branch_id"] = branch_id
    if unit is not None:
        row["unit"] = unit
    return row


def current_models_fixture(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "schema_version": "1.0",
        "normalized_currents": records if records is not None else [rating_record()],
        "rejected_currents": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def manifest_item(
    category: str = "rating_missing",
    target_id: str = "P20",
    *,
    pin: str | None = "1",
    affected_components: list[str] | None = None,
    affected_rails: list[str] | None = None,
    affected_branches: list[str] | None = None,
    group_id: str = "group_rating_missing_p20",
) -> dict[str, Any]:
    item = {
        "manifest_id": f"mdi_manifest_{category}_{target_id}",
        "source_missing_data_id": f"source_{category}_{target_id}",
        "category": category,
        "target_type": "component",
        "target_id": target_id,
        "normalized_target": target_id,
        "affected_components": affected_components if affected_components is not None else [target_id],
        "affected_rails": affected_rails or [],
        "affected_branches": affected_branches or [],
        "blocks": ["fuse_margin", "connector_pin_current_margin", "regulator_load_margin"],
        "group_id": group_id,
        "resolution_path": "datasheet_extraction",
        "resolution_queue": "datasheet_extraction",
    }
    if pin is not None:
        item["pin"] = pin
    return item


def manifest_fixture(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "manifest_items": items if items is not None else [manifest_item()],
        "groups": [],
        "warnings": [],
        "errors": [],
    }


def role_resolution_fixture(roles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "schema_version": "1.0",
        "component_roles": roles or [{"refdes": "F1", "role": "pass_through", "role_subtype": "fuse", "confidence": 0.9}],
        "role_resolution_pass": True,
    }


def branch_topology_fixture(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"project": "TestProject", "branches": rows}


def invoke(
    tmp_path: Path,
    current_models: dict[str, Any] | None = None,
    *,
    manifest: dict[str, Any] | None = None,
    role_resolution: dict[str, Any] | None = None,
    branch_topology: dict[str, Any] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    current_models_path = write_json(tmp_path / "current-models-normalized.json", current_models or current_models_fixture())
    out = tmp_path / "rating-models-normalized.json"
    args = ["--project", "TestProject", "--current-models-normalized", str(current_models_path), "--out", str(out)]
    if manifest is not None:
        args.extend(["--missing-data-manifest", str(write_json(tmp_path / "manifest.json", manifest))])
    if role_resolution is not None:
        args.extend(["--role-resolution", str(write_json(tmp_path / "role-resolution.json", role_resolution))])
    if branch_topology is not None:
        args.extend(["--branch-topology-enriched", str(write_json(tmp_path / "branch-topology.json", branch_topology))])
    return run_ingest(*args), out


def only_rating(artifact: dict[str, Any]) -> dict[str, Any]:
    assert len(artifact["normalized_ratings"]) == 1
    return artifact["normalized_ratings"][0]


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


def test_missing_required_current_models_normalized_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_ingest("--project", "TestProject", "--current-models-normalized", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_malformed_current_models_normalized_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    out = tmp_path / "out.json"
    result = run_ingest("--project", "TestProject", "--current-models-normalized", str(bad), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "project",
        "generated_at_utc",
        "execution_pass",
        "rating_model_ingest_pass",
        "schema_version",
        "source_artifacts",
        "normalized_ratings",
        "rejected_ratings",
        "unresolved_rating_links",
        "summary",
        "errors",
        "warnings",
    }
    assert expected.issubset(read_json(out))


def test_cli_writes_valid_json_artifact(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["project"] == "TestProject"


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        if isinstance(value, float):
            assert math.isfinite(value)


def test_summary_counts_match_arrays(tmp_path: Path) -> None:
    records = [
        rating_record(),
        rating_record(record_id="cur_rating_fuse_f1_hold", target_type="fuse", refdes="F1", pin=None, rating_name="hold_current", value=0.5),
        {"record_id": "cur_branch", "record_type": "branch_current", "branch_id": "br1", "value": 1.0, "unit": "A"},
    ]
    result, out = invoke(tmp_path, current_models_fixture(records))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    assert summary["input_rating_record_count"] == 2
    assert summary["normalized_rating_count"] == len(artifact["normalized_ratings"])
    assert summary["rejected_rating_count"] == len(artifact["rejected_ratings"])
    assert summary["unresolved_rating_link_count"] == len(artifact["unresolved_rating_links"])
    assert summary["usable_for_margin_calculation_count"] == sum(1 for row in artifact["normalized_ratings"] if row["usable_for_margin_calculation"])
    assert summary["human_review_count"] == sum(1 for row in artifact["normalized_ratings"] if row["human_review_needed"]) + sum(1 for row in artifact["unresolved_rating_links"] if row["human_review_needed"])
    assert summary["error_count"] == len(artifact["errors"])


def test_connector_pin_rating_normalizes_amp_value(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(value=2.0, unit="A")]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["value_a"] == 2.0
    assert row["unit"] == "A"


def test_connector_pin_rating_milliamp_normalizes_to_amp(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(value=500, unit="mA")]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert math.isclose(only_rating(read_json(out))["value_a"], 0.5, rel_tol=1e-12)


def test_fuse_hold_current_rating_normalizes(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="fuse", refdes="F1", pin=None, rating_name="fuse_hold_current", value=0.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["normalized_rating_name"] == "hold_current"
    assert "fuse_margin" in row["applies_to_calculation_families"]


def test_fuse_trip_current_rating_normalizes(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="fuse", refdes="F1", pin=None, rating_name="fuse_trip_current", value=1.0)]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert only_rating(read_json(out))["normalized_rating_name"] == "trip_current"


def test_regulator_output_current_rating_normalizes(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="regulator_output", refdes="U1", pin=None, rail_name="V3P3", rating_name="regulator_output_current", value=1.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["normalized_rating_name"] == "output_current_max"
    assert "regulator_load_margin" in row["applies_to_calculation_families"]


def test_rating_aliases_normalize_to_canonical_names(tmp_path: Path) -> None:
    records = [
        rating_record(record_id="r1", rating_name="connector_pin_current_max"),
        rating_record(record_id="r2", target_type="regulator", refdes="U1", pin=None, rating_name="regulator_current_limit"),
    ]
    result, out = invoke(tmp_path, current_models_fixture(records))

    assert result.returncode == 0, result.stderr + result.stdout
    names = {row["source_record_id"]: row["normalized_rating_name"] for row in read_json(out)["normalized_ratings"]}
    assert names == {"r1": "pin_current_max", "r2": "current_max"}


def test_complete_connector_pin_rating_is_usable_for_margin_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["usable_for_margin_calculation"] is True
    assert row["applies_to_calculation_families"] == ["connector_pin_current_margin"]


def test_complete_fuse_rating_is_usable_for_margin_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="fuse", refdes="F1", pin=None, rating_name="hold_current", value=0.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert only_rating(read_json(out))["usable_for_margin_calculation"] is True


def test_complete_regulator_rating_is_usable_for_margin_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="regulator_output", refdes="U1", pin=None, rail_name="V3P3", rating_name="output_current_max", value=1.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert only_rating(read_json(out))["usable_for_margin_calculation"] is True


def test_rating_without_explicit_target_is_rejected_or_unusable(tmp_path: Path) -> None:
    record = rating_record()
    record.pop("target_type")
    result, out = invoke(tmp_path, current_models_fixture([record]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["normalized_ratings"]
    assert artifact["rejected_ratings"][0]["reason_code"] == "missing_target"


def test_rating_without_unit_is_rejected(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(unit=None)]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["rejected_ratings"][0]["reason_code"] == "unsupported_unit"


def test_unsupported_unit_is_rejected(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(unit="W")]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["rejected_ratings"][0]["reason_code"] == "unsupported_unit"


def test_negative_rating_is_rejected(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(value=-0.1)]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["rejected_ratings"][0]["reason_code"] == "negative_rating"


def test_nonfinite_rating_is_rejected(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(value=float("nan"))]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["rejected_ratings"][0]["reason_code"] == "invalid_value"


def test_does_not_infer_connector_pin_rating_for_all_pins(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="connector", refdes="P20", pin=None, rating_name="pin_current_max")]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["usable_for_margin_calculation"] is False
    assert row.get("pin") is None
    assert "connector pin rating is not expanded to pins without an explicit pin" in row["warnings"]


def test_does_not_infer_component_role_from_refdes_prefix_without_role_resolution(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_models_fixture([rating_record(target_type="component", refdes="F1", pin=None, rating_name="hold_current", value=0.5)]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["normalized_target_type"] == "component"
    assert row["usable_for_margin_calculation"] is False


def test_does_not_calculate_margin(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "calculation_results" not in artifact
    assert "margin_results" not in artifact


def test_no_findings_or_pass_fail_judgments_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    raw_keys = "\n".join(key.lower() for key in all_keys(read_json(out)))
    forbidden = [
        "finding_id",
        "issue_id",
        "compliance_pass",
        "compliance_fail",
        "margin_pass",
        "margin_fail",
        "pass_fail",
        "judgment",
    ]
    assert not any(token in raw_keys for token in forbidden)


def test_manifest_linkage_for_rating_missing_when_present(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, manifest=manifest_fixture([manifest_item()]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_rating_missing_P20"]
    assert row["missing_data_group_ids"] == ["group_rating_missing_p20"]
    assert row["resolution_path"] == "datasheet_extraction"


def test_missing_manifest_link_is_warning_not_failure(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, manifest=manifest_fixture([manifest_item(target_id="P99", affected_components=["P99"])]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["rating_model_ingest_pass"] is True
    assert artifact["unresolved_rating_links"][0]["reason_code"] == "manifest_link_not_found"


def test_role_resolution_can_confirm_rating_target_role(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models_fixture([rating_record(target_type="component", refdes="F1", pin=None, rating_name="hold_current", value=0.5)]),
        role_resolution=role_resolution_fixture([{"refdes": "F1", "role": "pass_through", "role_subtype": "fuse"}]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["normalized_target_type"] == "fuse"
    assert row["usable_for_margin_calculation"] is True


def test_ambiguous_target_mapping_creates_unresolved_rating_link(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_models_fixture([rating_record(target_type="component", refdes="F1", pin=None, rating_name="hold_current", value=0.5)]),
        role_resolution=role_resolution_fixture([
            {"refdes": "F1", "role": "pass_through", "role_subtype": "fuse"},
            {"refdes": "F1", "role": "source", "role_subtype": "regulator"},
        ]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["unresolved_rating_links"][0]["reason_code"] == "ambiguous_target_mapping"
    assert only_rating(artifact)["usable_for_margin_calculation"] is False


def test_pr19_source_artifact_can_supply_missing_rating_name(tmp_path: Path) -> None:
    source_current_model = {
        "ratings": [
            {
                "target_type": "connector_pin",
                "refdes": "P20",
                "pin": "1",
                "rating_name": "pin_current_max",
                "value": 2.0,
                "unit": "A",
                "basis": "datasheet",
                "confidence": 0.95,
                "evidence_refs": ["datasheet:P20:p3"],
            }
        ]
    }
    source_path = write_json(tmp_path / "current-model.json", source_current_model)
    pr19_rating = {
        "record_id": "cur_rating_connector_pin_p20_1_000001",
        "record_type": "rating",
        "target_type": "connector_pin",
        "refdes": "P20",
        "pin": "1",
        "value": 2.0,
        "unit": "A",
        "basis": "datasheet",
        "source_artifacts": [{"artifact_type": "current_model", "path": str(source_path), "record_id": "source_record_000001"}],
    }
    result, out = invoke(tmp_path, current_models_fixture([pr19_rating]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_rating(read_json(out))
    assert row["normalized_rating_name"] == "pin_current_max"
    assert row["original_rating_name"] == "pin_current_max"


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    records = [
        {"record_id": "cur_branch", "record_type": "branch_current", "branch_id": "br_v3p3", "value": 0.25, "unit": "A"},
        rating_record(record_id="cur_rating_connector_pin_p20_1", target_type="connector_pin", refdes="P20", pin="1", rating_name="pin_current_max", value=2.0),
        rating_record(record_id="cur_rating_fuse_f1_hold", target_type="fuse", refdes="F1", pin=None, rating_name="hold_current", value=0.5),
        rating_record(record_id="cur_rating_reg_u1_vout", target_type="regulator_output", refdes="U1", pin=None, rail_name="V3P3", rating_name="output_current_max", value=1.5),
    ]
    result, out = invoke(tmp_path, current_models_fixture(records))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"
    assert artifact["execution_pass"] is True
    assert artifact["rating_model_ingest_pass"] is True
    assert artifact["summary"]["input_rating_record_count"] == 3
    assert artifact["summary"]["normalized_rating_count"] == 3
    assert artifact["summary"]["usable_for_margin_calculation_count"] == 3
