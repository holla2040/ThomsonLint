from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "branch_topology_build.py"


def run_builder(*args: str) -> subprocess.CompletedProcess[str]:
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


def topology_fixture(*, with_source_sink: bool = True) -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "sources": {
            "schematic": "sch.json",
            "board": "brd.json",
            "stackup": "stack.json",
            "bom": "bom.json",
            "part_info_index": "part_info_index.json",
            "datasheet_manifest": "manifest.jsonl",
        },
        "assumptions": [],
        "graph_summary": {"net_count": 4, "device_count": 1, "power_rail_count": 2, "branch_count": 0, "unresolved_count": 0},
        "nets": [
            {"net_name": "V3P3", "net_type": "power", "pin_refs": ["U1.1"], "confidence": 0.9},
            {"net_name": "V5P0", "net_type": "power", "pin_refs": [], "confidence": 0.9},
            {"net_name": "GND", "net_type": "ground", "pin_refs": ["U1.2"], "confidence": 0.9},
            {"net_name": "SIG_A", "net_type": "signal", "pin_refs": ["U1.3"], "confidence": 0.8},
        ],
        "power_rails": [
            {
                "net_name": "V3P3",
                "nominal_voltage_v": 3.3,
                "voltage_source": "derived_from_net_name",
                "source_components": ["J1"],
                "pass_through_components": [],
                "sink_components": ["U1"],
                "total_nominal_current_a": None,
                "total_max_current_a": None,
                "unresolved_current_a": None,
                "confidence": 0.6,
            },
            {
                "net_name": "V5P0",
                "nominal_voltage_v": 5.0,
                "voltage_source": "derived_from_net_name",
                "source_components": [],
                "pass_through_components": [],
                "sink_components": [],
                "total_nominal_current_a": None,
                "total_max_current_a": None,
                "unresolved_current_a": None,
                "confidence": 0.6,
            },
        ],
        "devices": [],
        "pins": [
            {"pin_ref": "U1.1", "refdes": "U1", "pin": "1", "pin_name": "VDD", "net_name": "V3P3", "role": "power", "confidence": 0.8},
            {"pin_ref": "U1.2", "refdes": "U1", "pin": "2", "pin_name": "GND", "net_name": "GND", "role": "ground", "confidence": 0.8},
            {"pin_ref": "U1.3", "refdes": "U1", "pin": "3", "pin_name": "SIG", "net_name": "SIG_A", "role": "signal", "confidence": 0.8},
        ],
        "pass_through_edges": [],
        "source_nodes": [
            {"node_id": "src_j1_v3p3", "source_type": "external_connector", "refdes": "J1", "pin_ref": None, "net_name": "V3P3", "confidence": 0.6}
        ]
        if with_source_sink
        else [],
        "sink_nodes": [
            {
                "node_id": "sink_u1_v3p3",
                "sink_type": "ic_supply",
                "refdes": "U1",
                "pin_ref": "U1.1",
                "net_name": "V3P3",
                "current_model_ref": "cm_v3p3",
                "confidence": 0.6,
            }
        ]
        if with_source_sink
        else [],
        "branches": [],
        "copper_geometry_links": [],
        "current_models": [
            {
                "model_id": "cm_v3p3",
                "target": "rail:V3P3",
                "type": "rail_total",
                "basis": "unresolved",
                "nominal_current_a": None,
                "max_current_a": None,
                "conservative_bound": False,
                "confidence": 0.3,
                "unresolved_flags": ["rail_current_unresolved"],
            }
        ],
        "voltage_models": [],
        "unresolved": [],
        "validation": {
            "execution_pass": True,
            "artifact_validation_pass": True,
            "topology_consistency_pass": True,
            "unresolved_items_present": False,
            "human_review_needed": False,
        },
    }


def copper_object(
    object_id: str,
    object_type: str,
    net_name: str,
    *,
    layer: str | None = "TOP",
    pin_ref: str | None = None,
    width: float | None = None,
    length: float | None = None,
    area: float | None = None,
    bbox: dict | None = None,
    available: bool = True,
    basis: str = "explicit_net",
    confidence: float = 1.0,
) -> dict:
    return {
        "object_id": object_id,
        "object_type": object_type,
        "net_name": net_name,
        "layer": layer,
        "refdes": None,
        "pin": None,
        "pin_ref": pin_ref,
        "geometry": {
            "available": available,
            "units": "INCH",
            "shape": "line" if object_type == "trace" else "polygon" if object_type in {"polygon", "plane"} else "circle",
            "bbox": bbox,
            "length": length,
            "width": width,
            "area": area,
        },
        "association_basis": basis,
        "confidence": confidence,
        "unresolved_flags": [],
    }


