from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_margin_calculate.py"
RESULT_SCHEMA = ROOT / "schemas" / "calculation_result_schema.json"


def run_margin(*args: str) -> subprocess.CompletedProcess[str]:
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


def allocation_record(branch_id: str = "br_f1_vin", current: float = 0.5, *, allocation_id: str = "alloc_f1_vin") -> dict[str, Any]:
    return {
        "allocation_id": allocation_id,
        "allocation_type": "explicit_branch_current",
        "branch_id": branch_id,
        "rail_name": "VIN",
        "allocated_current_a": current,
        "basis": "manual_design_requirement",
        "confidence": 0.9,
        "source_current_record_ids": ["cur_branch_f1"],
        "source_artifacts": [],
        "evidence_refs": ["manual_current:F1"],
        "missing_data_manifest_item_ids": [],
        "missing_data_group_ids": [],
        "assumptions": [],
        "warnings": [],
        "usable_for_calculation": True,
    }


def current_allocation_fixture(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "schema_version": "1.0",
        "allocation_records": records if records is not None else [allocation_record()],
        "unresolved_allocations": [],
        "passthrough_records": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def rating_record(
    *,
    rating_id: str = "rating_fuse_f1_hold",
    branch_id: str | None = "br_f1_vin",
    refdes: str | None = "F1",
    pin: str | None = None,
    target_type: str = "fuse",
    rating_name: str = "hold_current",
    value: float = 1.0,
    usable: bool = True,
    families: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "rating_id": rating_id,
        "source_record_id": f"source_{rating_id}",
        "target_type": target_type,
        "normalized_target_type": target_type,
        "refdes": refdes,
        "pin": pin,
        "rail_name": "VIN",
        "branch_id": branch_id,
        "net_name": "VIN",
        "rating_name": rating_name,
        "normalized_rating_name": rating_name,
        "value_a": value,
        "unit": "A",
        "original_value": value,
        "original_unit": "A",
        "original_rating_name": rating_name,
        "basis": "datasheet",
        "source": "current_model",
        "confidence": 0.8,
        "evidence_refs": ["datasheet:F1:p4"],
        "source_artifacts": [],
        "usable_for_margin_calculation": usable,
        "human_review_needed": False,
        "applies_to_calculation_families": families if families is not None else ["fuse_margin"],
        "missing_data_manifest_item_ids": [],
        "missing_data_group_ids": [],
        "warnings": [],
    }


def rating_models_fixture(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "schema_version": "1.0",
        "normalized_ratings": records if records is not None else [rating_record()],
        "rejected_ratings": [],
        "unresolved_rating_links": [],
        "summary": {},
        "errors": [],
        "warnings": [],
    }


def branch_topology_fixture(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "branches": rows if rows is not None else [{"branch_id": "br_f1_vin", "refdes": "F1", "role_subtype": "fuse", "rail_name": "VIN"}],
    }


def role_resolution_fixture(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "component_roles": rows if rows is not None else [{"refdes": "F1", "role": "pass_through", "role_subtype": "fuse", "branch_ids": ["br_f1_vin"]}],
    }


def manifest_item(
    category: str,
    target_id: str,
    *,
    affected_branches: list[str] | None = None,
    affected_components: list[str] | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    return {
        "manifest_id": f"mdi_manifest_{category}_{target_id}",
        "source_missing_data_id": f"source_{category}_{target_id}",
        "category": category,
        "target_type": "branch",
        "target_id": target_id,
        "normalized_target": target_id,
        "affected_rails": ["VIN"],
        "affected_branches": affected_branches or [target_id],
        "affected_components": affected_components or [],
        "blocks": ["current_allocation", "thermal_calculation", "fuse_margin"],
        "group_id": group_id or f"group_{category}_{target_id}",
        "resolution_path": "datasheet_extraction" if category == "rating_missing" else "deterministic_rule",
        "resolution_queue": "datasheet_extraction" if category == "rating_missing" else "deterministic_rule",
    }


def manifest_fixture(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "project": "TestProject",
        "schema_version": "1.0",
        "manifest_items": items if items is not None else [],
        "groups": [],
        "warnings": [],
        "errors": [],
    }


def invoke(
    tmp_path: Path,
    *,
    current_allocation: dict[str, Any] | None = None,
    rating_models: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
    role_resolution: dict[str, Any] | None = None,
    branch_topology: dict[str, Any] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    current_path = write_json(tmp_path / "current-allocation.json", current_allocation or current_allocation_fixture())
    rating_path = write_json(tmp_path / "rating-models.json", rating_models or rating_models_fixture())
    out = tmp_path / "topology-margin-calculations.json"
    args = ["--project", "TestProject", "--current-allocation", str(current_path), "--rating-models-normalized", str(rating_path), "--out", str(out)]
    if manifest is not None:
        args.extend(["--missing-data-manifest", str(write_json(tmp_path / "manifest.json", manifest))])
    if role_resolution is not None:
        args.extend(["--role-resolution", str(write_json(tmp_path / "role-resolution.json", role_resolution))])
    if branch_topology is not None:
        args.extend(["--branch-topology-enriched", str(write_json(tmp_path / "branch-topology.json", branch_topology))])
    return run_margin(*args), out


def result_for(artifact: dict[str, Any], target_id: str = "F1") -> dict[str, Any]:
    rows = [row for row in artifact["calculation_results"] if row["target_id"] == target_id]
    assert len(rows) == 1
    return rows[0]


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


def test_missing_required_current_allocation_exits_2(tmp_path: Path) -> None:
    rating_path = write_json(tmp_path / "ratings.json", rating_models_fixture())
    out = tmp_path / "out.json"
    result = run_margin("--project", "TestProject", "--current-allocation", str(tmp_path / "missing.json"), "--rating-models-normalized", str(rating_path), "--out", str(out))
    assert result.returncode == 2
    assert not out.exists()


def test_missing_required_rating_models_exits_2(tmp_path: Path) -> None:
    current_path = write_json(tmp_path / "current.json", current_allocation_fixture())
    out = tmp_path / "out.json"
    result = run_margin("--project", "TestProject", "--current-allocation", str(current_path), "--rating-models-normalized", str(tmp_path / "missing.json"), "--out", str(out))
    assert result.returncode == 2
    assert not out.exists()


def test_malformed_current_allocation_exits_2(tmp_path: Path) -> None:
    current_path = tmp_path / "bad-current.json"
    current_path.write_text("{not-json", encoding="utf-8")
    rating_path = write_json(tmp_path / "ratings.json", rating_models_fixture())
    result = run_margin("--project", "TestProject", "--current-allocation", str(current_path), "--rating-models-normalized", str(rating_path), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_malformed_rating_models_exits_2(tmp_path: Path) -> None:
    current_path = write_json(tmp_path / "current.json", current_allocation_fixture())
    rating_path = tmp_path / "bad-ratings.json"
    rating_path.write_text("{not-json", encoding="utf-8")
    result = run_margin("--project", "TestProject", "--current-allocation", str(current_path), "--rating-models-normalized", str(rating_path), "--out", str(tmp_path / "out.json"))
    assert result.returncode == 2


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "project",
        "generated_at_utc",
        "execution_pass",
        "topology_margin_calculation_pass",
        "schema_version",
        "source_artifacts",
        "calculation_results",
        "blocked_calculations",
        "unresolved_margin_inputs",
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
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating_record(), rating_record(rating_id="rating_trip", rating_name="trip_current")]))
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    results = artifact["calculation_results"]
    blocked = artifact["blocked_calculations"]
    unresolved = artifact["unresolved_margin_inputs"]
    assert summary["fuse_margin_result_count"] == len(results)
    assert summary["fuse_margin_calculated_count"] == sum(1 for row in results if row["status"] == "calculated")
    assert summary["fuse_margin_blocked_count"] == len(blocked)
    assert summary["unresolved_margin_input_count"] == len(unresolved)
    assert summary["error_count"] == len(artifact["errors"])


def test_fuse_margin_calculates_when_branch_rating_and_current_match(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["fuse_margin_a"]["value"], 0.5, rel_tol=1e-12)


def test_fuse_margin_calculates_utilization_ratio(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert math.isclose(result_for(read_json(out))["result"]["fuse_utilization_ratio"]["value"], 0.5, rel_tol=1e-12)


def test_negative_margin_is_numeric_result_not_finding(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([allocation_record(current=1.25)]), rating_models=rating_models_fixture([rating_record(value=1.0)]))
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = result_for(artifact)
    assert row["status"] == "calculated"
    assert row["result"]["fuse_margin_a"]["value"] < 0
    assert artifact["summary"]["negative_margin_numeric_result_count"] == 1
    assert "findings" not in artifact


def test_calculated_result_preserves_allocation_id_and_rating_id(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert "alloc_f1_vin" in row["input_refs"]
    assert "rating_fuse_f1_hold" in row["input_refs"]


def test_calculated_result_preserves_evidence_refs(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert "manual_current:F1" in row["evidence_refs"]
    assert "datasheet:F1:p4" in row["evidence_refs"]


def test_calculated_result_validates_against_calculation_result_schema(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    jsonschema.validate(result_for(read_json(out)), read_json(RESULT_SCHEMA))


def test_fuse_margin_blocks_when_current_missing(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([]), rating_models=rating_models_fixture([rating_record()]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["status"] == "blocked"
    assert "allocated_current_a" in {item["field"] for item in row["missing_inputs"]}


def test_fuse_margin_blocks_when_rating_missing(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        rating_models=rating_models_fixture([]),
        branch_topology=branch_topology_fixture(),
        role_resolution=role_resolution_fixture(),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out)["blocked_calculations"][0]
    assert "fuse_rating" in {item["field"] for item in row["missing_inputs"]}


def test_fuse_margin_blocks_when_rating_unusable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating_record(usable=False)]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["status"] == "blocked"
    assert "fuse_rating" in {item["field"] for item in row["missing_inputs"]}


def test_fuse_margin_blocks_when_rating_value_zero(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating_record(value=0.0)]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["status"] == "blocked"
    assert "rating_current_a" in {item["field"] for item in row["missing_inputs"]}


def test_trip_current_does_not_calculate_continuous_margin(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating_record(rating_name="trip_current")]))
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = result_for(artifact)
    assert row["status"] == "blocked"
    assert "trip_current_not_continuous_margin_basis" in row["warnings"]
    assert artifact["summary"]["trip_current_blocked_count"] == 1


def test_ambiguous_rating_to_branch_mapping_creates_unresolved_margin_input(tmp_path: Path) -> None:
    rating = rating_record(branch_id=None)
    topology = branch_topology_fixture([
        {"branch_id": "br_f1_a", "refdes": "F1", "role_subtype": "fuse"},
        {"branch_id": "br_f1_b", "refdes": "F1", "role_subtype": "fuse"},
    ])
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating]), branch_topology=topology)
    assert result.returncode == 0, result.stderr + result.stdout
    unresolved = read_json(out)["unresolved_margin_inputs"][0]
    assert unresolved["reason_code"] == "ambiguous_target_mapping"


def test_missing_rating_to_current_link_creates_unresolved_margin_input(tmp_path: Path) -> None:
    rating = rating_record(branch_id=None)
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["unresolved_margin_inputs"][0]["reason_code"] == "target_current_link_unknown"


def test_role_unknown_blocks_or_unresolves_when_role_confirmation_required(tmp_path: Path) -> None:
    rating = rating_record(target_type="pass_through_component", branch_id="br_f1_vin")
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating]))
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["status"] == "blocked"
    assert "fuse_rating" in {item["field"] for item in row["missing_inputs"]}


