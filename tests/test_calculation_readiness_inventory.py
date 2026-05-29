from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "calculation_readiness_inventory.py"


def run_inventory(*args: str) -> subprocess.CompletedProcess[str]:
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


def candidate(refdes: str, role: str, subtype: str) -> dict:
    return {"refdes": refdes, "role": role, "role_subtype": subtype, "confidence": 0.8, "evidence_refs": []}


def geometry(
    *,
    layer: str | None = "TOP",
    copper: float | None = 1.0,
    width: float | None = 0.01,
    length: float | None = 1.0,
    area: float | None = None,
    bbox: dict | None = None,
) -> dict:
    return {
        "has_geometry_context": True,
        "geometry_record_count": 1,
        "evidence_count": 1,
        "unresolved_count": 0,
        "branch_type": "trace_group",
        "layer": layer,
        "copper_thickness": copper,
        "stackup": {"primary_layer": layer, "is_copper_layer": True, "copper_thickness": copper},
        "units": "INCH",
        "known_width_count": 1 if width is not None else 0,
        "min_width": width,
        "max_width": width,
        "total_length": length,
        "total_area": area,
        "bbox": bbox,
    }


def branch(
    branch_id: str,
    net: str,
    *,
    rail: str | None = None,
    role: str = "source",
    power: bool = True,
    ground: bool = False,
    sources: list[dict] | None = None,
    sinks: list[dict] | None = None,
    pass_through: list[dict] | None = None,
    parents: list[str] | None = None,
    children: list[str] | None = None,
    geom: dict | None = None,
    current_known: bool = False,
    current_a: float | None = None,
    unresolved: list[dict] | None = None,
) -> dict:
    sources = [] if sources is None else sources
    sinks = [] if sinks is None else sinks
    pass_through = [] if pass_through is None else pass_through
    parents = [] if parents is None else parents
    children = [] if children is None else children
    has_rail = rail is not None
    return {
        "branch_id": branch_id,
        "net_name": net,
        "rail_name": rail,
        "branch_type": "trace_group",
        "is_power_branch": power,
        "is_ground_branch": ground,
        "rail_role": role,
        "rail_voltage": 5.0 if rail not in {None, "VCC"} else None,
        "voltage_source": "net_name" if rail not in {None, "VCC"} else "unknown",
        "parent_rails": parents,
        "child_rails": children,
        "rail_relationships": [],
        "source_candidates": sources,
        "sink_candidates": sinks,
        "pass_through_candidates": pass_through,
        "connected_components": sources + sinks + pass_through,
        "geometry_context": geometry() if geom is None else geom,
        "current_model_status": {
            "branch_current_known": current_known,
            "branch_current_a": current_a,
            "current_source": "fixture" if current_known else None,
            "current_confidence": 1.0 if current_known else 0.0,
            "current_unresolved": not current_known,
        },
        "calculation_readiness_seed": {
            "has_rail_context": has_rail,
            "has_source_context": bool(sources or parents or role == "source"),
            "has_sink_context": bool(sinks or children),
            "has_geometry_context": bool(geom is None or geom),
            "has_current_model": current_known,
            "ready_for_current_allocation": bool(power and has_rail and (sources or parents or role == "source") and (sinks or children)),
            "blocked_reasons": [],
        },
        "evidence": [],
        "unresolved": unresolved or [],
    }


def rail(
    name: str,
    role: str,
    *,
    voltage: float | None = 5.0,
    parents: list[str] | None = None,
    children: list[str] | None = None,
    sources: list[str] | None = None,
    sinks: list[str] | None = None,
    branch_ids: list[str] | None = None,
    unresolved: list[dict] | None = None,
) -> dict:
    return {
        "rail": name,
        "role": role,
        "voltage": voltage,
        "parent_rails": parents or [],
        "child_rails": children or [],
        "source_components": sources or [],
        "sink_components": sinks or [],
        "pass_through_components": [],
        "branch_ids": branch_ids or [],
        "relationship_ids": [],
        "unresolved": unresolved or [],
    }


