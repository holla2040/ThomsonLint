from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_copper_calculate.py"
RESULT_SCHEMA = ROOT / "schemas" / "calculation_result_schema.json"


def run_calculator(*args: str) -> subprocess.CompletedProcess[str]:
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def review_record(
    branch_id: str = "br_v3p3_top_trace_group_000001",
    *,
    width: float | None = 0.25,
    length: float | None = 50.0,
    thickness: float | None = 0.035,
    units: str = "mm",
) -> dict:
    return {
        "review_id": f"geo_{branch_id}",
        "branch_id": branch_id,
        "net_name": "V3P3",
        "topology_net_type": "power",
        "branch_type": "trace_group",
        "layer": "TOP",
        "geometry": {
            "units": units,
            "known_width_count": 1 if width is not None else 0,
            "min_width": width,
            "max_width": width,
            "total_length": length,
            "total_area": None,
            "bbox": None,
        },
        "stackup": {
            "primary_layer": "TOP",
            "is_copper_layer": True,
            "copper_thickness": thickness,
            "copper_thickness_unit": "mm",
        },
        "current_context": {
            "current_model_ref": None,
            "estimated_current_a": None,
            "current_basis": "unresolved",
            "current_known": False,
        },
        "review_status": "needs_current_model",
        "evidence": [f"ev_geo_{branch_id}_width", f"ev_geo_{branch_id}_length"],
        "unresolved_flags": ["current_unknown"] if thickness is not None else ["current_unknown", "missing_copper_thickness"],
        "warnings": [],
    }


def geometry_review_fixture(records: list[dict] | None = None) -> dict:
    records = records or [review_record()]
    evidence = []
    for record in records:
        for evidence_id in record["evidence"]:
            evidence.append({"evidence_id": evidence_id, "branch_id": record["branch_id"]})
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "review_records": records,
        "evidence_records": evidence,
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "geometry_review_pass": True,
    }


def readiness_branch(branch_id: str = "br_v3p3_top_trace_group_000001", *, current_known: bool = False, thickness: bool = True) -> dict:
    return {
        "branch_id": branch_id,
        "net_name": "V3P3",
        "rail_name": "V3P3",
        "branch_type": "trace_group",
        "is_power_branch": True,
        "is_ground_branch": False,
        "rail_role": "derived",
        "rail_voltage": 3.3,
        "current_allocation_readiness": {"status": "ready", "ready": True, "blocking_reasons": [], "required_missing_data_ids": [], "notes": []},
        "copper_calculation_readiness": {
            "status": "ready" if current_known and thickness else "blocked",
            "ready": current_known and thickness,
            "blocking_reasons": [] if current_known and thickness else ["branch_current_unknown"] + ([] if thickness else ["copper_thickness_missing"]),
            "required_missing_data_ids": [],
            "notes": [],
        },
        "available_context": {
            "has_rail_context": True,
            "has_source_context": True,
            "has_sink_context": True,
            "has_pass_through_context": False,
            "has_geometry_context": True,
            "has_current_model": current_known,
            "has_voltage": True,
            "has_layer": True,
            "has_copper_thickness": thickness,
            "has_width": True,
            "has_length_or_area": True,
        },
        "source_candidates": [],
        "sink_candidates": [],
        "pass_through_candidates": [],
        "rail_relationships": [],
        "evidence": [],
        "unresolved": [],
    }


def readiness_fixture(branches: list[dict] | None = None) -> dict:
    branches = branches or [readiness_branch()]
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "branch_readiness": branches,
        "rail_readiness": [],
        "missing_data_items": [],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "calculation_readiness_pass": True,
    }


