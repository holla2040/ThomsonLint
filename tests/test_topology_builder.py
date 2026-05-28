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
    files = [
        {
            "file": path,
            "mpn": "GRM155R71H104KE14D",
            "manufacturer": "Murata",
            "normalized_mpn": "grm155r71h104ke14d",
            "component_category": "capacitor",
            "confidence_overall": 0.9,
        },
        {
            "file": "exports/part_info/tps7a2033pdqnr.json",
            "mpn": "TPS7A2033PDQNR",
            "manufacturer": "Texas Instruments",
            "normalized_mpn": "tps7a2033pdqnr",
            "component_category": "ldo_regulator",
            "confidence_overall": 0.86,
        },
        {
            "file": "exports/part_info/sn65hvd230dr.json",
            "mpn": "SN65HVD230DR",
            "manufacturer": "Texas Instruments",
            "normalized_mpn": "sn65hvd230dr",
            "component_category": "transceiver",
            "confidence_overall": 0.82,
        },
        {
            "file": "exports/part_info/0430450414.json",
            "mpn": "043045-0414",
            "manufacturer": "Molex",
            "normalized_mpn": "0430450414",
            "component_category": "connector",
            "confidence_overall": 0.78,
        },
    ]
    return {
        "schema_version": "1.0",
        "project": "test",
        "mpns": {
            record["normalized_mpn"]: {
                "normalized_mpn": record["normalized_mpn"],
                "ambiguous": False,
                "files": [record],
                "bom_rows": [],
                "refdes": [],
            }
            for record in files
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
        },
        {
            "refdes": "U50",
            "value": "3.3V LDO",
            "footprint": "X2SON",
            "bom": {
                "description": "LDO_REG_3V3",
                "manufacturer": "Texas Instruments",
                "mpn": "TPS7A2033PDQNR",
                "quantity": "1",
                "dnp": None,
            },
            "part_number": "TPS7A2033PDQNR",
        },
        {
            "refdes": "U45",
            "value": "CAN",
            "footprint": "SOIC8",
            "bom": {
                "description": "CAN_TRANSCEIVER",
                "manufacturer": "Texas Instruments",
                "mpn": "SN65HVD230DR",
                "quantity": "1",
                "dnp": None,
            },
            "part_number": "SN65HVD230DR",
        },
        {
            "refdes": "R50",
            "value": "0R",
            "footprint": "R0402",
            "bom": {
                "description": "ZERO_OHM_JUMPER",
                "manufacturer": None,
                "mpn": None,
                "quantity": "1",
                "dnp": True,
            },
            "part_number": None,
        },
        {
            "refdes": "P20",
            "value": "CONN",
            "footprint": "HDR_4",
            "bom": {
                "description": "POWER_CONNECTOR",
                "manufacturer": "Molex",
                "mpn": "043045-0414",
                "quantity": "1",
                "dnp": None,
            },
            "part_number": "043045-0414",
        },
    ]
    used_refdes = {"C40", "U50", "U45", "R50", "P20"}
    filler_refdes = [f"U{i}" for i in range(1, 83) if f"U{i}" not in used_refdes]
    components.extend(
        {
            "refdes": refdes,
            "value": "IC",
            "footprint": "QFN",
            "bom": {
                "description": f"Synthetic IC {refdes}",
                "manufacturer": "ExampleSemi",
                "mpn": f"EXAMPLE-{refdes}",
                "quantity": "1",
                "dnp": None,
            },
            "part_number": f"EXAMPLE-{refdes}",
        }
        for refdes in filler_refdes
    )

    component_refdes = [component["refdes"] for component in components]
    nets = [
        {"name": "V24P0", "node_count": 1, "nodes": [{"refdes": "P20", "pin_number": "1", "pin_name": "VIN+"}]},
        {
            "name": "V3P3",
            "node_count": 4 if node_count_mismatch else 3,
            "nodes": [
                {"refdes": "U50", "pin_number": "2", "pin_name": "VOUT"},
                {"refdes": "U45", "pin_number": "1", "pin_name": "VDD"},
                {"refdes": "C40", "pin_number": "2", "pin_name": None},
            ],
        },
        {
            "name": "V5P0",
            "node_count": 3,
            "nodes": [
                {"refdes": "P20", "pin_number": "3", "pin_name": "5V"},
                {"refdes": "U50", "pin_number": "1", "pin_name": "VIN"},
                {"refdes": "R50", "pin_number": "2", "pin_name": None},
            ],
        },
        {"name": "VCC", "node_count": 1, "nodes": [{"refdes": "R50", "pin_number": "1", "pin_name": None}]},
        {"name": "VN24P0", "node_count": 1, "nodes": [{"refdes": "P20", "pin_number": "2", "pin_name": "VIN-"}]},
        {
            "name": "GND",
            "node_count": 4,
            "nodes": [
                {"refdes": "P20", "pin_number": "4", "pin_name": "GND"},
                {"refdes": "U50", "pin_number": "3", "pin_name": "GND"},
                {"refdes": "U45", "pin_number": "2", "pin_name": "GND"},
                {"refdes": "C40", "pin_number": "1", "pin_name": None},
            ],
        },
        {"name": "J3_LASER_GND", "node_count": 1, "nodes": [{"refdes": "P20", "pin_number": "5", "pin_name": "GND"}]},
        {"name": "P3_LASER_GND", "node_count": 1, "nodes": [{"refdes": "P20", "pin_number": "6", "pin_name": "GND"}]},
        {"name": "MOTION_CLK", "node_count": 1, "nodes": [{"refdes": "U45", "pin_number": "3", "pin_name": "CLK"}]},
    ]
    pin_index = 100
    for net_index in range(1, 123):
        expected_nodes = 4 if net_index <= 31 else 3
        nodes = []
        for offset in range(expected_nodes):
            refdes = component_refdes[(net_index + offset) % len(component_refdes)]
            nodes.append({"refdes": refdes, "pin_number": str(pin_index), "pin_name": None})
            pin_index += 1
        nets.append({"name": f"SIG_{net_index:03d}", "node_count": expected_nodes, "nodes": nodes})

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
    assert any("node_count=4 does not match nodes length=3" in warning for warning in warnings)


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