def enriched_fixture(branches: list[dict] | None = None, rails: list[dict] | None = None) -> dict:
    branches = branches if branches is not None else [
        branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector_power_input_or_io")], sinks=[candidate("U1", "sink", "ic_load")]),
        branch("br_gnd", "GND", rail="GND", role="return", power=False, ground=True, geom={}, sources=[], sinks=[]),
        branch("br_sig", "SDA", rail=None, role="unknown", power=False, ground=False, geom={}, sources=[], sinks=[]),
    ]
    rails = rails if rails is not None else [
        rail("V5P0", "source", sources=["P1"], sinks=["U1"], branch_ids=["br_v5"]),
        rail("GND", "return", voltage=None, branch_ids=["br_gnd"]),
    ]
    return {
        "schema_version": "1.0",
        "project": "unit",
        "generated_at_utc": "2026-05-29T00:00:00Z",
        "sources": {},
        "summary": {},
        "branches": branches,
        "rail_context": rails,
        "unresolved": [],
        "warnings": [],
        "errors": [],
        "execution_pass": True,
        "branch_enrichment_pass": True,
    }


def invoke(tmp_path: Path, enriched: dict | None = None) -> tuple[subprocess.CompletedProcess[str], Path]:
    enriched_path = write_json(tmp_path / "branch-enriched.json", enriched or enriched_fixture())
    out = tmp_path / "readiness.json"
    result = run_inventory("--project", "unit", "--branch-topology-enriched", str(enriched_path), "--out", str(out))
    return result, out


def branch_for(artifact: dict, branch_id: str) -> dict:
    return {row["branch_id"]: row for row in artifact["branch_readiness"]}[branch_id]


def rail_for(artifact: dict, name: str) -> dict:
    return {row["rail"]: row for row in artifact["rail_readiness"]}[name]


def categories(artifact: dict) -> set[str]:
    return {row["category"] for row in artifact["missing_data_items"]}


def test_missing_required_enriched_branch_topology_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    result = run_inventory("--project", "unit", "--branch-topology-enriched", str(tmp_path / "missing.json"), "--out", str(out))

    assert result.returncode == 2
    assert not out.exists()


def test_output_artifact_has_expected_top_level_shape(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    expected = {
        "schema_version",
        "project",
        "generated_at_utc",
        "sources",
        "summary",
        "branch_readiness",
        "rail_readiness",
        "missing_data_items",
        "unresolved",
        "warnings",
        "errors",
        "execution_pass",
        "calculation_readiness_pass",
    }
    assert expected.issubset(read_json(out))


def test_signal_branch_is_not_required_for_current_allocation_and_copper_calculation(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_sig")
    assert row["current_allocation_readiness"]["status"] == "not_required"
    assert row["copper_calculation_readiness"]["status"] == "not_required"


def test_ground_branch_is_not_required_and_does_not_emit_branch_current_unknown(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    row = branch_for(artifact, "br_gnd")
    assert row["current_allocation_readiness"]["status"] == "not_required"
    assert row["copper_calculation_readiness"]["status"] == "not_required"
    assert "branch_current_unknown" not in [item["category"] for item in row["unresolved"]]


def test_power_branch_with_rail_source_sink_context_ready_for_current_allocation_attempt(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert branch_for(read_json(out), "br_v5")["current_allocation_readiness"]["status"] == "ready"


def test_power_branch_with_no_rail_context_blocked_from_current_allocation_attempt(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail=None, role="unknown", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")])], [])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["current_allocation_readiness"]["status"] == "blocked"
    assert "branch_rail_unknown" in row["current_allocation_readiness"]["blocking_reasons"]


def test_power_branch_with_no_source_context_blocked_from_current_allocation_attempt(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v3", "V3P3", rail="V3P3", role="derived", sources=[], sinks=[candidate("U1", "sink", "ic_load")])], [rail("V3P3", "derived", sinks=["U1"], branch_ids=["br_v3"])])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v3")
    assert row["current_allocation_readiness"]["status"] == "blocked"
    assert "branch_source_unknown" in row["current_allocation_readiness"]["blocking_reasons"]


def test_power_branch_with_no_sink_context_blocked_from_current_allocation_attempt(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[], children=[])], [rail("V5P0", "source", sources=["P1"], branch_ids=["br_v5"])])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["current_allocation_readiness"]["status"] == "blocked"
    assert "branch_sink_unknown" in row["current_allocation_readiness"]["blocking_reasons"]


def test_current_unknown_does_not_block_current_allocation_attempt(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["available_context"]["has_current_model"] is False
    assert row["current_allocation_readiness"]["status"] == "ready"


def test_current_unknown_blocks_copper_calculation_readiness(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["copper_calculation_readiness"]["status"] == "blocked"
    assert "branch_current_unknown" in row["copper_calculation_readiness"]["blocking_reasons"]


def test_missing_geometry_blocks_copper_calculation_readiness(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], geom={})])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "geometry_context_missing" in branch_for(read_json(out), "br_v5")["copper_calculation_readiness"]["blocking_reasons"]


def test_missing_layer_blocks_copper_calculation_readiness(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], current_known=True, current_a=0.1, geom=geometry(layer=None))])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "layer_unknown" in branch_for(read_json(out), "br_v5")["copper_calculation_readiness"]["blocking_reasons"]


