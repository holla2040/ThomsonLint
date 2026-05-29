from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "current_model_ingest.py"


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


def branch_current(value: Any = 0.25, *, branch_id: str = "br_v3p3_top_trace_group_000001", unit: str | None = None) -> dict[str, Any]:
    row = {
        "branch_id": branch_id,
        "basis": "manual_design_requirement",
        "confidence": 1.0,
        "evidence_refs": ["manual_current_model:line1"],
    }
    if unit is None:
        row["branch_current_a"] = value
    else:
        row["value"] = value
        row["unit"] = unit
    return row


def current_model_fixture() -> dict[str, Any]:
    return {
        "project": "TestProject",
        "branch_currents": [branch_current()],
        "rail_currents": [
            {
                "rail_name": "V3P3",
                "rail_current_a": 0.75,
                "basis": "manual_design_requirement",
                "confidence": 1.0,
                "evidence_refs": [],
            }
        ],
        "component_currents": [
            {
                "refdes": "U12",
                "rail_name": "V3P3",
                "typ_current_a": 0.12,
                "max_current_a": 0.35,
                "basis": "datasheet",
                "confidence": 0.9,
                "evidence_refs": ["datasheet:U12:p14"],
            }
        ],
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
        ],
    }


def manifest_item(
    category: str = "branch_current_unknown",
    target_id: str = "br_v3p3_top_trace_group_000001",
    *,
    affected_rails: list[str] | None = None,
    affected_branches: list[str] | None = None,
    affected_components: list[str] | None = None,
    group_id: str = "group_current_model_missing_v3p3",
) -> dict[str, Any]:
    return {
        "manifest_id": f"mdi_manifest_{category}_{target_id}",
        "source_missing_data_id": f"source_{category}_{target_id}",
        "category": category,
        "target_type": "branch",
        "target_id": target_id,
        "normalized_target": target_id,
        "affected_rails": affected_rails or ["V3P3"],
        "affected_branches": affected_branches or [target_id],
        "affected_components": affected_components or [],
        "blocks": ["copper_calculation", "voltage_drop_calculation"],
        "group_id": group_id,
    }


def manifest_fixture(items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "project": "TestProject",
        "manifest_items": items if items is not None else [manifest_item()],
        "groups": [],
        "warnings": [],
        "errors": [],
    }


def invoke(
    tmp_path: Path,
    current_model: dict[str, Any] | None = None,
    *,
    manifest: dict[str, Any] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    current_model_path = write_json(tmp_path / "current-model.json", current_model or current_model_fixture())
    out = tmp_path / "current-models-normalized.json"
    args = ["--project", "TestProject", "--current-model", str(current_model_path), "--out", str(out)]
    if manifest is not None:
        args.extend(["--missing-data-manifest", str(write_json(tmp_path / "manifest.json", manifest))])
    return run_ingest(*args), out


def only_normalized(artifact: dict[str, Any], record_type: str) -> dict[str, Any]:
    rows = [row for row in artifact["normalized_currents"] if row["record_type"] == record_type]
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


def test_missing_required_current_model_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_ingest("--project", "TestProject", "--current-model", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_malformed_current_model_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    out = tmp_path / "out.json"
    result = run_ingest("--project", "TestProject", "--current-model", str(bad), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "project",
        "generated_at_utc",
        "execution_pass",
        "current_model_ingest_pass",
        "schema_version",
        "source_artifacts",
        "normalized_currents",
        "rejected_currents",
        "unresolved_references",
        "summary",
        "errors",
        "warnings",
    }
    assert expected.issubset(artifact)


def test_cli_writes_valid_json_artifact(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    for value in all_values(artifact):
        if isinstance(value, float):
            assert math.isfinite(value)


def test_summary_counts_match_arrays(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    normalized = artifact["normalized_currents"]
    assert summary["normalized_count"] == len(normalized)
    assert summary["rejected_count"] == len(artifact["rejected_currents"])
    assert summary["branch_current_count"] == sum(1 for row in normalized if row["record_type"] == "branch_current")
    assert summary["rail_current_count"] == sum(1 for row in normalized if row["record_type"] == "rail_current")
    assert summary["component_current_count"] == sum(1 for row in normalized if row["record_type"] == "component_current")
    assert summary["rating_count"] == sum(1 for row in normalized if row["record_type"] == "rating")
    assert summary["directly_usable_branch_current_count"] == sum(1 for row in normalized if row["usable_for_calculation"])
    assert summary["human_review_count"] == sum(1 for row in normalized if row["human_review_needed"])
    assert summary["unresolved_reference_count"] == len(artifact["unresolved_references"])
    assert summary["error_count"] == len(artifact["errors"])
    assert summary["warning_count"] == len(artifact["warnings"])


def test_branch_current_normalizes_amp_value(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current(0.25)]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "branch_current")
    assert row["value"] == 0.25
    assert row["unit"] == "A"


def test_milliamp_current_normalizes_to_amp(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current(250, unit="mA")]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "branch_current")
    assert math.isclose(row["value"], 0.25, rel_tol=1e-12)


def test_microamp_current_normalizes_to_amp(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current(250000, unit="uA")]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "branch_current")
    assert math.isclose(row["value"], 0.25, rel_tol=1e-12)


def test_explicit_branch_current_is_usable_for_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current()]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "branch_current")
    assert row["usable_for_calculation"] is True