def manifest_item(
    category: str,
    target_id: str,
    *,
    branch_id: str = "br_v3p3_top_trace_group_000001",
    group_id: str = "group_current_model_missing_v3p3",
    blocks: list[str] | None = None,
) -> dict:
    manifest_id = f"mdi_manifest_{category}_v3p3_{branch_id}"
    return {
        "manifest_id": manifest_id,
        "source_missing_data_id": f"source_{manifest_id}",
        "category": category,
        "scope": "branch",
        "target_type": "branch",
        "target_id": target_id,
        "normalized_target": "V3P3",
        "affected_rails": ["V3P3"],
        "affected_branches": [branch_id],
        "affected_components": ["U1"],
        "blocks": blocks or ["copper_calculation", "voltage_drop_calculation", "thermal_calculation"],
        "priority": "medium",
        "severity": "blocker",
        "resolution_path": "datasheet_extraction" if category == "branch_current_unknown" else "deterministic_rule",
        "resolution_reason": "fixture",
        "group_id": group_id,
        "packet_hint": {"packet_type": "current_model_completion", "max_items_per_packet": 5, "suggested_stage": "datasheet", "requires_artifacts": []},
        "evidence": [],
        "notes": "fixture",
    }


def manifest_fixture(items: list[dict] | None = None) -> dict:
    items = items if items is not None else [manifest_item("branch_current_unknown", "br_v3p3_top_trace_group_000001")]
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {"manifest_item_count": len(items)},
        "groups": [],
        "manifest_items": items,
        "resolution_queues": {},
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "missing_data_manifest_pass": True,
    }


def current_model_fixture(branch_id: str = "br_v3p3_top_trace_group_000001", current: float = 0.25) -> dict:
    return {
        "project": "unit",
        "branch_currents": [
            {
                "branch_id": branch_id,
                "branch_current_a": current,
                "basis": "manual_test_fixture",
                "confidence": 1.0,
                "evidence_refs": ["manual_current_fixture"],
            }
        ],
    }


def invoke(
    tmp_path: Path,
    *,
    review: dict | None = None,
    readiness: dict | None = None,
    manifest: dict | None = None,
    current_model: dict | None = None,
    extra: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    review_path = write_json(tmp_path / "geometry-review.json", review or geometry_review_fixture())
    readiness_path = write_json(tmp_path / "readiness.json", readiness or readiness_fixture())
    manifest_path = write_json(tmp_path / "manifest.json", manifest or manifest_fixture())
    out = tmp_path / "copper-calculations.json"
    args = [
        "--project",
        "unit",
        "--geometry-review",
        str(review_path),
        "--calculation-readiness",
        str(readiness_path),
        "--missing-data-manifest",
        str(manifest_path),
        "--out",
        str(out),
    ]
    if current_model is not None:
        args.extend(["--current-model", str(write_json(tmp_path / "current-model.json", current_model))])
    if extra:
        args.extend(extra)
    return run_calculator(*args), out


def result_for(artifact: dict, family: str, branch_id: str = "br_v3p3_top_trace_group_000001") -> dict:
    return [
        row for row in artifact["calculation_results"]
        if row["calculation_family"] == family and row["target_id"] == branch_id
    ][0]


def test_missing_required_inputs_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_calculator("--project", "unit", "--geometry-review", str(tmp_path / "missing.json"), "--calculation-readiness", str(tmp_path / "missing2.json"), "--missing-data-manifest", str(tmp_path / "missing3.json"), "--out", str(out))

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
        "topology_copper_calculation_pass",
        "schema_version",
        "summary",
        "source_artifacts",
        "calculation_results",
        "blocked_calculations",
        "errors",
        "warnings",
    }
    assert expected.issubset(artifact)


def test_trace_cross_section_calculates_when_width_and_thickness_known(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "trace_cross_section")
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["cross_section_area"]["value"], 0.00875, rel_tol=1e-9)


def test_trace_resistance_calculates_when_geometry_and_resistivity_known(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, extra=["--copper-resistivity-ohm-m", "1.7e-8"])

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "trace_resistance")
    expected = 1.7e-8 * 0.05 / (0.00875e-6)
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["trace_resistance"]["value"], expected, rel_tol=1e-9)


def test_voltage_drop_blocks_when_current_missing(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["status"] == "blocked"
    assert any(item["field"] == "branch_current_a" for item in row["missing_inputs"])


def test_current_density_blocks_when_current_missing(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "blocked"
    assert any(item["field"] == "branch_current_a" for item in row["missing_inputs"])


def test_voltage_drop_calculates_when_explicit_current_present(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model=current_model_fixture(current=0.25), extra=["--copper-resistivity-ohm-m", "1.7e-8"])

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    resistance = result_for(artifact, "trace_resistance")["result"]["trace_resistance"]["value"]
    row = result_for(artifact, "voltage_drop")
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["voltage_drop"]["value"], 0.25 * resistance, rel_tol=1e-9)
    assert "power_loss_w" in row["intermediate_values"]


def test_current_density_calculates_when_explicit_current_present(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model=current_model_fixture(current=0.25))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["current_density"]["value"], 0.25 / 0.00875, rel_tol=1e-9)


