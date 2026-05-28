from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "topology_validate.py"
SCHEMA = ROOT / "schemas" / "topology_map_schema.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
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


def minimal_topology(*, unresolved: bool = False) -> dict:
    unresolved_items = []
    if unresolved:
        unresolved_items = [
            {
                "id": "unres_vcc_no_source",
                "type": "power_net_no_source",
                "net": "VCC",
                "affected_refdes": [],
                "part_info_ref": None,
                "required_for": ["voltage_model", "current_model", "trace_current"],
                "human_review_needed": True,
                "notes": "No deterministic source.",
            },
            {
                "id": "unres_vcc_voltage",
                "type": "voltage_unknown",
                "net": "VCC",
                "affected_refdes": [],
                "part_info_ref": None,
                "required_for": ["voltage_model"],
                "human_review_needed": True,
                "notes": "Voltage unknown.",
            },
            {
                "id": "unres_u1_vcc_current",
                "type": "sink_current_unknown",
                "net": "VCC",
                "affected_refdes": ["U1"],
                "part_info_ref": None,
                "required_for": ["current_model", "trace_current", "thermal"],
                "human_review_needed": True,
                "notes": "Sink current unknown.",
            },
        ]

    topology = {
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
        "graph_summary": {
            "net_count": 2,
            "device_count": 1,
            "power_rail_count": 1,
            "branch_count": 0,
            "unresolved_count": len(unresolved_items),
        },
        "nets": [
            {
                "net_name": "VCC",
                "net_type": "power",
                "pin_refs": ["U1.1"],
                "nominal_voltage_v": None if unresolved else 3.3,
                "voltage_model_ref": "vm_vcc",
                "confidence": 0.7,
                "unresolved_flags": ["voltage_unknown"] if unresolved else [],
            },
            {
                "net_name": "GND",
                "net_type": "ground",
                "pin_refs": ["U1.2"],
                "nominal_voltage_v": None,
                "voltage_model_ref": None,
                "confidence": 0.9,
                "unresolved_flags": [],
            },
        ],
        "power_rails": [
            {
                "net_name": "VCC",
                "nominal_voltage_v": None if unresolved else 3.3,
                "voltage_source": "unknown" if unresolved else "derived_from_net_name",
                "source_components": [] if unresolved else ["J1"],
                "pass_through_components": [],
                "sink_components": ["U1"] if unresolved else [],
                "total_nominal_current_a": None,
                "total_max_current_a": None,
                "unresolved_current_a": None,
                "confidence": 0.5,
                "current_model_ref": "cm_vcc",
                "voltage_model_ref": "vm_vcc",
                "unresolved_flags": ["power_net_no_source", "voltage_unknown", "sink_current_unknown", "rail_current_unresolved"]
                if unresolved
                else ["rail_current_unresolved"],
            }
        ],
        "devices": [
            {
                "refdes": "U1",
                "mpn": "MCU",
                "manufacturer": "Example",
                "device_role": "sink",
                "input_nets": [],
                "output_nets": [],
                "supply_nets": ["VCC"],
                "ground_nets": ["GND"],
                "signal_nets": [],
                "part_info_ref": None,
                "current_model": None,
                "confidence": 0.7,
                "unresolved": [],
            }
        ],
        "pins": [
            {
                "pin_ref": "U1.1",
                "refdes": "U1",
                "pin": "1",
                "pin_name": "VDD",
                "net_name": "VCC",
                "role": "power",
                "confidence": 0.6,
                "part_info_pin_ref": None,
                "unresolved_flags": [],
            },
            {
                "pin_ref": "U1.2",
                "refdes": "U1",
                "pin": "2",
                "pin_name": "GND",
                "net_name": "GND",
                "role": "ground",
                "confidence": 0.6,
                "part_info_pin_ref": None,
                "unresolved_flags": [],
            },
        ],
        "pass_through_edges": [],
        "source_nodes": []
        if unresolved
        else [
            {
                "node_id": "src_j1_vcc",
                "source_type": "external_connector",
                "refdes": None,
                "pin_ref": None,
                "net_name": "VCC",
                "confidence": 0.5,
            }
        ],
        "sink_nodes": [
            {
                "node_id": "sink_u1_vcc",
                "sink_type": "ic_supply",
                "refdes": "U1",
                "pin_ref": "U1.1",
                "net_name": "VCC",
                "current_model_ref": "cm_u1_vcc",
                "confidence": 0.5,
                "unresolved_flags": ["sink_current_unknown"],
            }
        ]
        if unresolved
        else [],
        "branches": [],
        "copper_geometry_links": [],
        "current_models": [
            {
                "model_id": "cm_vcc",
                "target": "rail:VCC",
                "type": "rail_total",
                "basis": "unresolved",
                "nominal_current_a": None,
                "max_current_a": None,
                "conservative_bound": False,
                "confidence": 0.3,
                "unresolved_flags": ["rail_current_unresolved"],
            }
        ]
        + (
            [
                {
                    "model_id": "cm_u1_vcc",
                    "target": "device:U1",
                    "type": "sink_load",
                    "basis": "unresolved",
                    "nominal_current_a": None,
                    "max_current_a": None,
                    "conservative_bound": False,
                    "confidence": 0.3,
                    "unresolved_flags": ["sink_current_unknown"],
                }
            ]
            if unresolved
            else []
        ),
        "voltage_models": [
            {
                "model_id": "vm_vcc",
                "target": "net:VCC",
                "nominal_voltage_v": None if unresolved else 3.3,
                "min_voltage_v": None,
                "max_voltage_v": None,
                "basis": "unknown" if unresolved else "net_name",
                "confidence": 0.3 if unresolved else 0.75,
                "unresolved_flags": ["voltage_unknown"] if unresolved else [],
            }
        ],
        "unresolved": unresolved_items,
        "validation": {
            "execution_pass": True,
            "artifact_validation_pass": True,
            "topology_consistency_pass": not unresolved,
            "unresolved_items_present": bool(unresolved),
            "human_review_needed": bool(unresolved),
            "errors": [],
            "warnings": [],
        },
    }
    return topology