def test_rail_current_is_not_directly_branch_usable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"rail_currents": [{"rail_name": "V3P3", "rail_current_a": 0.75}]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "rail_current")
    assert row["usable_for_calculation"] is False
    assert row.get("branch_id") is None


def test_component_current_is_not_directly_branch_usable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"component_currents": [{"refdes": "U12", "rail_name": "V3P3", "typ_current_a": 0.12}]})

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "component_current")
    assert row["usable_for_calculation"] is False
    assert row.get("branch_id") is None


def test_rating_normalizes_but_does_not_create_margin_result(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"ratings": [current_model_fixture()["ratings"][0]]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = only_normalized(artifact, "rating")
    assert row["value"] == 2.0
    assert row["usable_for_calculation"] is False
    assert "calculation_results" not in artifact
    assert "margin_results" not in artifact


def test_negative_current_is_rejected(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current(-0.1)]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["normalized_currents"]
    assert artifact["rejected_currents"][0]["reason_code"] == "negative_current"


def test_missing_unit_is_rejected_or_unusable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [{"branch_id": "br_v3p3", "value": 250}]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["normalized_currents"] or artifact["normalized_currents"][0]["usable_for_calculation"] is False
    if artifact["rejected_currents"]:
        assert artifact["rejected_currents"][0]["reason_code"] in {"missing_value", "unsupported_unit"}


def test_unsupported_unit_is_rejected_or_unusable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current(0.25, unit="W")]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not artifact["normalized_currents"] or artifact["normalized_currents"][0]["usable_for_calculation"] is False
    if artifact["rejected_currents"]:
        assert artifact["rejected_currents"][0]["reason_code"] == "unsupported_unit"


def test_no_current_inference_from_rail_or_component_names(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        {
            "rail_currents": [{"rail_name": "br_v3p3_top_trace_group_000001", "rail_current_a": 0.75}],
            "component_currents": [{"refdes": "br_v3p3_top_trace_group_000001", "max_current_a": 0.35}],
        },
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not any(row["record_type"] == "branch_current" for row in artifact["normalized_currents"])
    assert artifact["summary"]["directly_usable_branch_current_count"] == 0
    assert all(row.get("branch_id") is None for row in artifact["normalized_currents"])


def test_manifest_linkage_for_branch_current_unknown(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"branch_currents": [branch_current()]}, manifest=manifest_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    row = only_normalized(read_json(out), "branch_current")
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_branch_current_unknown_br_v3p3_top_trace_group_000001"]
    assert row["missing_data_group_ids"] == ["group_current_model_missing_v3p3"]
    assert row["warnings"] == []


def test_unresolved_manifest_link_is_warning_not_failure(tmp_path: Path) -> None:
    manifest = manifest_fixture([manifest_item(target_id="br_other", affected_branches=["br_other"], affected_rails=["V1P8"])])
    result, out = invoke(tmp_path, {"branch_currents": [branch_current()]}, manifest=manifest)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["current_model_ingest_pass"] is True
    assert artifact["unresolved_references"]
    assert artifact["summary"]["warning_count"] == 1


def test_no_findings_or_pass_fail_judgments_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    raw_keys = "\n".join(key.lower() for key in all_keys(artifact))
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


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["project"] == "TestProject"
    assert artifact["execution_pass"] is True
    assert artifact["current_model_ingest_pass"] is True
    assert artifact["summary"]["input_record_count"] == 4
    assert artifact["summary"]["normalized_count"] == 5
    assert artifact["summary"]["branch_current_count"] == 1
    assert artifact["summary"]["rail_current_count"] == 1
    assert artifact["summary"]["component_current_count"] == 2
    assert artifact["summary"]["rating_count"] == 1
