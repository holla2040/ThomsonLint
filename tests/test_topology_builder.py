from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_builder.py"
SCHEMA = ROOT / "schemas" / "topology_map_schema.json"


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


def minimal_schematic(net_name: str = "3V3") -> dict:
    return {
        "components": [{"refdes": "U1", "part_number": "STM32F407VGT6"}],
        "nets": [{"name": net_name, "nodes": [{"refdes": "U1", "pin_number": "1", "pin_name": "VDD"}]}],
    }


def part_info_index(path: str = "exports/part_info/stm32f407vgt6.json") -> dict:
    return {
        "schema_version": "1.0",
        "project": "test",
        "mpns": {
            "stm32f407vgt6": {
                "normalized_mpn": "stm32f407vgt6",
                "ambiguous": False,
                "files": [
                    {
                        "file": path,
                        "mpn": "STM32F407VGT6",
                        "manufacturer": "STMicroelectronics",
                        "normalized_mpn": "stm32f407vgt6",
                        "component_category": "mcu",
                        "confidence_overall": 0.7,
                    }
                ],
                "bom_rows": [],
                "refdes": ["U1"],
            }
        },
        "refdes": {
            "U1": {
                "refdes": "U1",
                "mpn": "STM32F407VGT6",
                "manufacturer": "STMicroelectronics",
                "normalized_mpn": "stm32f407vgt6",
                "part_info_file": path,
                "component_category": "mcu",
                "confidence_overall": 0.7,
                "human_review_needed": False,
            }
        },
    }


def converter_part_info_index(path: str = "exports/part_info/grm155r71h104ke14d.json") -> dict:
    return {
        "schema_version": "1.0",
        "project": "test",
        "mpns": {
            "grm155r71h104ke14d": {
                "normalized_mpn": "grm155r71h104ke14d",
                "ambiguous": False,
                "files": [
                    {
                        "file": path,
                        "mpn": "GRM155R71H104KE14D",
                        "manufacturer": "Murata",
                        "normalized_mpn": "grm155r71h104ke14d",
                        "component_category": "capacitor",
                        "confidence_overall": 0.9,
                    }
                ],
                "bom_rows": [],
                "refdes": [],
            }
        },
        "refdes": {},
    }


def converter_schematic(node_count_mismatch: bool = False) -> dict:
    """Synthetic pads-v1 schematic export shaped like ThomsonLint converter output."""
    components = [
        {
            "refdes": "C40",
            "value": "0.1UF",
            "footprint": "C0402",
            "bom": {
                "description": "CAP_CER_0.1UF_50V_10%_X7R_0402",
                "manufacturer": "Murata",
                "mpn": "GRM155R71H104KE14D",
                "quantity": "14",
                "dnp": None,
            },
            "part_number": "GRM155R71H104KE14D",
        }
    ]
    components.extend(
        {
            "refdes": f"U{i}",
            "value": "IC",
            "footprint": "QFN",
            "bom": {
                "description": f"Synthetic IC {i}",
                "manufacturer": "ExampleSemi",
                "mpn": f"EXAMPLE-U{i}",
                "quantity": "1",
                "dnp": None,
            },
            "part_number": f"EXAMPLE-U{i}",
        }
        for i in range(1, 85)
    )

    component_refdes = ["C40", *[f"U{i}" for i in range(1, 85)]]
    net_names = [
        "V24P0",
        "V3P3",
        "V5P0",
        "VCC",
        "VN24P0",
        "GND",
        "J3_LASER_GND",
        "P3_LASER_GND",
        "MOTION_CLK",
        *[f"SIG_{i:03d}" for i in range(1, 123)],
    ]
    nets = []
    pin_index = 1
    for net_index, net_name in enumerate(net_names):
        expected_nodes = 4 if net_index < 20 else 3
        nodes = []
        for offset in range(expected_nodes):
            refdes = component_refdes[(net_index + offset) % len(component_refdes)]
            nodes.append({"refdes": refdes, "pin_number": str(pin_index), "pin_name": None})
            pin_index += 1
        node_count = expected_nodes + 1 if node_count_mismatch and net_name == "V3P3" else expected_nodes
        nets.append({"name": net_name, "node_count": node_count, "nodes": nodes})

    return {
        "project_name": "TestProject",
        "source": {
            "project_root": "/tmp/TestProject",
            "schematic_file": "example_pads.asc",
            "format": "pads_ascii",
            "detected_dialect": "pads_pcb_ascii_orcad_or_altium",
        },
        "parser_version": "pads-v1",
        "components": components,
        "nets": nets,
        "analysis": {
            "power_nets": ["V24P0", "V3P3", "V5P0", "VCC", "VN24P0"],
            "ground_nets": ["GND", "J3_LASER_GND", "P3_LASER_GND"],
            "clock_nets": ["MOTION_CLK", "XY2_CLK_POS"],
            "single_pin_nets": [],
        },
        "warnings": [],
        "extraction_counts": {
            "component_count": 85,
            "net_count": 131,
            "node_count": 413,
            "single_pin_net_count": 0,
            "power_net_count": 5,
            "ground_net_count": 3,
        },
        "bom_merge": {
            "components_with_bom_metadata": 85,
            "components_missing_bom_metadata": 0,
            "unmatched_bom_refdes": [],
            "value_mismatch_count": 0,
            "footprint_mismatch_count": 0,
        },
    }


