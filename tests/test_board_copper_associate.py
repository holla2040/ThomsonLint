from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "board_copper_associate.py"


def run_associate(*args: str) -> subprocess.CompletedProcess[str]:
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


def topology_fixture() -> dict:
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
        "source_nodes": [],
        "sink_nodes": [],
        "branches": [],
        "copper_geometry_links": [],
        "current_models": [],
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


def stackup_fixture() -> dict:
    return {
        "project_name": "unit",
        "parser_version": "ipc2581-v1",
        "units": "INCH",
        "physical_stackup": [
            {"name": "SILK_TOP", "sequence": 1, "type": "Mask", "function": "SILKSCREEN", "material": "INK", "side": "TOP"},
            {"name": "TOP", "sequence": 2, "type": "Conductor", "function": "CONDUCTOR", "material": "COPPER", "side": "TOP", "copper_thickness": 0.0014},
            {"name": "L2", "sequence": 3, "type": "Plane", "function": "PLANE", "material": "COPPER", "side": "INTERNAL", "copper_thickness": 0.0012},
            {"name": "DOC", "sequence": 4, "type": "Document", "function": "DOCUMENT", "material": "INK", "side": "TOP"},
        ],
    }


def board_fixture() -> dict:
    return {
        "project_name": "unit",
        "units": "INCH",
        "parser_version": "ipc2581-v1",
        "nets": [{"name": "V3P3"}, {"name": "GND"}, {"name": "BOARD_ONLY"}],
        "routing_geometry": {
            "units": "INCH",
            "copper_routes": [
                {
                    "id": "route_v3p3",
                    "layer": "TOP",
                    "net": "V3P3",
                    "feature_domain": "copper",
                    "line_width": 0.01,
                    "line_width_units": "INCH",
                    "points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}],
                    "bbox": {"min_x": 0.0, "min_y": 0.0, "max_x": 1.0, "max_y": 0.0},
                    "length": 1.0,
                }
            ],
            "copper_polygons": [
                {
                    "id": "poly_gnd",
                    "layer": "L2",
                    "net": "GND",
                    "feature_domain": "copper",
                    "points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}],
                    "bbox": {"min_x": 0.0, "min_y": 0.0, "max_x": 1.0, "max_y": 1.0},
                }
            ],
            "copper_pads": [
                {
                    "id": "pad_sig",
                    "layer": "TOP",
                    "feature_domain": "copper",
                    "refdes": "U1",
                    "pin_number": "3",
                    "resolved_shape": "circle",
                    "resolved_diameter": 0.02,
                    "resolved_units": "INCH",
                }
            ],
        },
        "via_holes": [
            {"id": "via_v3p3", "net": "V3P3", "layer": "DRILL_1-2", "x": 0.5, "y": 0.5, "diameter": 0.01, "diameter_units": "INCH"}
        ],
    }


def invoke(tmp_path: Path, board: dict, stackup: dict | None = None, topology: dict | None = None, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    board_path = write_json(tmp_path / "board.json", board)
    stack_path = write_json(tmp_path / "stack.json", stackup or stackup_fixture())
    topology_path = write_json(tmp_path / "topology.json", topology or topology_fixture())
    out = tmp_path / "association.json"
    result = run_associate(
        "--project",
        "unit",
        "--board",
        str(board_path),
        "--stackup",
        str(stack_path),
        "--topology",
        str(topology_path),
        "--out",
        str(out),
        *extra,
    )
    return result, out


def association_by_net(artifact: dict) -> dict:
    return {row["net_name"]: row for row in artifact["net_associations"]}


def objects_by_id(artifact: dict) -> dict:
    return {row["object_id"]: row for row in artifact["copper_objects"]}


def test_minimal_explicit_net_trace_associates_to_topology_net(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "traces": [{"net": "V3P3", "layer": "TOP", "width": 0.01}]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert association_by_net(artifact)["V3P3"]["object_count"] == 1
    obj = artifact["copper_objects"][0]
    assert obj["object_type"] == "trace"
    assert obj["association_basis"] == "explicit_net"
    assert obj["confidence"] == 1.0


def test_explicit_net_via_associates_to_topology_net(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "via_holes": [{"net": "V3P3", "diameter": 0.01}]})

    assert result.returncode == 0, result.stderr + result.stdout
    obj = read_json(out)["copper_objects"][0]
    assert obj["object_type"] == "via"
    assert obj["net_name"] == "V3P3"


def test_explicit_net_pad_associates_to_topology_net(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "pads": [{"net": "GND", "layer": "TOP", "resolved_shape": "circle"}]})

    assert result.returncode == 0, result.stderr + result.stdout
    obj = read_json(out)["copper_objects"][0]
    assert obj["object_type"] == "pad"
    assert obj["net_name"] == "GND"