def test_missing_copper_thickness_blocks_copper_calculation_readiness(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], current_known=True, current_a=0.1, geom=geometry(copper=None))])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "copper_thickness_missing" in branch_for(read_json(out), "br_v5")["copper_calculation_readiness"]["blocking_reasons"]


def test_missing_width_area_blocks_copper_calculation_readiness(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], current_known=True, current_a=0.1, geom=geometry(width=None, length=1.0, area=None, bbox=None))])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "geometry_width_missing" in branch_for(read_json(out), "br_v5")["copper_calculation_readiness"]["blocking_reasons"]


def test_explicit_current_plus_geometry_layer_thickness_width_makes_copper_calculation_ready(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], current_known=True, current_a=0.1)])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert branch_for(read_json(out), "br_v5")["copper_calculation_readiness"]["status"] == "ready"


def test_rail_with_source_and_sink_context_ready_for_current_allocation_attempt(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert rail_for(read_json(out), "V5P0")["current_allocation_readiness"]["status"] == "ready"


def test_rail_missing_source_context_emits_rail_source_unknown(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v3", "V3P3", rail="V3P3", role="derived", sources=[], sinks=[candidate("U1", "sink", "ic_load")])], [rail("V3P3", "derived", sinks=["U1"], branch_ids=["br_v3"])])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert rail_for(artifact, "V3P3")["current_allocation_readiness"]["status"] == "blocked"
    assert "rail_source_unknown" in categories(artifact)


def test_rail_missing_sink_context_emits_rail_sink_unknown(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[])], [rail("V5P0", "source", sources=["P1"], branch_ids=["br_v5"])])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert rail_for(artifact, "V5P0")["current_allocation_readiness"]["status"] == "blocked"
    assert "rail_sink_unknown" in categories(artifact)


def test_return_rail_is_not_required(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert rail_for(read_json(out), "GND")["current_allocation_readiness"]["status"] == "not_required"


def test_relationship_direction_unresolved_creates_missing_data_item(tmp_path: Path) -> None:
    unresolved = [{
        "id": "unres_rel",
        "category": "relationship_direction_unknown",
        "target_type": "relationship",
        "target_id": "rel_v5_q1_v3",
        "notes": "Direction is ambiguous.",
        "blocks": ["current_allocation"],
        "recommended_resolution": "human_review",
        "candidate_rule_ids": [],
    }]
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], unresolved=unresolved)])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "relationship_direction_unknown" in categories(read_json(out))


