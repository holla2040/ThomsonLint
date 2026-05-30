from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

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


def via_review_record(
    branch_id: str = "br_v3p3_via_cluster_000001",
    *,
    via_count: int | None = 1,
    diameter: float | None = 0.30,
    plating: float | None = 0.025,
    branch_type: str = "via_cluster",
    geometry_type: str = "via_cluster",
) -> dict:
    geometry: dict[str, Any] = {
        "geometry_type": geometry_type,
        "via_count": via_count,
        "finished_hole_diameter_mm": diameter,
        "via_barrel_plating_thickness_mm": plating,
        "barrel_length_mm": 1.6,
    }
    geometry = {key: value for key, value in geometry.items() if value is not None}
    return {
        "review_id": f"geo_{branch_id}",
        "branch_id": branch_id,
        "net_name": "V3P3",
        "topology_net_type": "power",
        "branch_type": branch_type,
        "target_type": geometry_type,
        "geometry_type": geometry_type,
        "layer": "THRU",
        "geometry": geometry,
        "stackup": {},
        "current_context": {
            "current_model_ref": None,
            "estimated_current_a": None,
            "current_basis": "unresolved",
            "current_known": False,
        },
        "review_status": "needs_current_model",
        "evidence": [f"ev_geo_{branch_id}_via"],
        "unresolved_flags": [],
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


def allocation_record(
    branch_id: str = "br_v3p3_top_trace_group_000001",
    current: Any = 0.25,
    *,
    allocation_id: str | None = None,
    allocation_type: str = "explicit_branch_current",
    usable: bool = True,
    source_current_record_ids: list[str] | None = None,
) -> dict:
    allocation_id = allocation_id or f"alloc_{allocation_type}_{branch_id}"
    return {
        "allocation_id": allocation_id,
        "allocation_type": allocation_type,
        "branch_id": branch_id,
        "rail_name": "V3P3",
        "net_name": "V3P3",
        "allocated_current_a": current,
        "current_type": "requirement",
        "basis": "manual_design_requirement",
        "confidence": 1.0,
        "source_current_record_ids": source_current_record_ids if source_current_record_ids is not None else ["cur_branch_v3p3"],
        "source_artifacts": [],
        "evidence_refs": ["allocation:evidence"],
        "missing_data_manifest_item_ids": [],
        "missing_data_group_ids": [],
        "assumptions": [
            {
                "id": "allocation_fixture",
                "description": "Fixture allocation assumption.",
                "basis": "explicit_current_records",
                "evidence_refs": ["allocation:evidence"],
                "confidence": 0.9,
            }
        ],
        "warnings": [],
        "usable_for_calculation": usable,
    }


def unresolved_allocation(
    branch_id: str = "br_v3p3_top_trace_group_000001",
    *,
    reason_code: str = "missing_current_model",
    rail_name: str = "V3P3",
) -> dict:
    return {
        "unresolved_id": f"unres_{reason_code}_{branch_id}",
        "reason_code": reason_code,
        "target_type": "branch",
        "branch_id": branch_id,
        "rail_name": rail_name,
        "refdes": None,
        "source_current_record_ids": [],
        "missing_inputs": [{"field": "branch_current_a", "reason": "missing", "required_for": ["current_allocation"]}],
        "blocked_by_categories": ["branch_current_unknown"],
        "blocked_by_calculations": ["current_allocation", "voltage_drop_calculation", "thermal_calculation"],
        "missing_data_manifest_item_ids": [f"mdi_manifest_branch_current_unknown_v3p3_{branch_id}"],
        "missing_data_group_ids": ["group_current_model_missing_v3p3"],
        "resolution_path": "datasheet_extraction",
        "resolution_queue": "datasheet_extraction",
        "human_review_needed": True,
        "detail": "Fixture unresolved allocation.",
        "source_artifacts": [],
        "evidence_refs": ["unresolved:evidence"],
    }


def current_allocation_fixture(
    allocations: list[dict] | None = None,
    unresolved: list[dict] | None = None,
) -> dict:
    allocation_rows = allocations if allocations is not None else [allocation_record()]
    unresolved_rows = unresolved if unresolved is not None else []
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "execution_pass": True,
        "topology_current_allocation_pass": True,
        "source_artifacts": [],
        "allocation_records": allocation_rows,
        "unresolved_allocations": unresolved_rows,
        "passthrough_records": [],
        "summary": {
            "allocation_record_count": len(allocation_rows),
            "unresolved_allocation_count": len(unresolved_rows),
        },
        "errors": [],
        "warnings": [],
    }