def test_pin_based_pad_association_uses_topology_pin_index(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "pads": [{"refdes": "U1", "pin_number": "1", "layer": "TOP"}]})

    assert result.returncode == 0, result.stderr + result.stdout
    obj = read_json(out)["copper_objects"][0]
    assert obj["net_name"] == "V3P3"
    assert obj["association_basis"] == "component_pin"
    assert obj["pin_ref"] == "U1.1"


def test_unknown_copper_object_remains_unassociated(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "traces": [{"layer": "TOP", "width": 0.01}]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["unassociated_copper_object_count"] == 1
    assert artifact["copper_objects"][0]["association_basis"] == "unknown"


def test_stackup_copper_layer_detection_for_conductor_and_plane(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    layers = {layer["layer_name"]: layer for layer in read_json(out)["layers"]}
    assert layers["TOP"]["is_copper"] is True
    assert layers["L2"]["is_copper"] is True


def test_mask_silkscreen_document_layers_are_not_copper(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    layers = {layer["layer_name"]: layer for layer in read_json(out)["layers"]}
    assert layers["SILK_TOP"]["is_copper"] is False
    assert layers["DOC"]["is_copper"] is False


def test_one_net_association_record_created_per_topology_net(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert len(artifact["net_associations"]) == len(topology_fixture()["nets"])


def test_unmatched_topology_nets_are_reported(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "traces": [{"net": "V3P3", "layer": "TOP"}], "nets": [{"name": "V3P3"}]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "V5P0" in artifact["unmatched_topology_nets"]


def test_unmatched_board_nets_are_reported(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "BOARD_ONLY" in artifact["unmatched_board_nets"]


def test_power_net_copper_object_count_is_computed(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["summary"]["power_net_copper_object_count"] == 2


def test_ground_net_copper_object_count_is_computed(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["summary"]["ground_net_copper_object_count"] == 1


def test_strict_mode_fails_when_power_rail_has_no_associated_copper(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "traces": [{"net": "V3P3", "layer": "TOP"}]}, None, None, "--strict")

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["association_pass"] is False
    assert any("power rail" in error for error in artifact["errors"])


def test_non_strict_does_not_fail_unmatched_nets(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, {"units": "INCH", "traces": [{"net": "BOARD_ONLY", "layer": "TOP"}]})

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["association_pass"] is True
    assert artifact["warnings"]


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "layers",
        "net_associations",
        "copper_objects",
        "unmatched_topology_nets",
        "unmatched_board_nets",
        "unassociated_copper_objects",
        "warnings",
        "errors",
        "execution_pass",
        "association_pass",
        "human_review_needed",
    }
    assert expected.issubset(artifact)


def test_exit_code_2_for_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "association.json"
    result = run_associate(
        "--project",
        "unit",
        "--board",
        str(tmp_path / "missing-board.json"),
        "--stackup",
        str(write_json(tmp_path / "stack.json", stackup_fixture())),
        "--topology",
        str(write_json(tmp_path / "topology.json", topology_fixture())),
        "--out",
        str(out),
    )

    assert result.returncode == 2
    assert not out.exists()


def test_converter_shaped_board_fixture_uses_routing_geometry_fields(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, board_fixture())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    by_id = objects_by_id(artifact)
    assert by_id["route_v3p3"]["object_type"] == "trace"
    assert by_id["poly_gnd"]["object_type"] in {"polygon", "plane"}
    assert by_id["pad_sig"]["net_name"] == "SIG_A"
    assert by_id["via_v3p3"]["object_type"] == "via"
