from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rail_relationship_extract.py"


def run_extractor(*args: str) -> subprocess.CompletedProcess[str]:
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


def net_role(name: str, role: str = "power", voltage: float | None = None) -> dict:
    return {
        "net_name": name,
        "role": role,
        "voltage": voltage,
        "confidence": 0.9,
        "evidence": [],
        "connected_sources": [],
        "connected_sinks": [],
        "connected_pass_through": [],
        "unresolved": [],
    }


def component_role(
    refdes: str,
    role: str,
    subtype: str,
    nets: list[str],
    *,
    power: list[str] | None = None,
    ground: list[str] | None = None,
) -> dict:
    return {
        "refdes": refdes,
        "mpn": None,
        "value": None,
        "description": "",
        "footprint": "",
        "role": role,
        "role_subtype": subtype,
        "confidence": 0.8,
        "evidence": [],
        "connected_nets": nets,
        "power_nets": power if power is not None else [net for net in nets if net.startswith("V")],
        "ground_nets": ground or [],
        "input_nets": [],
        "output_nets": [],
        "pass_through_nets": nets if role == "pass_through" else [],
        "unresolved": [],
    }


def pin_role(refdes: str, pin_name: str, net: str, role: str) -> dict:
    return {
        "refdes": refdes,
        "pin_number": pin_name,
        "pin_name": pin_name,
        "net_name": net,
        "pin_role": role,
        "confidence": 0.9,
        "evidence": [],
    }


def role_resolution_fixture(
    *,
    nets: list[dict] | None = None,
    components: list[dict] | None = None,
    pins: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "component_roles": components or [],
        "net_roles": nets or [],
        "pin_roles": pins or [],
        "role_edges": [],
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "role_resolution_pass": True,
    }


def topology_fixture(power: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "project": "unit",
        "nets": [{"net_name": name, "net_type": "power"} for name in (power or [])],
        "power_rails": [{"net_name": name} for name in (power or [])],
    }


def schematic_fixture(power: list[str] | None = None, ground: list[str] | None = None) -> dict:
    return {"components": [], "nets": [], "analysis": {"power_nets": power or [], "ground_nets": ground or [], "clock_nets": []}}