def test_copper_thickness_missing_blocks_cross_section_and_resistance(tmp_path: Path) -> None:
    branch_id = "br_v24p0_layer4_trace_group_000001"
    review = geometry_review_fixture([review_record(branch_id, thickness=None)])
    readiness = readiness_fixture([readiness_branch(branch_id, thickness=False)])
    manifest = manifest_fixture([manifest_item("copper_thickness_missing", branch_id, branch_id=branch_id, group_id="group_geometry_missing_v24p0")])
    result, out = invoke(tmp_path, review=review, readiness=readiness, manifest=manifest)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    cross = result_for(artifact, "trace_cross_section", branch_id)
    resistance = result_for(artifact, "trace_resistance", branch_id)
    assert cross["status"] == "blocked"
    assert resistance["status"] == "blocked"
    assert any(item["field"] == "copper_thickness" for item in cross["missing_inputs"])


def test_blocked_results_reference_manifest_items_when_available(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["blocked_by_manifest_items"]
    assert "branch_current_unknown" in row["blocked_by_categories"]
    assert row["missing_data_group_ids"] == ["group_current_model_missing_v3p3"]


def test_no_current_inference_from_rail_or_component_names(tmp_path: Path) -> None:
    branch_id = "br_v24p0_layer4_trace_group_000001"
    review = geometry_review_fixture([review_record(branch_id)])
    readiness = readiness_fixture([readiness_branch(branch_id)])
    manifest = manifest_fixture([manifest_item("branch_current_unknown", branch_id, branch_id=branch_id)])
    result, out = invoke(tmp_path, review=review, readiness=readiness, manifest=manifest)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert result_for(artifact, "voltage_drop", branch_id)["status"] == "blocked"
    assert result_for(artifact, "current_density", branch_id)["status"] == "blocked"


def test_results_validate_against_calculation_result_schema(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model=current_model_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    schema = read_json(RESULT_SCHEMA)
    for row in read_json(out)["calculation_results"]:
        jsonschema.validate(row, schema)


def test_no_findings_or_pass_fail_judgments_are_emitted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model=current_model_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    raw = out.read_text(encoding="utf-8").lower()
    forbidden = ["finding_id", "issue_id", "compliance_pass", "compliance_fail", "margin_pass", "margin_fail"]
    assert not any(token in raw for token in forbidden)


def test_malformed_input_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    readiness = write_json(tmp_path / "readiness.json", readiness_fixture())
    manifest = write_json(tmp_path / "manifest.json", manifest_fixture())
    out = tmp_path / "out.json"
    result = run_calculator("--project", "unit", "--geometry-review", str(bad), "--calculation-readiness", str(readiness), "--missing-data-manifest", str(manifest), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_manual_testproject_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    review = geometry_review_fixture([
        review_record("br_v3p3_top_trace_group_000001"),
        review_record("br_v24p0_layer4_trace_group_000001", width=0.5, length=25.0, thickness=0.035),
    ])
    readiness = readiness_fixture([
        readiness_branch("br_v3p3_top_trace_group_000001"),
        readiness_branch("br_v24p0_layer4_trace_group_000001"),
    ])
    manifest = manifest_fixture([
        manifest_item("branch_current_unknown", "br_v3p3_top_trace_group_000001", branch_id="br_v3p3_top_trace_group_000001"),
        manifest_item("branch_current_unknown", "br_v24p0_layer4_trace_group_000001", branch_id="br_v24p0_layer4_trace_group_000001", group_id="group_current_model_missing_v24p0"),
    ])
    result, out = invoke(tmp_path, review=review, readiness=readiness, manifest=manifest)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["topology_copper_calculation_pass"] is True
    assert artifact["summary"]["calculation_result_count"] == 8
    assert artifact["summary"]["missing_current_blocked_count"] == 4
