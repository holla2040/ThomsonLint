from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_role_resolve.py"


def run_resolver(*args: str) -> subprocess.CompletedProcess[str]:
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


def component(refdes: str, *, value: str = "", description: str = "", footprint: str = "PKG", mpn: str | None = None) -> dict:
    return {
        "refdes": refdes,
        "value": value,
        "footprint": footprint,
        "part_number": mpn,
        "bom": {"description": description, "mpn": mpn},
    }


def node(refdes: str, pin: str, pin_name: str | None) -> dict:
    return {"refdes": refdes, "pin_number": pin, "pin_name": pin_name}


def schematic_fixture(components: list[dict], nets: list[dict], *, power: list[str] | None = None, ground: list[str] | None = None, clock: list[str] | None = None) -> dict:
    return {
        "components": components,
        "nets": nets,
        "analysis": {
            "power_nets": power or ["V3P3", "VIN", "VOUT"],
            "ground_nets": ground or ["GND"],
            "clock_nets": clock or ["CLK"],
        },
    }


def net(name: str, nodes: list[dict]) -> dict:
    return {"name": name, "nodes": nodes}


def topology_fixture(schematic: dict) -> dict:
    nets = []
    for raw in schematic["nets"]:
        name = raw["name"]
        if name in schematic["analysis"].get("power_nets", []):
            net_type = "power"
        elif name in schematic["analysis"].get("ground_nets", []):
            net_type = "ground"
        else:
            net_type = "signal"
        nets.append({"net_name": name, "net_type": net_type, "pin_refs": []})
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "nets": nets,
        "power_rails": [{"net_name": item["net_name"]} for item in nets if item["net_type"] == "power"],
        "devices": [],
        "pins": [],
    }


def empty_index() -> dict:
    return {"schema_version": "1.0", "project": "unit", "mpns": {}, "refdes": {}}


def invoke(tmp_path: Path, schematic: dict, topology: dict | None = None, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    schematic_path = write_json(tmp_path / "schematic.json", schematic)
    topology_path = write_json(tmp_path / "topology.json", topology or topology_fixture(schematic))
    index_path = write_json(tmp_path / "part-info-index.json", empty_index())
    out = tmp_path / "roles.json"
    result = run_resolver(
        "--project",
        "unit",
        "--topology",
        str(topology_path),
        "--schematic",
        str(schematic_path),
        "--part-info-index",
        str(index_path),
        "--part-info-dir",
        str(tmp_path / "part_info"),
        "--out",
        str(out),
        *extra,
    )
    return result, out


def role_for(artifact: dict, refdes: str) -> dict:
    return {row["refdes"]: row for row in artifact["component_roles"]}[refdes]


def net_role_for(artifact: dict, net_name: str) -> dict:
    return {row["net_name"]: row for row in artifact["net_roles"]}[net_name]


def pin_roles_for(artifact: dict, refdes: str) -> dict[str, str]:
    return {
        str(row["pin_name"]): row["pin_role"]
        for row in artifact["pin_roles"]
        if row["refdes"] == refdes and row["pin_name"] is not None
    }


def test_connector_on_power_net_becomes_connector_power_input_or_io_source_candidate(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("J1", value="CONN", description="power connector")],
        [net("V3P3", [node("J1", "1", "VCC")]), net("GND", [node("J1", "2", "GND")])],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "J1")
    assert role["role"] == "source"
    assert role["role_subtype"] == "connector_power_input_or_io"


def test_connector_only_on_signal_nets_becomes_bidirectional_interface(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("J2", value="CONN")],
        [net("UART_TX", [node("J2", "1", "TX")]), net("UART_RX", [node("J2", "2", "RX")])],
        power=[],
        ground=[],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "J2")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "interface"


def test_battery_component_becomes_source_battery(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("BT1", value="coin cell")],
        [net("VBAT", [node("BT1", "1", "+")]), net("GND", [node("BT1", "2", "-")])],
        power=["VBAT"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "BT1")
    assert role["role"] == "source"
    assert role["role_subtype"] == "battery"