def copper_association_fixture(*, include_v5: bool = False) -> dict:
    objects = [
        copper_object("trace_v3p3_a", "trace", "V3P3", width=0.01, length=1.0, bbox={"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 0.1}),
        copper_object("trace_v3p3_b", "trace", "V3P3", width=0.02, length=2.0, bbox={"min_x": 1, "min_y": 0, "max_x": 3, "max_y": 0.2}),
        copper_object("via_v3p3", "via", "V3P3", layer="DRILL_1-2", width=0.015, bbox={"min_x": 0.4, "min_y": 0.4, "max_x": 0.6, "max_y": 0.6}),
        copper_object("pad_v3p3", "pad", "V3P3", pin_ref="U1.1", width=0.03, bbox={"min_x": 0.8, "min_y": 0.8, "max_x": 1.0, "max_y": 1.0}),
        copper_object("poly_gnd", "polygon", "GND", layer="L2", area=10.0, bbox={"min_x": -1, "min_y": -1, "max_x": 5, "max_y": 5}),
        copper_object("pad_sig", "pad", "SIG_A", pin_ref="U1.3", width=0.02),
    ]
    if include_v5:
        objects.append(copper_object("trace_v5p0", "trace", "V5P0", width=0.01, length=0.5))
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-28T00:00:00Z",
        "sources": {"board": "board.json", "stackup": "stack.json", "topology": "topology.json"},
        "summary": {"topology_net_count": 4, "copper_object_count": len(objects), "associated_copper_object_count": len(objects)},
        "layers": [],
        "net_associations": [],
        "copper_objects": objects,
        "unmatched_topology_nets": [],
        "unmatched_board_nets": [],
        "unassociated_copper_objects": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "association_pass": True,
        "human_review_needed": False,
    }


def invoke(tmp_path: Path, topology: dict | None = None, copper: dict | None = None, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    topology_path = write_json(tmp_path / "topology.json", topology or topology_fixture())
    copper_path = write_json(tmp_path / "copper.json", copper or copper_association_fixture())
    out = tmp_path / "branch.json"
    result = run_builder(
        "--project",
        "unit",
        "--topology",
        str(topology_path),
        "--copper-association",
        str(copper_path),
        "--out",
        str(out),
        *extra,
    )
    return result, out


def branches_by_type(artifact: dict, branch_type: str) -> list[dict]:
    return [branch for branch in artifact["branches"] if branch["branch_type"] == branch_type]


def test_explicit_trace_copper_on_power_net_creates_trace_group(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    traces = [branch for branch in branches_by_type(read_json(out), "trace_group") if branch["net_name"] == "V3P3"]
    assert len(traces) == 1
    assert traces[0]["object_count"] == 2


def test_polygon_plane_copper_on_ground_creates_plane_region(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    planes = [branch for branch in branches_by_type(read_json(out), "plane_region") if branch["net_name"] == "GND"]
    assert len(planes) == 1
    assert planes[0]["geometry_summary"]["has_plane_like_geometry"] is True


def test_vias_on_net_create_via_cluster(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    vias = [branch for branch in branches_by_type(read_json(out), "via_cluster") if branch["net_name"] == "V3P3"]
    assert len(vias) == 1
    assert vias[0]["geometry_summary"]["has_vias"] is True


def test_pads_on_net_create_pad_group(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    pads = [branch for branch in branches_by_type(read_json(out), "pad_group") if branch["net_name"] == "V3P3"]
    assert len(pads) == 1
    assert pads[0]["pin_refs"] == ["U1.1"]


def test_trace_via_pad_on_one_net_create_separate_groups(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    types = {branch["branch_type"] for branch in artifact["branches"] if branch["net_name"] == "V3P3"}
    assert {"trace_group", "via_cluster", "pad_group"} <= types


def test_net_branch_index_maps_net_to_branch_ids(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "V3P3" in artifact["net_branch_index"]
    assert all(branch_id.startswith("br_v3p3") for branch_id in artifact["net_branch_index"]["V3P3"])


def test_geometry_summary_aggregates_width_and_total_length(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    trace = [branch for branch in read_json(out)["branches"] if branch["net_name"] == "V3P3" and branch["branch_type"] == "trace_group"][0]
    summary = trace["geometry_summary"]
    assert summary["known_width_count"] == 2
    assert summary["min_width"] == 0.01
    assert summary["max_width"] == 0.02
    assert summary["total_length"] == 3.0


def test_geometry_summary_unions_bbox(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    trace = [branch for branch in read_json(out)["branches"] if branch["net_name"] == "V3P3" and branch["branch_type"] == "trace_group"][0]
    assert trace["geometry_summary"]["bbox"] == {"min_x": 0.0, "min_y": 0.0, "max_x": 3.0, "max_y": 0.2}


def test_power_branch_estimated_current_remains_null(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    branch = [branch for branch in read_json(out)["branches"] if branch["topology_net_type"] == "power"][0]
    assert branch["estimated_current_a"] is None


def test_power_branch_unresolved_current_flag(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    branch = [branch for branch in read_json(out)["branches"] if branch["net_name"] == "V3P3" and branch["branch_type"] == "trace_group"][0]
    assert branch["current_model_ref"] == "cm_v3p3"
    assert branch["current_basis"] == "unresolved"
    assert "branch_current_unknown" in branch["unresolved_flags"]


def test_power_branch_without_source_sink_gets_unresolved_flag(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, topology_fixture(with_source_sink=False))

    assert result.returncode == 0, result.stderr + result.stdout
    branch = [branch for branch in read_json(out)["branches"] if branch["net_name"] == "V3P3" and branch["branch_type"] == "trace_group"][0]
    assert "source_sink_not_resolved" in branch["unresolved_flags"]


def test_power_rail_with_no_copper_branch_creates_no_branch_unresolved(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert any(item["type"] == "no_branch" and item["net_name"] == "V5P0" for item in artifact["unresolved"])


def test_associated_copper_missing_layer_creates_unresolved(tmp_path: Path) -> None:
    copper = copper_association_fixture()
    copper["copper_objects"].append(copper_object("trace_no_layer", "trace", "V3P3", layer=None, width=0.01, length=1.0))
    result, out = invoke(tmp_path, copper=copper)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_layer" and item["object_id"] == "trace_no_layer" for item in read_json(out)["unresolved"])


def test_associated_copper_missing_geometry_creates_unresolved(tmp_path: Path) -> None:
    copper = copper_association_fixture()
    copper["copper_objects"].append(copper_object("trace_no_geom", "trace", "V3P3", available=False))
    result, out = invoke(tmp_path, copper=copper)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["type"] == "missing_geometry" and item["object_id"] == "trace_no_geom" for item in read_json(out)["unresolved"])


def test_non_strict_mode_passes_with_unresolved_items(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["branch_topology_pass"] is True
    assert artifact["unresolved"]


def test_strict_mode_fails_unresolved_power_branch_current(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, None, copper_association_fixture(include_v5=True), "--strict")

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["branch_topology_pass"] is False
    assert any("power branch current unresolved" in error for error in artifact["errors"])


def test_strict_mode_fails_power_rail_with_no_branch(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, None, copper_association_fixture(), "--strict")

    assert result.returncode == 1
    artifact = read_json(out)
    assert any("without branch candidates" in error for error in artifact["errors"])


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "branches",
        "net_branch_index",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "branch_topology_pass",
        "human_review_needed",
    }
    assert expected.issubset(artifact)


def test_exit_code_2_for_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "branch.json"
    result = run_builder(
        "--project",
        "unit",
        "--topology",
        str(tmp_path / "missing-topology.json"),
        "--copper-association",
        str(write_json(tmp_path / "copper.json", copper_association_fixture())),
        "--out",
        str(out),
    )

    assert result.returncode == 2
    assert not out.exists()


def test_converter_shaped_copper_association_fixture_works(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["branch_count"] >= 5
    assert artifact["summary"]["trace_branch_count"] >= 1
    assert artifact["summary"]["plane_branch_count"] >= 1
    assert artifact["summary"]["via_cluster_count"] >= 1