def test_does_not_infer_fuse_role_from_refdes_prefix(tmp_path: Path) -> None:
    rating = rating_record(target_type="component", branch_id=None, families=[])
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([rating]))
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["calculation_results"] == []
    assert artifact["unresolved_margin_inputs"] == []


def test_does_not_infer_rating_from_current_or_component_name(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["calculation_results"] == []


def test_does_not_infer_current_from_rating(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([]), rating_models=rating_models_fixture([rating_record()]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert result_for(read_json(out))["status"] == "blocked"


def test_no_findings_or_pass_fail_judgments_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    raw_keys = "\n".join(key.lower() for key in all_keys(read_json(out)))
    forbidden = ["finding_id", "issue_id", "violation", "compliance_pass", "compliance_fail", "margin_pass", "margin_fail", "pass_fail", "judgment"]
    assert not any(token in raw_keys for token in forbidden)


def test_no_severity_or_compliance_fields_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    raw_keys = "\n".join(key.lower() for key in all_keys(read_json(out)))
    assert "severity" not in raw_keys
    assert "compliance" not in raw_keys


def test_missing_rating_manifest_linkage_is_preserved_when_present(tmp_path: Path) -> None:
    manifest = manifest_fixture([manifest_item("rating_missing", "br_f1_vin", affected_branches=["br_f1_vin"], affected_components=["F1"])])
    result, out = invoke(tmp_path, rating_models=rating_models_fixture([]), branch_topology=branch_topology_fixture(), role_resolution=role_resolution_fixture(), manifest=manifest)
    assert result.returncode == 0, result.stderr + result.stdout
    row = read_json(out)["blocked_calculations"][0]
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_rating_missing_br_f1_vin"]
    assert row["missing_data_group_ids"] == ["group_rating_missing_br_f1_vin"]


def test_branch_current_unknown_manifest_linkage_is_preserved_when_current_missing(tmp_path: Path) -> None:
    manifest = manifest_fixture([manifest_item("branch_current_unknown", "br_f1_vin", affected_branches=["br_f1_vin"])])
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([]), rating_models=rating_models_fixture([rating_record()]), manifest=manifest)
    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out))
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_branch_current_unknown_br_f1_vin"]


def test_missing_manifest_link_is_warning_not_failure(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, manifest=manifest_fixture([manifest_item("current_model_missing", "other_branch", affected_branches=["other_branch"])]))
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["topology_margin_calculation_pass"] is True
    assert artifact["warnings"]


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_allocation=current_allocation_fixture([allocation_record("br_v3p3_fuse_f1", 0.25, allocation_id="alloc_testproject_f1")]),
        rating_models=rating_models_fixture([rating_record(rating_id="rating_testproject_f1", branch_id="br_v3p3_fuse_f1", refdes="F1", rating_name="hold_current", value=0.75)]),
        branch_topology=branch_topology_fixture([{"branch_id": "br_v3p3_fuse_f1", "refdes": "F1", "role_subtype": "fuse", "rail_name": "V3P3"}]),
        role_resolution=role_resolution_fixture([{"refdes": "F1", "role": "pass_through", "role_subtype": "fuse", "branch_ids": ["br_v3p3_fuse_f1"]}]),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"
    assert artifact["execution_pass"] is True
    assert artifact["topology_margin_calculation_pass"] is True
    assert artifact["summary"]["fuse_margin_calculated_count"] == 1