def test_missing_data_items_deduplicate_deterministically(tmp_path: Path) -> None:
    duplicate = {
        "id": "dupe",
        "category": "relationship_direction_unknown",
        "target_type": "relationship",
        "target_id": "rel_v5_q1_v3",
        "notes": "Direction is ambiguous.",
        "blocks": ["current_allocation"],
        "recommended_resolution": "human_review",
        "candidate_rule_ids": [],
    }
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail="V5P0", sources=[candidate("P1", "source", "connector")], sinks=[candidate("U1", "sink", "ic_load")], unresolved=[duplicate, dict(duplicate)])])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    items = [item for item in read_json(out)["missing_data_items"] if item["category"] == "relationship_direction_unknown"]
    assert len(items) == 1


def test_missing_data_ids_are_stable(tmp_path: Path) -> None:
    enriched = enriched_fixture([branch("br_v5", "V5P0", rail=None, role="unknown", sources=[], sinks=[])], [])
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    ids = sorted(item["id"] for item in read_json(out)["missing_data_items"])
    assert "mdi_branch_rail_unknown_branch_br_v5_current_allocation_calculation_readiness" in ids
    assert ids == sorted(ids)


def test_summary_counts_are_internally_consistent(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    summary = artifact["summary"]
    branches = artifact["branch_readiness"]
    rails = artifact["rail_readiness"]
    assert summary["branch_count"] == len(branches)
    assert summary["power_branch_count"] == sum(1 for row in branches if row["is_power_branch"])
    assert summary["ground_branch_count"] == sum(1 for row in branches if row["is_ground_branch"] or row["rail_role"] == "return")
    assert summary["branches_ready_for_current_allocation_attempt"] == sum(1 for row in branches if row["current_allocation_readiness"]["status"] == "ready")
    assert summary["branches_blocked_from_current_allocation_attempt"] == sum(1 for row in branches if row["current_allocation_readiness"]["status"] == "blocked")
    assert summary["rails_ready_for_current_allocation_attempt"] == sum(1 for row in rails if row["current_allocation_readiness"]["status"] == "ready")
    assert summary["rails_blocked_from_current_allocation_attempt"] == sum(1 for row in rails if row["current_allocation_readiness"]["status"] == "blocked")
    assert summary["missing_data_item_count"] == len(artifact["missing_data_items"])
    assert summary["unresolved_count"] == len(artifact["unresolved"])


def test_no_current_is_inferred_when_absent(tmp_path: Path) -> None:
    result, out = invoke(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    row = branch_for(read_json(out), "br_v5")
    assert row["available_context"]["has_current_model"] is False
    assert row["copper_calculation_readiness"]["status"] == "blocked"


def test_manual_converter_shaped_minimal_fixture_works(tmp_path: Path) -> None:
    enriched = enriched_fixture(
        [
            branch("br_v24", "V24P0", rail="V24P0", role="source", sources=[candidate("P20", "source", "connector_power_input_or_io")], sinks=[], children=["V24P0_SW"]),
            branch("br_sw", "V24P0_SW", rail="V24P0_SW", role="switched", parents=["V24P0"], sinks=[candidate("Q2", "bidirectional_or_interface", "mosfet_power_switch_candidate")]),
            branch("br_sig", "SDA", rail=None, power=False, ground=False, geom={}, sources=[], sinks=[]),
        ],
        [
            rail("V24P0", "source", children=["V24P0_SW"], sources=["P20"], branch_ids=["br_v24"]),
            rail("V24P0_SW", "switched", parents=["V24P0"], sinks=["Q2"], branch_ids=["br_sw"]),
        ],
    )
    result, out = invoke(tmp_path, enriched)

    assert result.returncode == 0, result.stderr + result.stdout
    artifact = read_json(out)
    assert artifact["execution_pass"] is True
    assert artifact["calculation_readiness_pass"] is True
    assert artifact["branch_readiness"]
    assert artifact["rail_readiness"]