def invoke(
    tmp_path: Path,
    *,
    review: dict | None = None,
    readiness: dict | None = None,
    manifest: dict | None = None,
    current_model: dict | None = None,
    current_allocation: dict | None = None,
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
    if current_allocation is not None:
        args.extend(["--current-allocation", str(write_json(tmp_path / "current-allocation.json", current_allocation))])
    if extra:
        args.extend(extra)
    return run_calculator(*args), out


def result_for(artifact: dict, family: str, branch_id: str = "br_v3p3_top_trace_group_000001") -> dict:
    return [
        row for row in artifact["calculation_results"]
        if row["calculation_family"] == family and row["target_id"] == branch_id
    ][0]


def all_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(all_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(all_values(child))
    return values


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


def test_current_allocation_cli_argument_is_supported(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["summary"]["current_allocation_source_count"] == 1


def test_voltage_drop_uses_allocated_branch_current(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture(), extra=["--copper-resistivity-ohm-m", "1.7e-8"])

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    resistance = result_for(artifact, "trace_resistance")["result"]["trace_resistance"]["value"]
    row = result_for(artifact, "voltage_drop")
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["voltage_drop"]["value"], 0.25 * resistance, rel_tol=1e-9)
    assert row["intermediate_values"]["current_source"] == "allocation"


def test_current_density_uses_allocated_branch_current(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["current_density"]["value"], 0.25 / 0.00875, rel_tol=1e-9)
    assert row["intermediate_values"]["current_source"] == "allocation"


def test_allocated_current_result_preserves_allocation_id(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(allocation_id="alloc_known_branch_current")
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert "alloc_known_branch_current" in row["input_refs"]
    assert any(source["artifact_type"] == "topology_current_allocation" and source["record_id"] == "alloc_known_branch_current" for source in row["source_artifacts"])


def test_allocated_current_result_preserves_source_current_record_ids(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(source_current_record_ids=["cur_u12", "cur_u13"])
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["source_current_record_ids"] == ["cur_u12", "cur_u13"]
    assert row["intermediate_values"]["source_current_record_ids"] == ["cur_u12", "cur_u13"]


def test_unusable_allocation_record_does_not_enable_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(usable=False)
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert result_for(artifact, "voltage_drop")["status"] == "blocked"
    assert result_for(artifact, "current_density")["status"] == "blocked"


def test_unresolved_allocation_blocks_voltage_drop_with_manifest_linkage(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([], [unresolved_allocation()]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["status"] == "blocked"
    assert "allocated_current_a" in {item["field"] for item in row["missing_inputs"]}
    assert row["missing_data_manifest_item_ids"] == ["mdi_manifest_branch_current_unknown_v3p3_br_v3p3_top_trace_group_000001"]
    assert row["missing_data_group_ids"] == ["group_current_model_missing_v3p3"]
    assert row["resolution_path"] == "datasheet_extraction"


def test_unresolved_allocation_blocks_current_density_with_manifest_linkage(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([], [unresolved_allocation()]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "blocked"
    assert "branch_current_unknown" in row["blocked_by_categories"]
    assert "current_allocation" in row["blocked_by_calculations"]
    assert row["human_review_needed"] is True


def test_missing_allocated_current_is_not_zero(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(current=None)
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert result_for(artifact, "voltage_drop")["status"] == "blocked"
    assert result_for(artifact, "current_density")["status"] == "blocked"
    assert not any(
        row.get("intermediate_values", {}).get("branch_current_a", {}).get("value") == 0
        for row in artifact["calculation_results"]
        if row["calculation_family"] in {"voltage_drop", "current_density"}
    )


def test_allocation_artifact_does_not_infer_from_rail_name(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(branch_id="br_other", current=0.25)
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert result_for(artifact, "voltage_drop")["status"] == "blocked"
    assert result_for(artifact, "current_density")["status"] == "blocked"


def test_legacy_current_model_still_works_when_no_allocation_artifact(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_model=current_model_fixture(current=0.25))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["status"] == "calculated"
    assert row["intermediate_values"]["current_source"] == "legacy"


def test_current_allocation_preferred_over_legacy_current_model_when_both_present_and_matching(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_model=current_model_fixture(current=0.25),
        current_allocation=current_allocation_fixture([allocation_record(current=0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["status"] == "calculated"
    assert row["intermediate_values"]["current_source"] == "allocation"
    assert any(source["artifact_type"] == "manual" for source in row["source_artifacts"])


def test_current_source_conflict_blocks_or_warns_when_allocation_and_legacy_differ(tmp_path: Path) -> None:
    result, out = invoke(
        tmp_path,
        current_model=current_model_fixture(current=0.5),
        current_allocation=current_allocation_fixture([allocation_record(current=0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "voltage_drop")
    assert row["status"] == "blocked"
    assert any(item["field"] == "current_source_conflict" for item in row["missing_inputs"])
    assert any("current_source_conflict" in warning for warning in row["warnings"])


def test_multiple_allocations_for_same_branch_conflict_when_not_deduplicable(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(current=0.25, allocation_id="alloc_a", source_current_record_ids=["cur_a"]),
        allocation_record(current=0.30, allocation_id="alloc_b", source_current_record_ids=["cur_b"]),
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "blocked"
    assert any(item["field"] == "current_source_conflict" for item in row["missing_inputs"])


def test_deterministic_branch_sum_allocation_is_not_double_counted(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record(current=0.30, allocation_id="alloc_sum", allocation_type="deterministic_branch_sum", source_current_record_ids=["cur_u12", "cur_u13"]),
        allocation_record(current=0.12, allocation_id="alloc_u12", allocation_type="explicit_branch_current", source_current_record_ids=["cur_u12"]),
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "current_density")
    assert row["status"] == "calculated"
    assert math.isclose(row["intermediate_values"]["branch_current_a"]["value"], 0.30, rel_tol=1e-12)


def test_summary_counts_include_current_allocation_usage(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    summary = read_json(out)["summary"]
    assert summary["current_allocation_source_count"] == 1
    assert summary["allocated_current_used_count"] == 2
    assert summary["legacy_current_model_used_count"] == 0
    assert summary["current_source_conflict_count"] == 0


def test_output_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        if isinstance(value, float):
            assert math.isfinite(value)


def test_manual_testproject_shaped_minimal_fixture_with_current_allocation_works(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, current_allocation=current_allocation_fixture([
        allocation_record("br_v3p3_top_trace_group_000001", 0.25, allocation_type="deterministic_branch_sum", source_current_record_ids=["cur_u12"])
    ]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["topology_copper_calculation_pass"] is True
    assert result_for(artifact, "voltage_drop")["status"] == "calculated"
    assert result_for(artifact, "current_density")["status"] == "calculated"


def test_via_current_density_calculates_for_single_via_with_explicit_geometry_and_current(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, branch_type="via", geometry_type="via", via_count=None)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    expected_area = math.pi * 0.30 * 0.025
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["via_current_density"]["value"], 0.25 / expected_area, rel_tol=1e-9)
    assert row["intermediate_values"]["via_count"]["value"] == 1.0


def test_via_current_density_calculates_for_explicit_via_cluster_total_area(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=4)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.8)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    expected_area = math.pi * 0.30 * 0.025 * 4
    assert row["status"] == "calculated"
    assert math.isclose(row["result"]["via_current_density"]["value"], 0.8 / expected_area, rel_tol=1e-9)
    assert math.isclose(row["intermediate_values"]["current_per_via_a"]["value"], 0.2, rel_tol=1e-12)
    assert any(item["id"] == "parallel_via_barrel_area" for item in row["assumptions"])


def test_via_current_density_uses_allocated_current_from_pr20(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=2)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.4, allocation_id="alloc_via_current")]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "calculated"
    assert row["intermediate_values"]["current_source"] == "allocation"
    assert "alloc_via_current" in row["input_refs"]


def test_via_current_density_legacy_current_model_still_works_without_allocation(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=2)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_model=current_model_fixture(branch_id, 0.4),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "calculated"
    assert row["intermediate_values"]["current_source"] == "legacy"


def test_via_current_density_blocks_when_current_missing(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=2)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        manifest=manifest_fixture([manifest_item("branch_current_unknown", branch_id, branch_id=branch_id)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert "branch_current_a" in {item["field"] for item in row["missing_inputs"]}


def test_via_current_density_blocks_when_plating_thickness_missing(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, plating=None)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert "via_barrel_plating_thickness_mm" in {item["field"] for item in row["missing_inputs"]}


def test_via_current_density_blocks_when_diameter_missing(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, diameter=None)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert "finished_hole_diameter_mm" in {item["field"] for item in row["missing_inputs"]}


def test_via_current_density_blocks_when_via_count_missing_for_cluster(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=None)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert "via_count" in {item["field"] for item in row["missing_inputs"]}


def test_via_current_density_does_not_infer_via_count_from_branch_name(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id, via_count=None, branch_type="via_cluster", geometry_type="via_cluster")]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "via_count" in {item["field"] for item in result_for(read_json(out), "via_current_density", branch_id)["missing_inputs"]}


def test_via_current_density_does_not_assume_plating_thickness(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    record = via_review_record(branch_id, plating=None)
    record["stackup"] = {"copper_thickness": 0.035, "copper_thickness_unit": "mm"}
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([record]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert "via_barrel_plating_thickness_mm" in {item["field"] for item in row["missing_inputs"]}


def test_via_current_density_preserves_allocation_id_and_source_current_record_ids(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25, allocation_id="alloc_via", source_current_record_ids=["cur_via_source"])]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert "alloc_via" in row["input_refs"]
    assert row["source_current_record_ids"] == ["cur_via_source"]


def test_via_current_density_preserves_manifest_linkage_for_blocked_current(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        manifest=manifest_fixture([]),
        current_allocation=current_allocation_fixture([], [unresolved_allocation(branch_id)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    row = result_for(read_json(out), "via_current_density", branch_id)
    assert row["status"] == "blocked"
    assert row["missing_data_manifest_item_ids"] == [f"mdi_manifest_branch_current_unknown_v3p3_{branch_id}"]
    assert row["missing_data_group_ids"] == ["group_current_model_missing_v3p3"]


def test_via_current_density_result_validates_against_calculation_result_schema(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    jsonschema.validate(result_for(read_json(out), "via_current_density", branch_id), read_json(RESULT_SCHEMA))


def test_via_current_density_json_has_no_nan_or_infinity(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    for value in all_values(read_json(out)):
        if isinstance(value, float):
            assert math.isfinite(value)


def test_via_current_density_summary_counts_match_results(tmp_path: Path) -> None:
    calculated_id = "br_v3p3_via_cluster_000001"
    blocked_id = "br_v3p3_via_cluster_000002"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([
            via_review_record(calculated_id),
            via_review_record(blocked_id, plating=None),
        ]),
        readiness=readiness_fixture([readiness_branch(calculated_id), readiness_branch(blocked_id)]),
        current_allocation=current_allocation_fixture([
            allocation_record(calculated_id, 0.25),
            allocation_record(blocked_id, 0.25),
        ]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    via_results = [row for row in artifact["calculation_results"] if row["calculation_family"] == "via_current_density"]
    assert artifact["summary"]["via_current_density_calculated_count"] == sum(1 for row in via_results if row["status"] == "calculated")
    assert artifact["summary"]["via_current_density_blocked_count"] == sum(1 for row in via_results if row["status"] == "blocked")
    assert artifact["summary"]["missing_via_plating_blocked_count"] == 1


def test_no_findings_or_pass_fail_judgments_are_emitted_after_via_density_addition(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([via_review_record(branch_id)]),
        readiness=readiness_fixture([readiness_branch(branch_id)]),
        current_allocation=current_allocation_fixture([allocation_record(branch_id, 0.25)]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    raw = out.read_text(encoding="utf-8").lower()
    forbidden = ["finding_id", "issue_id", "compliance_pass", "compliance_fail", "margin_pass", "margin_fail"]
    assert not any(token in raw for token in forbidden)


def test_manual_testproject_shaped_minimal_fixture_with_via_current_density_works(tmp_path: Path) -> None:
    branch_id = "br_v3p3_via_cluster_000001"
    result, out = invoke(
        tmp_path,
        review=geometry_review_fixture([
            review_record("br_v3p3_top_trace_group_000001"),
            via_review_record(branch_id, via_count=3),
        ]),
        readiness=readiness_fixture([
            readiness_branch("br_v3p3_top_trace_group_000001"),
            readiness_branch(branch_id),
        ]),
        current_allocation=current_allocation_fixture([
            allocation_record("br_v3p3_top_trace_group_000001", 0.25),
            allocation_record(branch_id, 0.30, allocation_id="alloc_testproject_vias"),
        ]),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["topology_copper_calculation_pass"] is True
    assert result_for(artifact, "via_current_density", branch_id)["status"] == "calculated"


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
    result, out = invoke(tmp_path, current_model=current_model_fixture(), current_allocation=current_allocation_fixture())

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