def invoke(tmp_path: Path, topology: dict, *extra: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    topology_path = write_json(tmp_path / "topology-map.json", topology)
    out = tmp_path / "validation.json"
    result = run_validator(
        "--project",
        "unit",
        "--topology",
        str(topology_path),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
        *extra,
    )
    return result, out


def test_valid_minimal_topology_passes_non_strict(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_topology())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["artifact_validation_pass"] is True
    assert artifact["topology_consistency_pass"] is True
    assert artifact["phase_gate_passed"] is True
    assert artifact["overall_pass"] is True


def test_unresolved_items_pass_non_strict_but_report_human_review(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_topology(unresolved=True))

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["unresolved_items_present"] is True
    assert artifact["phase_gate_passed"] is True
    assert artifact["overall_pass"] is True
    assert artifact["summary"]["human_review_item_count"] >= 3
    assert {item["type"] for item in artifact["human_review_needed"]} >= {
        "power_net_no_source",
        "voltage_unknown",
        "sink_current_unknown",
    }


def test_strict_fails_when_unresolved_power_source_or_current_exists(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_topology(unresolved=True), "--strict")

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["phase_gate_passed"] is False
    assert artifact["overall_pass"] is False
    assert any("strict_mode" in error for error in artifact["errors"])


def test_schema_violation_fails_artifact_validation(tmp_path: Path) -> None:
    topology = minimal_topology()
    del topology["schema_version"]
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["artifact_validation_pass"] is False
    assert artifact["phase_gate_passed"] is False
    assert artifact["summary"]["schema_error_count"] > 0


def test_dangling_current_model_ref_is_consistency_error(tmp_path: Path) -> None:
    topology = minimal_topology()
    topology["power_rails"][0]["current_model_ref"] = "cm_missing"
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["topology_consistency_pass"] is False
    assert any("current_model_ref dangling" in error for error in artifact["errors"])


def test_dangling_voltage_model_ref_is_consistency_error(tmp_path: Path) -> None:
    topology = minimal_topology()
    topology["power_rails"][0]["voltage_model_ref"] = "vm_missing"
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert artifact["topology_consistency_pass"] is False
    assert any("voltage_model_ref dangling" in error for error in artifact["errors"])


def test_graph_summary_count_mismatch_is_consistency_error(tmp_path: Path) -> None:
    topology = minimal_topology()
    topology["graph_summary"]["net_count"] = 99
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert any("graph_summary.net_count" in error for error in artifact["errors"])


def test_duplicate_model_ids_are_consistency_error(tmp_path: Path) -> None:
    topology = minimal_topology()
    topology["current_models"].append(dict(topology["current_models"][0]))
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert any("duplicate current model_id" in error for error in artifact["errors"])


def test_power_rail_with_no_source_requires_unresolved_item(tmp_path: Path) -> None:
    topology = minimal_topology()
    topology["power_rails"][0]["source_components"] = []
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 1
    artifact = read_json(out)
    assert any("without power_net_no_source" in error for error in artifact["errors"])


def test_missing_current_is_not_treated_as_zero_and_zero_warns(tmp_path: Path) -> None:
    topology = minimal_topology()
    result, out = invoke(tmp_path, topology)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert not any("zero" in warning for warning in artifact["warnings"])

    topology["current_models"][0]["nominal_current_a"] = 0
    result, out = invoke(tmp_path / "zero", topology)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert any("nominal_current_a is zero" in warning for warning in artifact["warnings"])


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path, minimal_topology())

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "checks",
        "errors",
        "warnings",
        "human_review_needed",
        "execution_pass",
        "artifact_validation_pass",
        "topology_consistency_pass",
        "unresolved_items_present",
        "phase_gate_passed",
        "overall_pass",
    }
    assert expected.issubset(artifact)
    assert artifact["summary"]["net_count"] == 2
    assert artifact["checks"][0]["check"] == "schema_validation"


def test_exit_code_2_for_missing_input(tmp_path: Path) -> None:
    out = tmp_path / "validation.json"
    result = run_validator(
        "--project",
        "unit",
        "--topology",
        str(tmp_path / "missing-topology.json"),
        "--schema",
        str(SCHEMA),
        "--out",
        str(out),
    )

    assert result.returncode == 2
    assert not out.exists()