def invoke(tmp_path: Path, schematic: dict, index: dict | None = None) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    schematic_path = write_json(tmp_path / "sch.json", schematic)
    index_path = write_json(tmp_path / "part_info_index.json", index or part_info_index())
    out = tmp_path / "topology-map.json"
    power = tmp_path / "power-topology.json"
    result = run_builder(
        "--project",
        "synthetic",
        "--examples",
        "--schematic",
        str(schematic_path),
        "--part-info-index",
        str(index_path),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
        "--power-out",
        str(power),
    )
    return result, out, power


def test_minimal_schematic_builds_one_net_device_and_pin(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, minimal_schematic())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    assert topology["graph_summary"]["net_count"] == 1
    assert topology["graph_summary"]["device_count"] == 1
    assert len(topology["pins"]) == 1
    assert topology["pins"][0]["pin_ref"] == "U1.1"


def test_ground_power_signal_net_classification(tmp_path: Path) -> None:
    schematic = {
        "components": [{"refdes": "U1", "part_number": "STM32F407VGT6"}],
        "nets": [
            {"name": "GND", "nodes": [{"refdes": "U1", "pin_number": "1", "pin_name": "VSS"}]},
            {"name": "3V3", "nodes": [{"refdes": "U1", "pin_number": "2", "pin_name": "VDD"}]},
            {"name": "UART_TX", "nodes": [{"refdes": "U1", "pin_number": "3", "pin_name": "TX"}]},
        ],
    }
    result, out, _ = invoke(tmp_path, schematic)

    assert result.returncode == 0, result.stderr + result.stdout
    by_name = {net["net_name"]: net["net_type"] for net in read_json(out)["nets"]}
    assert by_name["GND"] == "ground"
    assert by_name["3V3"] == "power"
    assert by_name["UART_TX"] == "signal"


def test_part_info_index_refdes_mapping_enriches_device(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, minimal_schematic())

    assert result.returncode == 0, result.stderr + result.stdout
    device = read_json(out)["devices"][0]
    assert device["mpn"] == "STM32F407VGT6"
    assert device["manufacturer"] == "STMicroelectronics"
    assert device["device_role"] == "sink"
    assert device["part_info_ref"].endswith("stm32f407vgt6.json")


def test_missing_part_info_creates_unresolved_without_crash(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, minimal_schematic(), index={"mpns": {}, "refdes": {}})

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    assert topology["validation"]["unresolved_items_present"] is True
    assert any(item["type"] == "missing_part_info" for item in topology["unresolved"])


def test_output_validates_against_topology_schema(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, minimal_schematic())

    assert result.returncode == 0, result.stderr + result.stdout
    try:
        import jsonschema
    except Exception as exc:  # pragma: no cover - environment dependent
        raise AssertionError(f"jsonschema unavailable: {exc}")
    schema = read_json(SCHEMA)
    topology = read_json(out)
    jsonschema.Draft7Validator.check_schema(schema)
    errors = list(jsonschema.Draft7Validator(schema).iter_errors(topology))
    assert errors == []