def test_power_rails_are_created_from_converter_power_nets(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    rail_names = {rail["net_name"] for rail in topology["power_rails"]}
    assert {"V24P0", "VN24P0", "V5P0", "V3P3", "VCC"} <= rail_names
    assert topology["graph_summary"]["power_rail_count"] == 5


def test_power_rail_voltage_parsing_and_unknown_voltage(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    rails = {rail["net_name"]: rail for rail in read_json(out)["power_rails"]}
    assert rails["V3P3"]["nominal_voltage_v"] == 3.3
    assert rails["V5P0"]["nominal_voltage_v"] == 5.0
    assert rails["V24P0"]["nominal_voltage_v"] == 24.0
    assert rails["VN24P0"]["nominal_voltage_v"] == -24.0
    assert rails["VCC"]["nominal_voltage_v"] is None
    assert "voltage_unknown" in rails["VCC"]["unresolved_flags"]


def test_voltage_and_rail_current_models_are_created_unresolved(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    voltage_models = {model["model_id"]: model for model in topology["voltage_models"]}
    current_models = {model["model_id"]: model for model in topology["current_models"]}
    assert voltage_models["vm_v3p3"]["nominal_voltage_v"] == 3.3
    assert voltage_models["vm_v3p3"]["basis"] == "net_name"
    rail_model = current_models["cm_v3p3"]
    assert rail_model["type"] == "rail_total"
    assert rail_model["basis"] == "unresolved"
    assert rail_model["nominal_current_a"] is None
    assert rail_model["max_current_a"] is None


def test_missing_source_creates_power_net_no_source_unresolved(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    assert any(item["type"] == "power_net_no_source" and item["net"] == "VCC" for item in topology["unresolved"])


def test_active_sink_without_current_creates_sink_current_unknown(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    topology = read_json(out)
    current_models = {model["model_id"]: model for model in topology["current_models"]}
    assert current_models["cm_u45_v3p3"]["type"] == "sink_load"
    assert current_models["cm_u45_v3p3"]["basis"] == "unresolved"
    assert any(item["type"] == "sink_current_unknown" and item["net"] == "V3P3" for item in topology["unresolved"])


def test_capacitors_are_not_counted_as_current_sinks(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    rails = {rail["net_name"]: rail for rail in read_json(out)["power_rails"]}
    assert "C40" not in rails["V3P3"]["sink_components"]


def test_dnp_pass_through_parts_are_not_counted_live(tmp_path: Path) -> None:
    result, out, _ = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    rails = {rail["net_name"]: rail for rail in read_json(out)["power_rails"]}
    assert "R50" not in rails["V5P0"]["pass_through_components"]
    assert "R50" not in rails["VCC"]["pass_through_components"]


def test_zero_ohm_resistor_classifies_as_pass_through_with_low_confidence(tmp_path: Path) -> None:
    schematic = {
        "components": [
            {
                "refdes": "R1",
                "value": "0R00",
                "bom": {"description": "zero ohm jumper", "dnp": None},
            }
        ],
        "nets": [{"name": "V5P0", "nodes": [{"refdes": "R1", "pin_number": "1", "pin_name": None}]}],
        "analysis": {"power_nets": ["V5P0"], "ground_nets": [], "clock_nets": []},
    }
    result, out, _ = invoke(tmp_path, schematic, index={"mpns": {}, "refdes": {}})

    assert result.returncode == 0, result.stderr + result.stdout
    device = read_json(out)["devices"][0]
    assert device["device_role"] == "pass_through"
    assert device["confidence"] < 0.5
    assert "heuristic_role" in device["unresolved"]


def test_power_summary_includes_power_topology_counts(tmp_path: Path) -> None:
    result, _, power = invoke(tmp_path, converter_schematic(), converter_part_info_index())

    assert result.returncode == 0, result.stderr + result.stdout
    summary = read_json(power)
    assert summary["summary"]["power_rail_count"] == 5
    assert summary["summary"]["source_component_count"] >= 2
    assert summary["summary"]["sink_component_count"] >= 2
    assert summary["summary"]["unresolved_current_model_count"] >= 5
    assert summary["summary"]["voltage_unknown_count"] == 1
    assert "VCC" in summary["unresolved_power_rails"]