def test_regulator_with_vin_vout_gnd_pins_becomes_source_with_input_output_nets(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U1", value="Buck Regulator", description="switching regulator")],
        [
            net("VIN", [node("U1", "1", "VIN")]),
            net("VOUT", [node("U1", "2", "VOUT")]),
            net("GND", [node("U1", "3", "GND")]),
        ],
        power=["VIN", "VOUT"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "U1")
    assert role["role"] == "source"
    assert role["role_subtype"] == "buck_regulator"
    assert role["input_nets"] == ["VIN"]
    assert role["output_nets"] == ["VOUT"]


def test_ldo_description_keyword_is_recognized(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U2", value="3V3 LDO", description="LDO regulator")],
        [net("VIN", [node("U2", "1", "VIN")]), net("VOUT", [node("U2", "2", "VOUT")]), net("GND", [node("U2", "3", "GND")])],
        power=["VIN", "VOUT"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    assert role_for(read_json(out), "U2")["role_subtype"] == "ldo"


def test_buck_regulator_keyword_is_recognized(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U3", description="DC-DC buck converter")],
        [net("VIN", [node("U3", "1", "VIN")]), net("VOUT", [node("U3", "2", "VOUT")]), net("GND", [node("U3", "3", "GND")])],
        power=["VIN", "VOUT"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    assert role_for(read_json(out), "U3")["role_subtype"] == "buck_regulator"


def test_ic_with_vdd_gnd_pins_becomes_sink_ic_load(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U4", value="MCU")],
        [net("V3P3", [node("U4", "1", "VDD")]), net("GND", [node("U4", "2", "GND")])],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "U4")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "ic_load"


def test_decoupling_capacitor_between_power_and_ground_is_passive_decoupling_not_explicit_load(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("C1", value="0.1uF")],
        [net("V3P3", [node("C1", "1", None)]), net("GND", [node("C1", "2", None)])],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "C1")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "passive_decoupling"
    assert "not a load current model" in role["unresolved"]


def test_ferrite_bead_becomes_pass_through(tmp_path: Path) -> None:
    sch = schematic_fixture([component("FB1", description="ferrite bead")], [net("VIN", [node("FB1", "1", None)]), net("VOUT", [node("FB1", "2", None)])], power=["VIN", "VOUT"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "FB1")
    assert role["role"] == "pass_through"
    assert role["role_subtype"] == "ferrite_bead"


def test_fuse_becomes_pass_through(tmp_path: Path) -> None:
    sch = schematic_fixture([component("F1", description="polyfuse")], [net("VIN", [node("F1", "1", None)]), net("VOUT", [node("F1", "2", None)])], power=["VIN", "VOUT"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    assert role_for(read_json(out), "F1")["role_subtype"] == "fuse"


def test_zero_ohm_resistor_becomes_pass_through_zero_ohm_link(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R1", value="0R")], [net("VIN", [node("R1", "1", None)]), net("VOUT", [node("R1", "2", None)])], power=["VIN", "VOUT"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    assert role_for(read_json(out), "R1")["role_subtype"] == "zero_ohm_link"


def test_zero_ohm_value_variants_are_zero_ohm_links(tmp_path: Path) -> None:
    components = [
        component("R1", value="0R00"),
        component("R2", value="0R"),
        component("R3", value="0R0"),
        component("R4", value="0.0"),
        component("R5", value="DNP", description="DNP jumper link"),
    ]
    nets = []
    for idx in range(1, 6):
        nets.extend([
            net(f"VIN_{idx}", [node(f"R{idx}", "1", None)]),
            net(f"VOUT_{idx}", [node(f"R{idx}", "2", None)]),
        ])
    sch = schematic_fixture(components, nets, power=[f"VIN_{idx}" for idx in range(1, 6)] + [f"VOUT_{idx}" for idx in range(1, 6)])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    for idx in range(1, 6):
        role = role_for(artifact, f"R{idx}")
        assert role["role"] == "pass_through"
        assert role["role_subtype"] == "zero_ohm_link"


def test_nonzero_resistor_values_are_not_zero_ohm_links(tmp_path: Path) -> None:
    values = ["4K7", "5K1", "120R", "0R1", "0.1R"]
    components = [component(f"R{idx}", value=value) for idx, value in enumerate(values, 1)]
    nets = []
    for idx in range(1, len(values) + 1):
        nets.extend([
            net(f"VIN_{idx}", [node(f"R{idx}", "1", None)]),
            net(f"VOUT_{idx}", [node(f"R{idx}", "2", None)]),
        ])
    sch = schematic_fixture(components, nets, power=[f"VIN_{idx}" for idx in range(1, len(values) + 1)] + [f"VOUT_{idx}" for idx in range(1, len(values) + 1)])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    for idx, value in enumerate(values, 1):
        role = role_for(artifact, f"R{idx}")
        assert role["role_subtype"] != "zero_ohm_link", value
        assert role["role"] != "pass_through", value


def test_current_sense_resistor_becomes_pass_through_current_sense(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R2", value="0.005 ohm", description="current sense shunt")], [net("VIN", [node("R2", "1", None)]), net("VOUT", [node("R2", "2", None)])], power=["VIN", "VOUT"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    assert role_for(read_json(out), "R2")["role_subtype"] == "current_sense"


def test_test_point_on_signal_net_is_test_point_signal(tmp_path: Path) -> None:
    sch = schematic_fixture([component("TP1")], [net("SDA", [node("TP1", "1", "TP")])], power=[], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "TP1")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "test_point_signal"


def test_test_point_on_power_net_is_test_point_power_or_ground(tmp_path: Path) -> None:
    sch = schematic_fixture([component("TP2")], [net("V3P3", [node("TP2", "1", "TP")])], power=["V3P3"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "TP2")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "test_point_power_or_ground"


def test_test_point_on_ground_net_is_test_point_power_or_ground(tmp_path: Path) -> None:
    sch = schematic_fixture([component("TP3")], [net("GND", [node("TP3", "1", "TP")])], power=[], ground=["GND"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "TP3")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "test_point_power_or_ground"


def test_pullup_resistor_classification(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R10", value="4K7")], [net("V3P3", [node("R10", "1", None)]), net("SDA", [node("R10", "2", None)])], power=["V3P3"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "R10")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "pullup_resistor"
    assert "not an explicit load current model" in role["unresolved"]


def test_pulldown_resistor_classification(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R11", value="5K1")], [net("BUTTON", [node("R11", "1", None)]), net("GND", [node("R11", "2", None)])], power=[], ground=["GND"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "R11")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "pulldown_resistor"


def test_divider_or_bleeder_resistor_candidate(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R12", value="10K")], [net("V5P0", [node("R12", "1", None)]), net("GND", [node("R12", "2", None)])], power=["V5P0"], ground=["GND"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "R12")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "divider_or_bleeder_candidate"
    assert "current model requires full resistor network context" in role["unresolved"]


def test_differential_termination_candidate(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R13", value="120R")], [net("CANH", [node("R13", "1", None)]), net("CANL", [node("R13", "2", None)])], power=[], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "R13")
    assert role["role"] == "sink"
    assert role["role_subtype"] == "differential_termination_candidate"
    assert role["role_subtype"] != "zero_ohm_link"


def test_series_termination_candidate(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R14", value="33R")], [net("MCU_CLK", [node("R14", "1", None)]), net("CLK_OUT", [node("R14", "2", None)])], power=[], ground=[], clock=["MCU_CLK", "CLK_OUT"])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "R14")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "series_termination_candidate"


def test_nonzero_resistor_with_insufficient_context_is_resistor_nonzero_unknown(tmp_path: Path) -> None:
    sch = schematic_fixture([component("R15", value="5K1")], [net("SIG_ONLY", [node("R15", "1", None)])], power=[], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    role = role_for(artifact, "R15")
    assert role["role"] == "unknown"
    assert role["role_subtype"] == "resistor_nonzero_unknown"
    assert any(item["category"] == "resistor_role_unknown" for item in artifact["unresolved"])


def test_mosfet_level_shifter_candidate(tmp_path: Path) -> None:
    sch = schematic_fixture([component("Q1", value="BSS138")], [net("SDA_3V3", [node("Q1", "1", None)]), net("SDA_5V", [node("Q1", "2", None)]), net("GATE", [node("Q1", "3", None)])], power=[], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "Q1")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "mosfet_level_shifter_candidate"


def test_mosfet_power_switch_candidate_emits_unresolved(tmp_path: Path) -> None:
    sch = schematic_fixture([component("Q2", value="FDS4435BZ")], [net("V5P0", [node("Q2", "1", None)]), net("LOAD_SW", [node("Q2", "2", None)]), net("EN_SW", [node("Q2", "3", None)])], power=["V5P0", "LOAD_SW"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    role = role_for(artifact, "Q2")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "mosfet_power_switch_candidate"
    assert any(item["category"] == "power_path_direction_unknown" for item in artifact["unresolved"])


def test_generic_q_part_on_signal_nets_is_mosfet_signal_or_switch(tmp_path: Path) -> None:
    sch = schematic_fixture([component("Q3", value="MMBT3904")], [net("SIG_A", [node("Q3", "1", None)]), net("SIG_B", [node("Q3", "2", None)]), net("CTRL", [node("Q3", "3", None)])], power=[], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "Q3")
    assert role["role"] == "bidirectional_or_interface"
    assert role["role_subtype"] == "mosfet_signal_or_switch"


def test_mosfet_classification_does_not_infer_current_or_rating_fields(tmp_path: Path) -> None:
    sch = schematic_fixture([component("Q4", value="AO3400")], [net("V5P0", [node("Q4", "1", None)]), net("LOAD", [node("Q4", "2", None)])], power=["V5P0"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    role = role_for(read_json(out), "Q4")
    forbidden = [key for key in role if "current" in key.lower() or "rating" in key.lower() or "rds" in key.lower()]
    assert forbidden == []


def test_unknown_component_emits_component_role_unknown_unresolved(tmp_path: Path) -> None:
    sch = schematic_fixture([component("X1")], [net("SIG", [node("X1", "1", "IO")])], power=[], ground=[], clock=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert role_for(artifact, "X1")["role"] == "unknown"
    assert any(item["category"] == "component_role_unknown" and item["target_id"] == "X1" for item in artifact["unresolved"])


def test_net_roles_preserve_power_ground_clock_signal_classification(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U1", value="MCU")],
        [
            net("V3P3", [node("U1", "1", "VDD")]),
            net("GND", [node("U1", "2", "GND")]),
            net("CLK", [node("U1", "3", "CLK")]),
            net("GPIO1", [node("U1", "4", "GPIO")]),
        ],
        power=["V3P3"],
        ground=["GND"],
        clock=["CLK"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert net_role_for(artifact, "V3P3")["role"] == "power"
    assert net_role_for(artifact, "GND")["role"] == "ground"
    assert net_role_for(artifact, "CLK")["role"] == "clock"
    assert net_role_for(artifact, "GPIO1")["role"] == "signal"


def test_pin_roles_classify_vin_vout_gnd_fb_en_sw(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U5", description="buck regulator")],
        [
            net("VIN", [node("U5", "1", "VIN")]),
            net("VOUT", [node("U5", "2", "VOUT")]),
            net("GND", [node("U5", "3", "GND")]),
            net("FB_NET", [node("U5", "4", "FB")]),
            net("EN_NET", [node("U5", "5", "EN")]),
            net("SW_NET", [node("U5", "6", "SW")]),
        ],
        power=["VIN", "VOUT"],
        ground=["GND"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    roles = pin_roles_for(read_json(out), "U5")
    assert roles["VIN"] == "power_in"
    assert roles["VOUT"] == "power_out"
    assert roles["GND"] == "ground"
    assert roles["FB"] == "feedback"
    assert roles["EN"] == "enable"
    assert roles["SW"] == "switch_node"


def test_regulator_missing_clear_vout_emits_regulator_input_output_unknown(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [component("U6", description="LDO regulator")],
        [net("VIN", [node("U6", "1", "VIN")]), net("GND", [node("U6", "2", "GND")])],
        power=["VIN"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "regulator_input_output_unknown" in role_for(artifact, "U6")["unresolved"]
    assert any(item["category"] == "regulator_input_output_unknown" for item in artifact["unresolved"])


def test_connector_direction_ambiguity_emits_connector_direction_unknown(tmp_path: Path) -> None:
    sch = schematic_fixture([component("P1", value="CONN")], [net("V3P3", [node("P1", "1", "VCC")])], power=["V3P3"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert "connector_direction_unknown" in role_for(artifact, "P1")["unresolved"]
    assert any(item["category"] == "connector_direction_unknown" for item in artifact["unresolved"])


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    sch = schematic_fixture([component("BT1", value="battery")], [net("VBAT", [node("BT1", "1", "+")])], power=["VBAT"], ground=[])
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "component_roles",
        "net_roles",
        "pin_roles",
        "role_edges",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "role_resolution_pass",
    }
    assert expected.issubset(artifact)


def test_summary_counts_are_internally_consistent(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [
            component("TP1"),
            component("R1", value="4K7"),
            component("Q1", value="BSS138"),
            component("U1", value="MCU"),
        ],
        [
            net("V3P3", [node("R1", "1", None), node("U1", "1", "VDD")]),
            net("SDA", [node("R1", "2", None), node("Q1", "1", None), node("TP1", "1", "TP")]),
            net("SCL", [node("Q1", "2", None)]),
            net("GND", [node("U1", "2", "GND")]),
        ],
        power=["V3P3"],
        ground=["GND"],
        clock=[],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    roles = artifact["component_roles"]
    assert summary["component_count"] == len(roles)
    assert summary["net_count"] == len(artifact["net_roles"])
    assert summary["role_candidate_count"] == len(roles)
    assert summary["source_candidate_count"] == sum(1 for row in roles if row["role"] == "source")
    assert summary["sink_candidate_count"] == sum(1 for row in roles if row["role"] == "sink")
    assert summary["pass_through_candidate_count"] == sum(1 for row in roles if row["role"] == "pass_through")
    assert summary["unknown_candidate_count"] == sum(1 for row in roles if row["role"] == "unknown")
    assert summary["unresolved_count"] == len(artifact["unresolved"])


def test_exit_code_2_for_missing_required_input(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_resolver(
        "--project",
        "unit",
        "--topology",
        str(tmp_path / "missing-topology.json"),
        "--schematic",
        str(tmp_path / "missing-schematic.json"),
        "--out",
        str(out),
    )

    assert result.returncode == 2
    assert not out.exists()


def test_manual_converter_shaped_schematic_fixture_works(tmp_path: Path) -> None:
    sch = schematic_fixture(
        [
            component("P20", value="CONN", description="POWER_CONNECTOR"),
            component("U50", value="3.3V LDO", description="LDO_REG_3V3"),
            component("U45", value="CAN", description="CAN_TRANSCEIVER"),
            component("C40", value="0.1UF", description="CAP_CER_0.1UF"),
        ],
        [
            net("V24P0", [node("P20", "1", "VIN+")]),
            net("V5P0", [node("P20", "3", "5V"), node("U50", "1", "VIN")]),
            net("V3P3", [node("U50", "2", "VOUT"), node("U45", "1", "VDD"), node("C40", "2", None)]),
            net("GND", [node("P20", "4", "GND"), node("U50", "3", "GND"), node("U45", "2", "GND"), node("C40", "1", None)]),
            net("MOTION_CLK", [node("U45", "3", "CLK")]),
        ],
        power=["V24P0", "V5P0", "V3P3"],
        ground=["GND"],
        clock=["MOTION_CLK"],
    )
    result, out = invoke(tmp_path, sch)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["summary"]["component_count"] == 4
    assert artifact["summary"]["net_count"] == 5
    assert artifact["component_roles"]
    assert artifact["net_roles"]
    assert artifact["pin_roles"]
    assert artifact["role_edges"]