def invoke(tmp_path: Path, role_resolution: dict, *, topology: dict | None = None, schematic: dict | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
    role_path = write_json(tmp_path / "role-resolution.json", role_resolution)
    out = tmp_path / "rail-relationships.json"
    args = ["--project", "unit", "--role-resolution", str(role_path), "--out", str(out)]
    if topology is not None:
        args.extend(["--topology", str(write_json(tmp_path / "topology.json", topology))])
    if schematic is not None:
        args.extend(["--schematic", str(write_json(tmp_path / "schematic.json", schematic))])
    result = run_extractor(*args)
    return result, out


def relationship_for(artifact: dict, through: str) -> dict:
    return [row for row in artifact["relationships"] if row["through_component"] == through][0]


def rail_for(artifact: dict, name: str) -> dict:
    return {row["rail"]: row for row in artifact["rails"]}[name]


def test_parses_voltage_names(tmp_path: Path) -> None:
    names = ["V24P0", "V5P0", "V3P3", "VN24P0", "VCC"]
    result, out = invoke(tmp_path, role_resolution_fixture(nets=[net_role(name) for name in names]))

    assert result.returncode == 0, result.stderr + result.stdout
    rails = {row["rail"]: row for row in read_json(out)["rails"]}
    assert rails["V24P0"]["voltage"] == 24.0
    assert rails["V5P0"]["voltage"] == 5.0
    assert rails["V3P3"]["voltage"] == 3.3
    assert rails["VN24P0"]["voltage"] == -24.0
    assert rails["VCC"]["voltage"] is None


def test_discovers_rails_from_role_resolution_net_roles(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, role_resolution_fixture(nets=[net_role("V3P3"), net_role("GND", "ground")]))

    assert result.returncode == 0, result.stderr + result.stdout
    assert {row["rail"] for row in read_json(out)["rails"]} == {"GND", "V3P3"}


def test_connector_power_input_creates_connector_input_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V24P0")],
        components=[component_role("P1", "source", "connector_power_input_or_io", ["V24P0"], power=["V24P0"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    rel = relationship_for(read_json(out), "P1")
    assert rel["relationship_type"] == "connector_input"
    assert rel["parent_rail"] is None
    assert rel["child_rail"] == "V24P0"


def test_regulator_with_vin_vout_pin_roles_creates_regulator_conversion(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("V3P3")],
        components=[component_role("U1", "source", "ldo", ["V5P0", "V3P3", "GND"], power=["V5P0", "V3P3"], ground=["GND"])],
        pins=[pin_role("U1", "VIN", "V5P0", "power_in"), pin_role("U1", "VOUT", "V3P3", "power_out")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    rel = relationship_for(read_json(out), "U1")
    assert rel["relationship_type"] == "regulator_conversion"
    assert rel["parent_rail"] == "V5P0"
    assert rel["child_rail"] == "V3P3"
    assert rel["direction"] == "parent_to_child"


def test_regulator_with_ambiguous_vin_vout_emits_unresolved(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0")],
        components=[component_role("U1", "source", "ldo", ["V5P0"], power=["V5P0"])],
        pins=[pin_role("U1", "VIN", "V5P0", "power_in")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["category"] == "regulator_input_output_unknown" for item in read_json(out)["unresolved"])


def test_regulator_like_description_without_pin_names_creates_conservative_voltage_relationship(tmp_path: Path) -> None:
    reg = component_role("U50", "sink", "ic_load", ["V5P0", "V3P3", "GND"], power=["V5P0", "V3P3"], ground=["GND"])
    reg["description"] = "PWR_LIN_3V3 regulator-like component"
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("V3P3"), net_role("GND", "ground")],
        components=[reg],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    rel = relationship_for(artifact, "U50")
    assert rel["relationship_type"] == "regulator_conversion"
    assert rel["parent_rail"] == "V5P0"
    assert rel["child_rail"] == "V3P3"
    assert any(item["category"] == "regulator_input_output_unknown" for item in artifact["unresolved"])


def test_mosfet_power_switch_between_raw_and_switched_rail_creates_switched_power_path(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V24P0")],
        components=[component_role("Q2", "bidirectional_or_interface", "mosfet_power_switch_candidate", ["V24P0", "V24P0_SW", "EN"], power=["V24P0"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    rel = relationship_for(read_json(out), "Q2")
    assert rel["relationship_type"] == "switched_power_path"
    assert rel["parent_rail"] == "V24P0"
    assert rel["child_rail"] == "V24P0_SW"
    assert any(item["category"] == "power_path_direction_unknown" for item in rel["unresolved"])


def test_mosfet_power_switch_does_not_infer_current_or_rating_fields(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V24P0")],
        components=[component_role("Q2", "bidirectional_or_interface", "mosfet_power_switch_candidate", ["V24P0", "V24P0_SW"], power=["V24P0"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    rel = relationship_for(read_json(out), "Q2")
    forbidden = [key for key in rel if "current" in key.lower() or "rating" in key.lower() or "rds" in key.lower()]
    assert forbidden == []


def test_zero_ohm_link_between_two_power_rails_creates_pass_through_candidate(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("VCC")],
        components=[component_role("R1", "pass_through", "zero_ohm_link", ["V5P0", "VCC"], power=["V5P0", "VCC"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert relationship_for(read_json(out), "R1")["relationship_type"] == "pass_through"


def test_zero_ohm_link_between_signal_nets_does_not_create_rail_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V3P3")],
        components=[component_role("R1", "pass_through", "zero_ohm_link", ["SIG_A", "SIG_B"], power=[])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["relationships"] == []


def test_pullup_resistor_does_not_create_parent_child_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V3P3")],
        components=[component_role("R1", "sink", "pullup_resistor", ["V3P3", "SDA"], power=["V3P3"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["relationships"] == []


def test_divider_bleeder_candidate_does_not_create_parent_child_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("GND", "ground")],
        components=[component_role("R1", "sink", "divider_or_bleeder_candidate", ["V5P0", "GND"], power=["V5P0"], ground=["GND"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["relationships"] == []


def test_passive_decoupling_does_not_create_parent_child_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V3P3"), net_role("GND", "ground")],
        components=[component_role("C1", "sink", "passive_decoupling", ["V3P3", "GND"], power=["V3P3"], ground=["GND"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["relationships"] == []


def test_test_point_does_not_create_parent_child_relationship(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V3P3")],
        components=[component_role("TP1", "bidirectional_or_interface", "test_point_power_or_ground", ["V3P3"], power=["V3P3"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert read_json(out)["relationships"] == []


def test_jp1_like_unknown_component_creates_low_confidence_candidate_and_unresolved(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("VCC")],
        components=[component_role("JP1", "unknown", "unknown", ["V24P0_SW", "V5P0", "VCC"], power=["V5P0", "VCC"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert any(rel["relationship_type"] == "candidate" and rel["confidence"] <= 0.45 for rel in artifact["relationships"])
    assert any(item["category"] == "ambiguous_pass_through" for item in artifact["unresolved"])


def test_rail_with_sink_and_no_source_emits_rail_source_unknown(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V3P3")],
        components=[component_role("U1", "sink", "ic_load", ["V3P3"], power=["V3P3"])],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert any(item["category"] == "rail_source_unknown" for item in read_json(out)["unresolved"])


def test_rail_with_parent_relationship_gets_parent_rails_populated(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("V3P3")],
        components=[component_role("U1", "source", "ldo", ["V5P0", "V3P3"], power=["V5P0", "V3P3"])],
        pins=[pin_role("U1", "VIN", "V5P0", "power_in"), pin_role("U1", "VOUT", "V3P3", "power_out")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert rail_for(read_json(out), "V3P3")["parent_rails"] == ["V5P0"]


def test_rail_with_child_relationship_gets_child_rails_populated(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("V3P3")],
        components=[component_role("U1", "source", "ldo", ["V5P0", "V3P3"], power=["V5P0", "V3P3"])],
        pins=[pin_role("U1", "VIN", "V5P0", "power_in"), pin_role("U1", "VOUT", "V3P3", "power_out")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    assert rail_for(read_json(out), "V5P0")["child_rails"] == ["V3P3"]


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, role_resolution_fixture(nets=[net_role("V3P3")]))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "rails",
        "relationships",
        "source_candidates",
        "derived_candidates",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "rail_relationship_pass",
    }
    assert expected.issubset(artifact)


def test_summary_counts_are_internally_consistent(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V5P0"), net_role("V3P3")],
        components=[component_role("U1", "source", "ldo", ["V5P0", "V3P3"], power=["V5P0", "V3P3"])],
        pins=[pin_role("U1", "VIN", "V5P0", "power_in"), pin_role("U1", "VOUT", "V3P3", "power_out")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    assert summary["rail_count"] == len(artifact["rails"])
    assert summary["relationship_count"] == len(artifact["relationships"])
    assert summary["source_rail_count"] == sum(1 for rail in artifact["rails"] if rail["role"] == "source")
    assert summary["derived_rail_count"] == sum(1 for rail in artifact["rails"] if rail["role"] == "derived")
    assert summary["switched_rail_count"] == sum(1 for rail in artifact["rails"] if rail["role"] == "switched")
    assert summary["ambiguous_relationship_count"] == sum(1 for rel in artifact["relationships"] if rel["relationship_type"] == "candidate" or rel["direction"] == "unknown")
    assert summary["unresolved_count"] == len(artifact["unresolved"])


def test_missing_required_role_resolution_input_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_extractor("--project", "unit", "--role-resolution", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_manual_converter_shaped_minimal_role_resolution_fixture_works(tmp_path: Path) -> None:
    role_resolution = role_resolution_fixture(
        nets=[net_role("V24P0"), net_role("V5P0"), net_role("V3P3"), net_role("GND", "ground")],
        components=[
            component_role("P20", "source", "connector_power_input_or_io", ["V24P0", "V5P0", "GND"], power=["V24P0", "V5P0"], ground=["GND"]),
            component_role("U50", "source", "ldo", ["V5P0", "V3P3", "GND"], power=["V5P0", "V3P3"], ground=["GND"]),
            component_role("Q2", "bidirectional_or_interface", "mosfet_power_switch_candidate", ["V24P0", "V24P0_SW", "EN"], power=["V24P0"]),
        ],
        pins=[pin_role("U50", "VIN", "V5P0", "power_in"), pin_role("U50", "VOUT", "V3P3", "power_out")],
    )
    result, out = invoke(tmp_path, role_resolution)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["rail_relationship_pass"] is True
    assert artifact["rails"]
    assert artifact["relationships"]