def test_examples_mode_runs_with_synthetic_paths_without_real_exports(tmp_path: Path) -> None:
    schematic_path = write_json(tmp_path / "sch.json", minimal_schematic())
    index_path = write_json(tmp_path / "part_info_index.json", part_info_index())
    out = tmp_path / "map.json"
    power = tmp_path / "power.json"

    result = run_builder(
        "--project",
        "synthetic",
        "--examples",
        "--schematic",
        str(schematic_path),
        "--board",
        str(tmp_path / "missing-board.json"),
        "--stackup",
        str(tmp_path / "missing-stackup.json"),
        "--bom",
        str(tmp_path / "missing-bom.json"),
        "--datasheet-manifest",
        str(tmp_path / "missing-manifest.jsonl"),
        "--part-info-index",
        str(index_path),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
        "--power-out",
        str(power),
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert out.exists()
    assert power.exists()


def test_missing_schematic_fails_without_examples(tmp_path: Path) -> None:
    out = tmp_path / "map.json"
    power = tmp_path / "power.json"

    result = run_builder(
        "--project",
        "synthetic",
        "--schematic",
        str(tmp_path / "missing-sch.json"),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
        "--power-out",
        str(power),
    )

    assert result.returncode == 2
    assert "missing schematic JSON" in result.stderr


def test_power_topology_summary_is_written(tmp_path: Path) -> None:
    result, _, power = invoke(tmp_path, minimal_schematic("3V3"))

    assert result.returncode == 0, result.stderr + result.stdout
    summary = read_json(power)
    assert summary["execution_pass"] is True
    assert summary["summary"]["net_count"] == 1
    assert summary["summary"]["device_count"] == 1
    assert summary["summary"]["pin_count"] == 1
    assert summary["summary"]["power_like_net_count"] == 1
    assert summary["power_like_nets"] == ["3V3"]


def test_converter_shaped_schematic_parses_real_export_counts(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    assert topology["graph_summary"]["device_count"] == 85
    assert topology["graph_summary"]["net_count"] == 131
    assert len(topology["pins"]) == 413


def test_converter_analysis_power_and_ground_nets_take_precedence(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    by_name = {net["net_name"]: net for net in read_json(out)["nets"]}
    for net_name in ["V3P3", "V5P0", "V24P0", "VCC", "VN24P0"]:
        assert by_name[net_name]["net_type"] == "power"
    for net_name in ["GND", "J3_LASER_GND", "P3_LASER_GND"]:
        assert by_name[net_name]["net_type"] == "ground"


def test_converter_clock_net_remains_signal_with_clock_flag(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    clock_net = {net["net_name"]: net for net in read_json(out)["nets"]}["MOTION_CLK"]
    assert clock_net["net_type"] == "signal"
    assert "clock_net" in clock_net["unresolved_flags"]


def test_converter_component_bom_mpn_fallback_matches_part_info_index(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    devices = {device["refdes"]: device for device in read_json(out)["devices"]}
    assert devices["C40"]["mpn"] == "GRM155R71H104KE14D"
    assert devices["C40"]["manufacturer"] == "Murata"
    assert devices["C40"]["part_info_ref"].endswith("grm155r71h104ke14d.json")


def test_converter_node_count_mismatch_warns_without_crash(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(node_count_mismatch=True), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    warnings = read_json(out)["validation"]["warnings"]
    assert any("node_count=5 does not match nodes length=4" in warning for warning in warnings)


def test_converter_output_validates_against_topology_schema(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    try:
        import jsonschema
    except Exception as exc:  # pragma: no cover - environment dependent
        raise AssertionError(f"jsonschema unavailable: {exc}")
    schema = read_json(SCHEMA)
    topology = read_json(out)
    jsonschema.Draft7Validator.check_schema(schema)
    errors = list(jsonschema.Draft7Validator(schema).iter_errors(topology))
    assert errors == []
